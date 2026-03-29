import json
import logging
import os
from datetime import datetime
from typing import Any, Dict, Optional

from ...config import Config


class ReportLogger:
    """Persist detailed report-agent events as JSONL."""

    def __init__(self, report_id: str):
        self.report_id = report_id
        self.log_file_path = os.path.join(
            Config.UPLOAD_FOLDER, "reports", report_id, "agent_log.jsonl"
        )
        self.start_time = datetime.now()
        self._ensure_log_file()

    def _ensure_log_file(self) -> None:
        os.makedirs(os.path.dirname(self.log_file_path), exist_ok=True)

    def _get_elapsed_time(self) -> float:
        return (datetime.now() - self.start_time).total_seconds()

    def log(
        self,
        action: str,
        stage: str,
        details: Dict[str, Any],
        section_title: Optional[str] = None,
        section_index: Optional[int] = None,
    ) -> None:
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "elapsed_seconds": round(self._get_elapsed_time(), 2),
            "report_id": self.report_id,
            "action": action,
            "stage": stage,
            "section_title": section_title,
            "section_index": section_index,
            "details": details,
        }

        with open(self.log_file_path, "a", encoding="utf-8") as file:
            file.write(json.dumps(log_entry, ensure_ascii=False) + "\n")

    def log_start(self, simulation_id: str, graph_id: str, simulation_requirement: str) -> None:
        self.log(
            action="report_start",
            stage="pending",
            details={
                "simulation_id": simulation_id,
                "graph_id": graph_id,
                "simulation_requirement": simulation_requirement,
                "message": "보고서 생성작업 시작",
            },
        )

    def log_planning_start(self) -> None:
        self.log(
            action="planning_start",
            stage="planning",
            details={"message": "시작보고서"},
        )

    def log_planning_context(self, context: Dict[str, Any]) -> None:
        self.log(
            action="planning_context",
            stage="planning",
            details={"message": "시뮬레이션정보", "context": context},
        )

    def log_planning_complete(self, outline_dict: Dict[str, Any]) -> None:
        self.log(
            action="planning_complete",
            stage="planning",
            details={"message": "완료", "outline": outline_dict},
        )

    def log_section_start(self, section_title: str, section_index: int) -> None:
        self.log(
            action="section_start",
            stage="generating",
            section_title=section_title,
            section_index=section_index,
            details={"message": f"시작생성섹션: {section_title}"},
        )

    def log_react_thought(
        self, section_title: str, section_index: int, iteration: int, thought: str
    ) -> None:
        self.log(
            action="react_thought",
            stage="generating",
            section_title=section_title,
            section_index=section_index,
            details={
                "iteration": iteration,
                "thought": thought,
                "message": f"ReACT {iteration}",
            },
        )

    def log_tool_call(
        self,
        section_title: str,
        section_index: int,
        tool_name: str,
        parameters: Dict[str, Any],
        iteration: int,
    ) -> None:
        self.log(
            action="tool_call",
            stage="generating",
            section_title=section_title,
            section_index=section_index,
            details={
                "iteration": iteration,
                "tool_name": tool_name,
                "parameters": parameters,
                "message": f"도구 호출: {tool_name}",
            },
        )

    def log_tool_result(
        self,
        section_title: str,
        section_index: int,
        tool_name: str,
        result: str,
        iteration: int,
    ) -> None:
        self.log(
            action="tool_result",
            stage="generating",
            section_title=section_title,
            section_index=section_index,
            details={
                "iteration": iteration,
                "tool_name": tool_name,
                "result": result,
                "result_length": len(result),
                "message": f"도구 {tool_name} 반환",
            },
        )

    def log_llm_response(
        self,
        section_title: str,
        section_index: int,
        response: str,
        iteration: int,
        has_tool_calls: bool,
        has_final_answer: bool,
    ) -> None:
        self.log(
            action="llm_response",
            stage="generating",
            section_title=section_title,
            section_index=section_index,
            details={
                "iteration": iteration,
                "response": response,
                "response_length": len(response),
                "has_tool_calls": has_tool_calls,
                "has_final_answer": has_final_answer,
                "message": f"LLM 응답 (도구 호출: {has_tool_calls}, 완료: {has_final_answer})",
            },
        )

    def log_section_content(
        self,
        section_title: str,
        section_index: int,
        content: str,
        tool_calls_count: int,
    ) -> None:
        self.log(
            action="section_content",
            stage="generating",
            section_title=section_title,
            section_index=section_index,
            details={
                "content": content,
                "content_length": len(content),
                "tool_calls_count": tool_calls_count,
                "message": f"섹션 {section_title} 생성완료",
            },
        )

    def log_section_full_complete(
        self, section_title: str, section_index: int, full_content: str
    ) -> None:
        self.log(
            action="section_complete",
            stage="generating",
            section_title=section_title,
            section_index=section_index,
            details={
                "content": full_content,
                "content_length": len(full_content),
                "message": f"섹션 {section_title} 생성완료",
            },
        )

    def log_report_complete(self, total_sections: int, total_time_seconds: float) -> None:
        self.log(
            action="report_complete",
            stage="completed",
            details={
                "total_sections": total_sections,
                "total_time_seconds": round(total_time_seconds, 2),
                "message": "보고서 생성완료",
            },
        )

    def log_error(
        self, error_message: str, stage: str, section_title: Optional[str] = None
    ) -> None:
        self.log(
            action="error",
            stage=stage,
            section_title=section_title,
            section_index=None,
            details={"error": error_message, "message": f"오류: {error_message}"},
        )


class ReportConsoleLogger:
    """Attach a file handler for report-agent console logs."""

    def __init__(self, report_id: str):
        self.report_id = report_id
        self.log_file_path = os.path.join(
            Config.UPLOAD_FOLDER, "reports", report_id, "console_log.txt"
        )
        self._file_handler: Optional[logging.FileHandler] = None
        self._ensure_log_file()
        self._setup_file_handler()

    def _ensure_log_file(self) -> None:
        os.makedirs(os.path.dirname(self.log_file_path), exist_ok=True)

    def _setup_file_handler(self) -> None:
        self._file_handler = logging.FileHandler(
            self.log_file_path,
            mode="a",
            encoding="utf-8",
        )
        self._file_handler.setLevel(logging.INFO)
        self._file_handler.setFormatter(
            logging.Formatter("[%(asctime)s] %(levelname)s: %(message)s", datefmt="%H:%M:%S")
        )

        for logger_name in ("mirofish.report_agent", "mirofish.zep_tools"):
            target_logger = logging.getLogger(logger_name)
            if self._file_handler not in target_logger.handlers:
                target_logger.addHandler(self._file_handler)

    def close(self) -> None:
        if not self._file_handler:
            return

        for logger_name in ("mirofish.report_agent", "mirofish.zep_tools"):
            target_logger = logging.getLogger(logger_name)
            if self._file_handler in target_logger.handlers:
                target_logger.removeHandler(self._file_handler)

        self._file_handler.close()
        self._file_handler = None

    def __del__(self) -> None:
        self.close()
