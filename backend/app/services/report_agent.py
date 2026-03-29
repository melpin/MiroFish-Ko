"""
Report Agent
LangChain + ZepReACT시뮬레이션보고서 생성

:
1. 시뮬레이션Zep그래프정보생성보고서
2. 디렉터리, 생성
3. ReACT
4. , 호출도구
"""

import os
import json
import time
import re
from typing import Dict, Any, List, Optional, Callable
from datetime import datetime

from ..config import Config
from ..prompts import get_prompt
from ..utils.llm_client import LLMClient
from ..utils.logger import get_logger
from .report_logging import ReportConsoleLogger, ReportLogger
from .report_models import Report, ReportOutline, ReportSection, ReportStatus
from .report_storage import ReportManager
from .zep_tools import (
    ZepToolsService, 
    SearchResult, 
    InsightForgeResult, 
    PanoramaResult,
    InterviewResult
)

logger = get_logger('mirofish.report_agent')


# ═══════════════════════════════════════════════════════════════
# Prompt
# ═══════════════════════════════════════════════════════════════

# ── 도구 설명 ──

TOOL_DESC_INSIGHT_FORGE = """\
[심층 분석 도구]
질문 하나를 깊이 파고들어 근거 중심 분석을 수행합니다.

주요 기능:
1. 질문 의도와 핵심 쟁점 정리
2. 시뮬레이션 그래프에서 관련 엔터티/관계 추적
3. 사실 검색, 엔터티 분석, 관계 흐름 해석
4. 보고서에 바로 반영할 수 있는 인사이트 반환

적합한 사용 상황:
- 원인/맥락 분석이 필요한 질문
- 특정 주장에 대한 근거 검증
- 보고서 섹션의 핵심 논점 정리

반환 결과:
- 근거 사실(출처 포함)
- 핵심 엔터티
- 관계 흐름과 해석
"""

TOOL_DESC_PANORAMA_SEARCH = """\
[전역 탐색 도구]
시뮬레이션 그래프를 폭넓게 훑어 현재 상태를 빠르게 파악합니다.

주요 기능:
1. 노드/관계의 전체 분포 확인
2. 현재 유효 사실과 과거/만료 사실 구분 조회
3. 엔터티 관계의 전반적 구조 파악

적합한 사용 상황:
- 현황 요약이 필요할 때
- 탐색 초기 단계에서 큰 그림을 잡을 때
- 인터뷰 전 대상/맥락을 빠르게 훑을 때

반환 결과:
- 현재 유효 사실
- 과거/만료 사실
- 엔터티 및 관계 요약
"""

TOOL_DESC_QUICK_SEARCH = """\
[빠른 조회 도구]
특정 키워드나 조건으로 사실을 즉시 조회하는 경량 검색 도구입니다.

적합한 사용 상황:
- 숫자/사실을 빠르게 확인할 때
- 특정 엔터티 관련 정보를 단건 확인할 때
- 이미 가설이 있고 증거만 보강하면 될 때

반환 결과:
- 조회된 사실 목록
"""

TOOL_DESC_INTERVIEW_AGENTS = """\
[에이전트 인터뷰 도구(플랫폼 기반)]
OASIS 시뮬레이션 인터뷰 API를 호출해 실행 중 시뮬레이션의 에이전트를 인터뷰합니다.
Twitter/Reddit 플랫폼 맥락을 반영한 답변을 수집할 수 있습니다.

주요 기능:
1. 시뮬레이션 에이전트 목록 확인
2. 인터뷰 대상 및 주제 선정(행동, 인식, 감정, 전략 등)
3. 인터뷰 질문 생성
4. `/api/simulation/interview/batch` API 호출
5. 인터뷰 응답 분석 및 보고서 반영

적합한 사용 상황:
- "왜 그렇게 행동했는가?" 같은 동기 분석이 필요할 때
- 플랫폼별 반응 차이를 비교할 때
- 보고서에 인터뷰 기반 근거를 추가할 때

반환 결과:
- 인터뷰 대상 에이전트 정보
- 플랫폼별 인터뷰 응답
- 핵심 인사이트(직접 인용 포함)
- 인터뷰 결과 요약

주의: OASIS 시뮬레이션이 실행 중일 때만 사용 가능합니다.
"""

# ── 보고서 개요 생성 프롬프트 ──

PLAN_SYSTEM_PROMPT = get_prompt("report_agent.plan.system")
PLAN_USER_PROMPT_TEMPLATE = get_prompt("report_agent.plan.user")

SECTION_SYSTEM_PROMPT_TEMPLATE = get_prompt("report_agent.section.system")
SECTION_USER_PROMPT_TEMPLATE = get_prompt("report_agent.section.user")

REACT_OBSERVATION_TEMPLATE = get_prompt("report_agent.react.observation")
REACT_INSUFFICIENT_TOOLS_MSG = get_prompt("report_agent.react.insufficient_tools_msg")
REACT_INSUFFICIENT_TOOLS_MSG_ALT = get_prompt("report_agent.react.insufficient_tools_msg_alt")
REACT_TOOL_LIMIT_MSG = get_prompt("report_agent.react.tool_limit_msg")
REACT_UNUSED_TOOLS_HINT = get_prompt("report_agent.react.unused_tools_hint")
REACT_FORCE_FINAL_MSG = get_prompt("report_agent.react.force_final_msg")

CHAT_SYSTEM_PROMPT_TEMPLATE = get_prompt("report_agent.chat.system")
CHAT_OBSERVATION_SUFFIX = "\n\n" + get_prompt("report_agent.chat.observation_suffix_text")


# ═══════════════════════════════════════════════════════════════
# ReportAgent 
# ═══════════════════════════════════════════════════════════════


class ReportAgent:
    """
    시뮬레이션 보고서를 생성하는 에이전트.

    ReACT(Reasoning + Acting):
    1. 분석: 시뮬레이션 데이터와 보고서 맥락을 해석
    2. 실행: 도구를 호출해 근거를 수집
    3. 작성: 섹션별 최종 본문 생성
    """
    
    # 도구 호출(섹션)
    MAX_TOOL_CALLS_PER_SECTION = 5
    
    # 리플렉션 최대 횟수
    MAX_REFLECTION_ROUNDS = 3
    
    # 채팅 응답당 도구 호출 한도
    MAX_TOOL_CALLS_PER_CHAT = 2
    
    def __init__(
        self, 
        graph_id: str,
        simulation_id: str,
        simulation_requirement: str,
        llm_client: Optional[LLMClient] = None,
        zep_tools: Optional[ZepToolsService] = None
    ):
        """
        ReportAgent를 초기화한다.
        
        Args:
            graph_id: 그래프 ID
            simulation_id: 시뮬레이션 ID
            simulation_requirement: 시뮬레이션 요구사항
            llm_client: LLM 클라이언트(선택)
            zep_tools: Zep 도구 서비스(선택)
        """
        self.graph_id = graph_id
        self.simulation_id = simulation_id
        self.simulation_requirement = simulation_requirement
        
        self.llm = llm_client or LLMClient()
        self.zep_tools = zep_tools or ZepToolsService()
        
        # 사용 가능한 도구 정의
        self.tools = self._define_tools()
        
        # 리포트 생성 로그 핸들러
        self.report_logger: Optional[ReportLogger] = None
        # 콘솔 출력 로그 핸들러
        self.console_logger: Optional[ReportConsoleLogger] = None
        
        logger.info(f"ReportAgent 완료: graph_id={graph_id}, simulation_id={simulation_id}")
    
    def _define_tools(self) -> Dict[str, Dict[str, Any]]:
        """에이전트가 사용할 도구 메타데이터를 정의한다."""
        return {
            "insight_forge": {
                "name": "insight_forge",
                "description": TOOL_DESC_INSIGHT_FORGE,
                "parameters": {
                    "query": "분석할 질문",
                    "report_context": "현재 보고서 섹션 맥락(선택)"
                }
            },
            "panorama_search": {
                "name": "panorama_search",
                "description": TOOL_DESC_PANORAMA_SEARCH,
                "parameters": {
                    "query": "검색 질의",
                    "include_expired": "만료/과거 사실 포함 여부(True/False)"
                }
            },
            "quick_search": {
                "name": "quick_search",
                "description": TOOL_DESC_QUICK_SEARCH,
                "parameters": {
                    "query": "검색 질의",
                    "limit": "반환 개수(선택, 기본 10)"
                }
            },
            "interview_agents": {
                "name": "interview_agents",
                "description": TOOL_DESC_INTERVIEW_AGENTS,
                "parameters": {
                    "interview_topic": "인터뷰 주제",
                    "max_agents": "인터뷰 에이전트 수(선택, 기본 5, 최대 10)"
                }
            }
        }
    
    def _execute_tool(self, tool_name: str, parameters: Dict[str, Any], report_context: str = "") -> str:
        """
        지정한 도구를 실행한다.
        
        Args:
            tool_name: 도구 이름
            parameters: 도구 파라미터
            report_context: 현재 보고서 맥락(InsightForge용)
            
        Returns:
            도구 실행 결과 텍스트
        """
        logger.info(f"도구: {tool_name}, 파라미터: {parameters}")
        
        try:
            if tool_name == "insight_forge":
                query = parameters.get("query", "")
                ctx = parameters.get("report_context", "") or report_context
                result = self.zep_tools.insight_forge(
                    graph_id=self.graph_id,
                    query=query,
                    simulation_requirement=self.simulation_requirement,
                    report_context=ctx
                )
                return result.to_text()
            
            elif tool_name == "panorama_search":
                # 전역 검색
                query = parameters.get("query", "")
                include_expired = parameters.get("include_expired", True)
                if isinstance(include_expired, str):
                    include_expired = include_expired.lower() in ['true', '1', 'yes']
                result = self.zep_tools.panorama_search(
                    graph_id=self.graph_id,
                    query=query,
                    include_expired=include_expired
                )
                return result.to_text()
            
            elif tool_name == "quick_search":
                # 빠른 검색
                query = parameters.get("query", "")
                limit = parameters.get("limit", 10)
                if isinstance(limit, str):
                    limit = int(limit)
                result = self.zep_tools.quick_search(
                    graph_id=self.graph_id,
                    query=query,
                    limit=limit
                )
                return result.to_text()
            
            elif tool_name == "interview_agents":
                # OASIS 인터뷰 API 호출
                interview_topic = parameters.get("interview_topic", parameters.get("query", ""))
                max_agents = parameters.get("max_agents", 5)
                if isinstance(max_agents, str):
                    max_agents = int(max_agents)
                max_agents = min(max_agents, 10)
                result = self.zep_tools.interview_agents(
                    simulation_id=self.simulation_id,
                    interview_requirement=interview_topic,
                    simulation_requirement=self.simulation_requirement,
                    max_agents=max_agents
                )
                return result.to_text()
            
            # ========== 호환용 별칭 도구 ==========
            
            elif tool_name == "search_graph":
                #  quick_search
                logger.info("search_graph  quick_search")
                return self._execute_tool("quick_search", parameters, report_context)
            
            elif tool_name == "get_graph_statistics":
                result = self.zep_tools.get_graph_statistics(self.graph_id)
                return json.dumps(result, ensure_ascii=False, indent=2)
            
            elif tool_name == "get_entity_summary":
                entity_name = parameters.get("entity_name", "")
                result = self.zep_tools.get_entity_summary(
                    graph_id=self.graph_id,
                    entity_name=entity_name
                )
                return json.dumps(result, ensure_ascii=False, indent=2)
            
            elif tool_name == "get_simulation_context":
                #  insight_forge, 
                logger.info("get_simulation_context  insight_forge")
                query = parameters.get("query", self.simulation_requirement)
                return self._execute_tool("insight_forge", {"query": query}, report_context)
            
            elif tool_name == "get_entities_by_type":
                entity_type = parameters.get("entity_type", "")
                nodes = self.zep_tools.get_entities_by_type(
                    graph_id=self.graph_id,
                    entity_type=entity_type
                )
                result = [n.to_dict() for n in nodes]
                return json.dumps(result, ensure_ascii=False, indent=2)
            
            else:
                return f"도구: {tool_name}.도구: insight_forge, panorama_search, quick_search"
                
        except Exception as e:
            logger.error(f"도구실패: {tool_name}, 오류: {str(e)}")
            return f"도구실패: {str(e)}"
    
    # 도구,  JSON 
    VALID_TOOL_NAMES = {"insight_forge", "panorama_search", "quick_search", "interview_agents"}

    def _parse_tool_calls(self, response: str) -> List[Dict[str, Any]]:
        """
        LLM도구호출

        ():
        1. <tool_call>{"name": "tool_name", "parameters": {...}}</tool_call>
        2.  JSON(도구 호출 JSON)
        """
        tool_calls = []

        # 1: XML()
        xml_pattern = r'<tool_call>\s*(\{.*?\})\s*</tool_call>'
        for match in re.finditer(xml_pattern, response, re.DOTALL):
            try:
                call_data = json.loads(match.group(1))
                tool_calls.append(call_data)
            except json.JSONDecodeError:
                pass

        if tool_calls:
            return tool_calls

        # 2:  - LLM  JSON( <tool_call> )
        # 1, JSON
        stripped = response.strip()
        if stripped.startswith('{') and stripped.endswith('}'):
            try:
                call_data = json.loads(stripped)
                if self._is_valid_tool_call(call_data):
                    tool_calls.append(call_data)
                    return tool_calls
            except json.JSONDecodeError:
                pass

        #  +  JSON,  JSON 
        json_pattern = r'(\{"(?:name|tool)"\s*:.*?\})\s*$'
        match = re.search(json_pattern, stripped, re.DOTALL)
        if match:
            try:
                call_data = json.loads(match.group(1))
                if self._is_valid_tool_call(call_data):
                    tool_calls.append(call_data)
            except json.JSONDecodeError:
                pass

        return tool_calls

    def _is_valid_tool_call(self, data: dict) -> bool:
        """ JSON 도구 호출"""
        #  {"name": ..., "parameters": ...}  {"tool": ..., "params": ...} 
        tool_name = data.get("name") or data.get("tool")
        if tool_name and tool_name in self.VALID_TOOL_NAMES:
            #  name / parameters
            if "tool" in data:
                data["name"] = data.pop("tool")
            if "params" in data and "parameters" not in data:
                data["parameters"] = data.pop("params")
            return True
        return False
    
    def _get_tools_description(self) -> str:
        """생성도구"""
        desc_parts = ["도구:"]
        for name, tool in self.tools.items():
            params_desc = ", ".join([f"{k}: {v}" for k, v in tool["parameters"].items()])
            desc_parts.append(f"- {name}: {tool['description']}")
            if params_desc:
                desc_parts.append(f"  파라미터: {params_desc}")
        return "\n".join(desc_parts)
    
    def plan_outline(
        self, 
        progress_callback: Optional[Callable] = None
    ) -> ReportOutline:
        """
        보고서
        
        LLM분석시뮬레이션, 보고서디렉터리
        
        Args:
            progress_callback: 진행률
            
        Returns:
            ReportOutline: 보고서
        """
        logger.info("시작보고서...")
        
        if progress_callback:
            progress_callback("planning", 0, "진행 중분석시뮬레이션...")
        
        # 시뮬레이션
        context = self.zep_tools.get_simulation_context(
            graph_id=self.graph_id,
            simulation_requirement=self.simulation_requirement
        )
        
        if progress_callback:
            progress_callback("planning", 30, "진행 중생성보고서...")
        
        system_prompt = PLAN_SYSTEM_PROMPT
        user_prompt = PLAN_USER_PROMPT_TEMPLATE.format(
            simulation_requirement=self.simulation_requirement,
            total_nodes=context.get('graph_statistics', {}).get('total_nodes', 0),
            total_edges=context.get('graph_statistics', {}).get('total_edges', 0),
            entity_types=list(context.get('graph_statistics', {}).get('entity_types', {}).keys()),
            total_entities=context.get('total_entities', 0),
            related_facts_json=json.dumps(context.get('related_facts', [])[:10], ensure_ascii=False, indent=2),
        )

        try:
            response = self.llm.chat_json(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.3
            )
            
            if progress_callback:
                progress_callback("planning", 80, "진행 진행 중")
            
            # 
            sections = []
            for section_data in response.get("sections", []):
                sections.append(ReportSection(
                    title=section_data.get("title", ""),
                    content=""
                ))
            
            outline = ReportOutline(
                title=response.get("title", "시뮬레이션분석보고서"),
                summary=response.get("summary", ""),
                sections=sections
            )
            
            if progress_callback:
                progress_callback("planning", 100, "완료")
            
            logger.info(f"완료: {len(sections)}개섹션")
            return outline
            
        except Exception as e:
            logger.error(f"실패: {str(e)}")
            # 반환(3섹션, fallback)
            return ReportOutline(
                title="보고서",
                summary="시뮬레이션분석",
                sections=[
                    ReportSection(title=""),
                    ReportSection(title="분석"),
                    ReportSection(title="")
                ]
            )
    
    def _generate_section_react(
        self, 
        section: ReportSection,
        outline: ReportOutline,
        previous_sections: List[str],
        progress_callback: Optional[Callable] = None,
        section_index: int = 0
    ) -> str:
        """
        ReACT생성섹션
        
        ReACT:
        1. Thought()- 분석정보
        2. Action()- 도구 호출정보
        3. Observation()- 분석도구반환
        4. 정보
        5. Final Answer()- 생성섹션
        
        Args:
            section: 생성섹션
            outline: 
            previous_sections: 섹션()
            progress_callback: 진행률
            section_index: 섹션(로그)
            
        Returns:
            섹션(Markdown)
        """
        logger.info(f"ReACT생성섹션: {section.title}")
        
        # 섹션시작로그
        if self.report_logger:
            self.report_logger.log_section_start(section.title, section_index)
        
        system_prompt = SECTION_SYSTEM_PROMPT_TEMPLATE.format(
            report_title=outline.title,
            report_summary=outline.summary,
            simulation_requirement=self.simulation_requirement,
            section_title=section.title,
            tools_description=self._get_tools_description(),
        )

        # prompt - 완료섹션4000
        if previous_sections:
            previous_parts = []
            for sec in previous_sections:
                # 섹션4000
                truncated = sec[:4000] + "..." if len(sec) > 4000 else sec
                previous_parts.append(truncated)
            previous_content = "\n\n---\n\n".join(previous_parts)
        else:
            previous_content = "(이전에 작성된 섹션 없음)"
        
        user_prompt = SECTION_USER_PROMPT_TEMPLATE.format(
            previous_content=previous_content,
            section_title=section.title,
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        
        # ReACT
        tool_calls_count = 0
        max_iterations = 5  # 
        min_tool_calls = 3  # 도구 호출
        conflict_retries = 0  # 도구 호출Final Answer
        used_tools = set()  # 도구 호출
        all_tools = {"insight_forge", "panorama_search", "quick_search", "interview_agents"}

        # 보고서, InsightForge질문생성
        report_context = f"섹션: {section.title}\n시뮬레이션: {self.simulation_requirement}"
        
        for iteration in range(max_iterations):
            if progress_callback:
                progress_callback(
                    "generating", 
                    int((iteration / max_iterations) * 100),
                    f"섹션 생성 진행 중 (도구 호출 {tool_calls_count}/{self.MAX_TOOL_CALLS_PER_SECTION})"
                )
            
            # 호출LLM
            response = self.llm.chat(
                messages=messages,
                temperature=0.5,
                max_tokens=4096
            )

            #  LLM 반환 None(API )
            if response is None:
                logger.warning(f"섹션 {section.title}  {iteration + 1}회: LLM 반환 None")
                # , 
                if iteration < max_iterations - 1:
                    messages.append({"role": "assistant", "content": "(응답 생성 실패) 다시 시도합니다."})
                    messages.append({"role": "user", "content": "이전 지침을 유지한 채 섹션을 다시 작성해 주세요."})
                    continue
                # 반환 None, 
                break

            logger.debug(f"LLM: {response[:200]}...")

            # , 
            tool_calls = self._parse_tool_calls(response)
            has_tool_calls = bool(tool_calls)
            has_final_answer = "Final Answer:" in response

            # ── :LLM 도구 호출 Final Answer ──
            if has_tool_calls and has_final_answer:
                conflict_retries += 1
                logger.warning(
                    f"섹션 {section.title}  {iteration+1} : "
                    f"LLM 도구 호출 Final Answer( {conflict_retries}회)"
                )

                if conflict_retries <= 2:
                    # :,  LLM 
                    messages.append({"role": "assistant", "content": response})
                    messages.append({
                        "role": "user",
                        "content": (
                            "[오류]진행 중도구 호출 Final Answer, .\n"
                            ":\n"
                            "- 도구 호출( <tool_call> ,  Final Answer)\n"
                            "- ( 'Final Answer:' ,  <tool_call>)\n"
                            ", 진행 중."
                        ),
                    })
                    continue
                else:
                    # :, 도구 호출, 
                    logger.warning(
                        f"섹션 {section.title}:  {conflict_retries}회, "
                        "도구 호출"
                    )
                    first_tool_end = response.find('</tool_call>')
                    if first_tool_end != -1:
                        response = response[:first_tool_end + len('</tool_call>')]
                        tool_calls = self._parse_tool_calls(response)
                        has_tool_calls = bool(tool_calls)
                    has_final_answer = False
                    conflict_retries = 0

            #  LLM 로그
            if self.report_logger:
                self.report_logger.log_llm_response(
                    section_title=section.title,
                    section_index=section_index,
                    response=response,
                    iteration=iteration + 1,
                    has_tool_calls=has_tool_calls,
                    has_final_answer=has_final_answer
                )

            # ── 1:LLM  Final Answer ──
            if has_final_answer:
                # 도구 호출, 도구
                if tool_calls_count < min_tool_calls:
                    messages.append({"role": "assistant", "content": response})
                    unused_tools = all_tools - used_tools
                    unused_hint = f"(도구, : {', '.join(unused_tools)})" if unused_tools else ""
                    messages.append({
                        "role": "user",
                        "content": REACT_INSUFFICIENT_TOOLS_MSG.format(
                            tool_calls_count=tool_calls_count,
                            min_tool_calls=min_tool_calls,
                            unused_hint=unused_hint,
                        ),
                    })
                    continue

                # 
                final_answer = response.split("Final Answer:")[-1].strip()
                logger.info(f"섹션 {section.title} 생성완료(도구 호출: {tool_calls_count})")

                if self.report_logger:
                    self.report_logger.log_section_content(
                        section_title=section.title,
                        section_index=section_index,
                        content=final_answer,
                        tool_calls_count=tool_calls_count
                    )
                return final_answer

            # ── 2:LLM 도구 호출 ──
            if has_tool_calls:
                # 도구 → ,  Final Answer
                if tool_calls_count >= self.MAX_TOOL_CALLS_PER_SECTION:
                    messages.append({"role": "assistant", "content": response})
                    messages.append({
                        "role": "user",
                        "content": REACT_TOOL_LIMIT_MSG.format(
                            tool_calls_count=tool_calls_count,
                            max_tool_calls=self.MAX_TOOL_CALLS_PER_SECTION,
                        ),
                    })
                    continue

                # 도구 호출
                call = tool_calls[0]
                if len(tool_calls) > 1:
                    logger.info(f"LLM 호출 {len(tool_calls)}개도구, : {call['name']}")

                if self.report_logger:
                    self.report_logger.log_tool_call(
                        section_title=section.title,
                        section_index=section_index,
                        tool_name=call["name"],
                        parameters=call.get("parameters", {}),
                        iteration=iteration + 1
                    )

                result = self._execute_tool(
                    call["name"],
                    call.get("parameters", {}),
                    report_context=report_context
                )

                if self.report_logger:
                    self.report_logger.log_tool_result(
                        section_title=section.title,
                        section_index=section_index,
                        tool_name=call["name"],
                        result=result,
                        iteration=iteration + 1
                    )

                tool_calls_count += 1
                used_tools.add(call['name'])

                # 도구
                unused_tools = all_tools - used_tools
                unused_hint = ""
                if unused_tools and tool_calls_count < self.MAX_TOOL_CALLS_PER_SECTION:
                    unused_hint = REACT_UNUSED_TOOLS_HINT.format(unused_list=", ".join(unused_tools))

                messages.append({"role": "assistant", "content": response})
                messages.append({
                    "role": "user",
                    "content": REACT_OBSERVATION_TEMPLATE.format(
                        tool_name=call["name"],
                        result=result,
                        tool_calls_count=tool_calls_count,
                        max_tool_calls=self.MAX_TOOL_CALLS_PER_SECTION,
                        used_tools_str=", ".join(used_tools),
                        unused_hint=unused_hint,
                    ),
                })
                continue

            # ── 3:도구 호출,  Final Answer ──
            messages.append({"role": "assistant", "content": response})

            if tool_calls_count < min_tool_calls:
                # 도구 호출, 도구
                unused_tools = all_tools - used_tools
                unused_hint = f"(도구, : {', '.join(unused_tools)})" if unused_tools else ""

                messages.append({
                    "role": "user",
                    "content": REACT_INSUFFICIENT_TOOLS_MSG_ALT.format(
                        tool_calls_count=tool_calls_count,
                        min_tool_calls=min_tool_calls,
                        unused_hint=unused_hint,
                    ),
                })
                continue

            # 도구 호출, LLM  "Final Answer:" 
            # , 
            logger.info(f"섹션 {section.title}  'Final Answer:' , LLM(도구 호출: {tool_calls_count})")
            final_answer = response.strip()

            if self.report_logger:
                self.report_logger.log_section_content(
                    section_title=section.title,
                    section_index=section_index,
                    content=final_answer,
                    tool_calls_count=tool_calls_count
                )
            return final_answer
        
        # , 생성
        logger.warning(f"섹션 {section.title} , 생성")
        messages.append({"role": "user", "content": REACT_FORCE_FINAL_MSG})
        
        response = self.llm.chat(
            messages=messages,
            temperature=0.5,
            max_tokens=4096
        )

        #  LLM 반환 None
        if response is None:
            logger.error(f"섹션 {section.title}  LLM 반환 None, 오류")
            final_answer = f"(섹션생성 실패:LLM 반환, )"
        elif "Final Answer:" in response:
            final_answer = response.split("Final Answer:")[-1].strip()
        else:
            final_answer = response
        
        # 섹션생성완료로그
        if self.report_logger:
            self.report_logger.log_section_content(
                section_title=section.title,
                section_index=section_index,
                content=final_answer,
                tool_calls_count=tool_calls_count
            )
        
        return final_answer
    
    def generate_report(
        self, 
        progress_callback: Optional[Callable[[str, int, str], None]] = None,
        report_id: Optional[str] = None
    ) -> Report:
        """
        생성보고서(섹션)
        
        섹션생성완료저장파일, 보고서완료.
        파일:
        reports/{report_id}/
            meta.json       - 보고서정보
            outline.json    - 보고서
            progress.json   - 생성진행률
            section_01.md   - 1섹션
            section_02.md   - 2섹션
            ...
            full_report.md  - 보고서
        
        Args:
            progress_callback: 진행률 (stage, progress, message)
            report_id: 보고서ID(선택, 생성)
            
        Returns:
            Report: 보고서
        """
        import uuid
        
        #  report_id, 생성
        if not report_id:
            report_id = f"report_{uuid.uuid4().hex[:12]}"
        start_time = datetime.now()
        
        report = Report(
            report_id=report_id,
            simulation_id=self.simulation_id,
            graph_id=self.graph_id,
            simulation_requirement=self.simulation_requirement,
            status=ReportStatus.PENDING,
            created_at=datetime.now().isoformat()
        )
        
        # 완료섹션목록(진행률)
        completed_section_titles = []
        
        try:
            # :보고서파일저장상태
            ReportManager._ensure_report_folder(report_id)
            
            # 로그(로그 agent_log.jsonl)
            self.report_logger = ReportLogger(report_id)
            self.report_logger.log_start(
                simulation_id=self.simulation_id,
                graph_id=self.graph_id,
                simulation_requirement=self.simulation_requirement
            )
            
            # 콘솔로그(console_log.txt)
            self.console_logger = ReportConsoleLogger(report_id)
            
            ReportManager.update_progress(
                report_id, "pending", 0, "보고서...",
                completed_sections=[]
            )
            ReportManager.save_report(report)
            
            # 1: 
            report.status = ReportStatus.PLANNING
            ReportManager.update_progress(
                report_id, "planning", 5, "시작보고서...",
                completed_sections=[]
            )
            
            # 시작로그
            self.report_logger.log_planning_start()
            
            if progress_callback:
                progress_callback("planning", 0, "시작보고서...")
            
            outline = self.plan_outline(
                progress_callback=lambda stage, prog, msg: 
                    progress_callback(stage, prog // 5, msg) if progress_callback else None
            )
            report.outline = outline
            
            # 완료로그
            self.report_logger.log_planning_complete(outline.to_dict())
            
            # 저장파일
            ReportManager.save_outline(report_id, outline)
            ReportManager.update_progress(
                report_id, "planning", 15, f"완료, {len(outline.sections)}섹션",
                completed_sections=[]
            )
            ReportManager.save_report(report)
            
            logger.info(f"저장파일: {report_id}/outline.json")
            
            # 2: 섹션생성(섹션저장)
            report.status = ReportStatus.GENERATING
            
            total_sections = len(outline.sections)
            generated_sections = []  # 저장
            
            for i, section in enumerate(outline.sections):
                section_num = i + 1
                base_progress = 20 + int((i / total_sections) * 70)
                
                # 진행률
                ReportManager.update_progress(
                    report_id, "generating", base_progress,
                    f"진행 중생성섹션: {section.title} ({section_num}/{total_sections})",
                    current_section=section.title,
                    completed_sections=completed_section_titles
                )
                
                if progress_callback:
                    progress_callback(
                        "generating", 
                        base_progress, 
                        f"진행 중생성섹션: {section.title} ({section_num}/{total_sections})"
                    )
                
                # 생성섹션
                section_content = self._generate_section_react(
                    section=section,
                    outline=outline,
                    previous_sections=generated_sections,
                    progress_callback=lambda stage, prog, msg:
                        progress_callback(
                            stage, 
                            base_progress + int(prog * 0.7 / total_sections),
                            msg
                        ) if progress_callback else None,
                    section_index=section_num
                )
                
                section.content = section_content
                generated_sections.append(f"## {section.title}\n\n{section_content}")

                # 저장섹션
                ReportManager.save_section(report_id, section_num, section)
                completed_section_titles.append(section.title)

                # 섹션완료로그
                full_section_content = f"## {section.title}\n\n{section_content}"

                if self.report_logger:
                    self.report_logger.log_section_full_complete(
                        section_title=section.title,
                        section_index=section_num,
                        full_content=full_section_content.strip()
                    )

                logger.info(f"섹션저장: {report_id}/section_{section_num:02d}.md")
                
                # 진행률
                ReportManager.update_progress(
                    report_id, "generating", 
                    base_progress + int(70 / total_sections),
                    f"섹션 {section.title} 완료",
                    current_section=None,
                    completed_sections=completed_section_titles
                )
            
            # 3: 보고서
            if progress_callback:
                progress_callback("generating", 95, "진행 중보고서...")
            
            ReportManager.update_progress(
                report_id, "generating", 95, "진행 중보고서...",
                completed_sections=completed_section_titles
            )
            
            # ReportManager보고서
            report.markdown_content = ReportManager.assemble_full_report(report_id, outline)
            report.status = ReportStatus.COMPLETED
            report.completed_at = datetime.now().isoformat()
            
            # 
            total_time_seconds = (datetime.now() - start_time).total_seconds()
            
            # 보고서완료로그
            if self.report_logger:
                self.report_logger.log_report_complete(
                    total_sections=total_sections,
                    total_time_seconds=total_time_seconds
                )
            
            # 저장보고서
            ReportManager.save_report(report)
            ReportManager.update_progress(
                report_id, "completed", 100, "보고서 생성완료",
                completed_sections=completed_section_titles
            )
            
            if progress_callback:
                progress_callback("completed", 100, "보고서 생성완료")
            
            logger.info(f"보고서 생성완료: {report_id}")
            
            # 콘솔로그
            if self.console_logger:
                self.console_logger.close()
                self.console_logger = None
            
            return report
            
        except Exception as e:
            logger.error(f"보고서 생성 실패: {str(e)}")
            report.status = ReportStatus.FAILED
            report.error = str(e)
            
            # 오류로그
            if self.report_logger:
                self.report_logger.log_error(str(e), "failed")
            
            # 저장실패상태
            try:
                ReportManager.save_report(report)
                ReportManager.update_progress(
                    report_id, "failed", -1, f"보고서 생성 실패: {str(e)}",
                    completed_sections=completed_section_titles
                )
            except Exception:
                pass  # 저장실패오류
            
            # 콘솔로그
            if self.console_logger:
                self.console_logger.close()
                self.console_logger = None
            
            return report
    
    def chat(
        self, 
        message: str,
        chat_history: List[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """
        Report Agent
        
        에이전트도구 호출질문
        
        Args:
            message: 
            chat_history: 과거
            
        Returns:
            {
                "response": "Agent",
                "tool_calls": [도구 호출목록],
                "sources": [정보출처]
            }
        """
        logger.info(f"Report Agent: {message[:50]}...")
        
        chat_history = chat_history or []
        
        # 생성보고서
        report_content = ""
        try:
            report = ReportManager.get_report_by_simulation(self.simulation_id)
            if report and report.markdown_content:
                # 보고서, 
                report_content = report.markdown_content[:15000]
                if len(report.markdown_content) > 15000:
                    report_content += "\n\n... [보고서] ..."
        except Exception as e:
            logger.warning(f"보고서실패: {e}")
        
        system_prompt = CHAT_SYSTEM_PROMPT_TEMPLATE.format(
            simulation_requirement=self.simulation_requirement,
            report_content=report_content if report_content else "(보고서)",
            tools_description=self._get_tools_description(),
        )

        # 
        messages = [{"role": "system", "content": system_prompt}]
        
        # 과거
        for h in chat_history[-10:]:  # 과거
            messages.append(h)
        
        # 
        messages.append({
            "role": "user", 
            "content": message
        })
        
        # ReACT()
        tool_calls_made = []
        max_iterations = 2  # 
        
        for iteration in range(max_iterations):
            response = self.llm.chat(
                messages=messages,
                temperature=0.5
            )
            
            # 도구 호출
            tool_calls = self._parse_tool_calls(response)
            
            if not tool_calls:
                # 도구 호출, 반환
                clean_response = re.sub(r'<tool_call>.*?</tool_call>', '', response, flags=re.DOTALL)
                clean_response = re.sub(r'\[TOOL_CALL\].*?\)', '', clean_response)
                
                return {
                    "response": clean_response.strip(),
                    "tool_calls": tool_calls_made,
                    "sources": [tc.get("parameters", {}).get("query", "") for tc in tool_calls_made]
                }
            
            # 도구 호출()
            tool_results = []
            for call in tool_calls[:1]:  # 1도구 호출
                if len(tool_calls_made) >= self.MAX_TOOL_CALLS_PER_CHAT:
                    break
                result = self._execute_tool(call["name"], call.get("parameters", {}))
                tool_results.append({
                    "tool": call["name"],
                    "result": result[:1500]  # 
                })
                tool_calls_made.append(call)
            
            # 
            messages.append({"role": "assistant", "content": response})
            observation = "\n".join([f"[{r['tool']}]\n{r['result']}" for r in tool_results])
            messages.append({
                "role": "user",
                "content": observation + CHAT_OBSERVATION_SUFFIX
            })
        
        # , 
        final_response = self.llm.chat(
            messages=messages,
            temperature=0.5
        )
        
        # 
        clean_response = re.sub(r'<tool_call>.*?</tool_call>', '', final_response, flags=re.DOTALL)
        clean_response = re.sub(r'\[TOOL_CALL\].*?\)', '', clean_response)
        
        return {
            "response": clean_response.strip(),
            "tool_calls": tool_calls_made,
            "sources": [tc.get("parameters", {}).get("query", "") for tc in tool_calls_made]
        }



