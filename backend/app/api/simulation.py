"""
시뮬레이션API라우트
Step2: Zep엔터티읽기, OASIS시뮬레이션 실행()
"""

import os
import traceback
from flask import request, jsonify, send_file

from . import simulation_bp
from ..config import Config
from ..prompts import get_prompt
from ..services.zep_entity_reader import ZepEntityReader
from ..services.oasis_profile_generator import OasisProfileGenerator
from ..services.simulation_manager import SimulationManager, SimulationStatus
from ..services.simulation_runner import SimulationRunner, RunnerStatus
from ..utils.logger import get_logger
from ..models.project import ProjectManager

logger = get_logger('mirofish.api.simulation')


# Interview prompt 
# Agent도구 호출, 
INTERVIEW_PROMPT_PREFIX = get_prompt("simulation.interview_prompt_prefix")


def optimize_interview_prompt(prompt: str) -> str:
    """
    Interview, Agent도구 호출
    
    Args:
        prompt: 
        
    Returns:
        
    """
    if not prompt:
        return prompt
    # 
    if prompt.startswith(INTERVIEW_PROMPT_PREFIX):
        return prompt
    return f"{INTERVIEW_PROMPT_PREFIX}{prompt}"


# ============== 시뮬레이션API ==============

@simulation_bp.route('/create', methods=['POST'])
def create_simulation():
    """
    시뮬레이션
    
    :max_rounds파라미터LLM생성, 
    
    요청(JSON):
        {
            "project_id": "proj_xxxx",      // 필수
            "graph_id": "mirofish_xxxx",    // 선택, project
            "enable_twitter": true,          // 선택, true
            "enable_reddit": true            // 선택, true
        }
    
    반환:
        {
            "success": true,
            "data": {
                "simulation_id": "sim_xxxx",
                "project_id": "proj_xxxx",
                "graph_id": "mirofish_xxxx",
                "status": "created",
                "enable_twitter": true,
                "enable_reddit": true,
                "created_at": "2025-12-01T10:00:00"
            }
        }
    """
    try:
        data = request.get_json() or {}
        
        project_id = data.get('project_id')
        if not project_id:
            return jsonify({
                "success": False,
                "error": "project_id를 입력해 주세요."
            }), 400
        
        project = ProjectManager.get_project(project_id)
        if not project:
            return jsonify({
                "success": False,
                "error": f"프로젝트가 존재하지 않습니다: {project_id}"
            }), 404
        
        graph_id = data.get('graph_id') or project.graph_id
        if not graph_id:
            return jsonify({
                "success": False,
                "error": "프로젝트그래프, 호출 /api/graph/build"
            }), 400
        
        manager = SimulationManager()
        state = manager.create_simulation(
            project_id=project_id,
            graph_id=graph_id,
            enable_twitter=data.get('enable_twitter', True),
            enable_reddit=data.get('enable_reddit', True),
        )
        
        return jsonify({
            "success": True,
            "data": state.to_dict()
        })
        
    except Exception as e:
        logger.error(f"시뮬레이션실패: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


def _check_simulation_prepared(simulation_id: str) -> tuple:
    """
    시뮬레이션 완료
    
    :
    1. state.json  status  "ready"
    2. 파일:reddit_profiles.json, twitter_profiles.csv, simulation_config.json
    
    :실행(run_*.py) backend/scripts/ 디렉터리, 시뮬레이션디렉터리
    
    Args:
        simulation_id: 시뮬레이션 ID
        
    Returns:
        (is_prepared: bool, info: dict)
    """
    import os
    from ..config import Config
    
    simulation_dir = os.path.join(Config.OASIS_SIMULATION_DATA_DIR, simulation_id)
    
    # 디렉터리
    if not os.path.exists(simulation_dir):
        return False, {"reason": "시뮬레이션디렉터리존재하지 않습니다"}
    
    # 파일목록(,  backend/scripts/)
    required_files = [
        "state.json",
        "simulation_config.json",
        "reddit_profiles.json",
        "twitter_profiles.csv"
    ]
    
    # 파일
    existing_files = []
    missing_files = []
    for f in required_files:
        file_path = os.path.join(simulation_dir, f)
        if os.path.exists(file_path):
            existing_files.append(f)
        else:
            missing_files.append(f)
    
    if missing_files:
        return False, {
            "reason": "누락파일",
            "missing_files": missing_files,
            "existing_files": existing_files
        }
    
    # state.json 상태 확인
    state_file = os.path.join(simulation_dir, "state.json")
    try:
        import json
        with open(state_file, 'r', encoding='utf-8') as f:
            state_data = json.load(f)
        
        status = state_data.get("status", "")
        config_generated = state_data.get("config_generated", False)
        
        # 상세로그
        logger.debug(f"시뮬레이션상태: {simulation_id}, status={status}, config_generated={config_generated}")
        
        #  config_generated=True 파일, 완료
        # 상태설명완료:
        # - ready: 완료, 실행
        # - preparing:  config_generated=True 설명완료
        # - running: 실행 중, 설명완료
        # - completed: 실행완료, 설명완료
        # - stopped: 중지, 설명완료
        # - failed: 실행실패(완료)
        prepared_statuses = ["ready", "preparing", "running", "completed", "stopped", "failed"]
        if status in prepared_statuses and config_generated:
            # 파일정보
            profiles_file = os.path.join(simulation_dir, "reddit_profiles.json")
            config_file = os.path.join(simulation_dir, "simulation_config.json")
            
            profiles_count = 0
            if os.path.exists(profiles_file):
                with open(profiles_file, 'r', encoding='utf-8') as f:
                    profiles_data = json.load(f)
                    profiles_count = len(profiles_data) if isinstance(profiles_data, list) else 0
            
            # 상태preparing파일완료, 상태ready
            if status == "preparing":
                try:
                    state_data["status"] = "ready"
                    from datetime import datetime
                    state_data["updated_at"] = datetime.now().isoformat()
                    with open(state_file, 'w', encoding='utf-8') as f:
                        json.dump(state_data, f, ensure_ascii=False, indent=2)
                    logger.info(f"시뮬레이션상태: {simulation_id} preparing -> ready")
                    status = "ready"
                except Exception as e:
                    logger.warning(f"상태실패: {e}")
            
            logger.info(f"시뮬레이션 {simulation_id} : 완료 (status={status}, config_generated={config_generated})")
            return True, {
                "status": status,
                "entities_count": state_data.get("entities_count", 0),
                "profiles_count": profiles_count,
                "entity_types": state_data.get("entity_types", []),
                "config_generated": config_generated,
                "created_at": state_data.get("created_at"),
                "updated_at": state_data.get("updated_at"),
                "existing_files": existing_files
            }
        else:
            logger.warning(f"시뮬레이션 {simulation_id} : 완료 (status={status}, config_generated={config_generated})")
            return False, {
                "reason": f"상태목록config_generatedfalse: status={status}, config_generated={config_generated}",
                "status": status,
                "config_generated": config_generated
            }
            
    except Exception as e:
        return False, {"reason": f"읽기상태파일실패: {str(e)}"}


@simulation_bp.route('/prepare', methods=['POST'])
def prepare_simulation():
    """
    시뮬레이션(작업, LLM생성파라미터)
    
    , API반환task_id, 
     GET /api/simulation/prepare/status 진행률 조회
    
    :
    - 완료, 생성
    - 완료, 반환
    - 생성(force_regenerate=true)
    
    :
    1. 완료
    2. Zep그래프읽기엔터티
    3. 엔터티생성OASIS Agent Profile()
    4. LLM생성시뮬레이션설정()
    5. 저장설정 파일
    
    요청(JSON):
        {
            "simulation_id": "sim_xxxx",                   // 필수, 시뮬레이션 ID
            "entity_types": ["Student", "PublicFigure"],  // 선택, 엔터티타입
            "use_llm_for_profiles": true,                 // 선택, LLM생성
            "parallel_profile_count": 5,                  // 선택, 병렬생성, 5
            "force_regenerate": false                     // 선택, 생성, false
        }
    
    반환:
        {
            "success": true,
            "data": {
                "simulation_id": "sim_xxxx",
                "task_id": "task_xxxx",           // 작업반환
                "status": "preparing|ready",
                "message": "작업 시작|완료",
                "already_prepared": true|false    // 완료
            }
        }
    """
    import threading
    import os
    from ..models.task import TaskManager, TaskStatus
    from ..config import Config
    
    try:
        data = request.get_json() or {}
        
        simulation_id = data.get('simulation_id')
        if not simulation_id:
            return jsonify({
                "success": False,
                "error": "simulation_id를 입력해 주세요."
            }), 400
        
        manager = SimulationManager()
        state = manager.get_simulation(simulation_id)
        
        if not state:
            return jsonify({
                "success": False,
                "error": f"시뮬레이션이 존재하지 않습니다: {simulation_id}"
            }), 404
        
        # 생성
        force_regenerate = data.get('force_regenerate', False)
        logger.info(f"시작 /prepare 요청: simulation_id={simulation_id}, force_regenerate={force_regenerate}")
        
        # 완료(생성)
        if not force_regenerate:
            logger.debug(f"시뮬레이션 {simulation_id} 완료...")
            is_prepared, prepare_info = _check_simulation_prepared(simulation_id)
            logger.debug(f": is_prepared={is_prepared}, prepare_info={prepare_info}")
            if is_prepared:
                logger.info(f"시뮬레이션 {simulation_id} 완료, 생성")
                return jsonify({
                    "success": True,
                    "data": {
                        "simulation_id": simulation_id,
                        "status": "ready",
                        "message": "완료, 생성",
                        "already_prepared": True,
                        "prepare_info": prepare_info
                    }
                })
            else:
                logger.info(f"시뮬레이션 {simulation_id} 완료, 시작작업")
        
        # 프로젝트정보
        project = ProjectManager.get_project(state.project_id)
        if not project:
            return jsonify({
                "success": False,
                "error": f"프로젝트가 존재하지 않습니다: {state.project_id}"
            }), 404
        
        # 시뮬레이션
        simulation_requirement = project.simulation_requirement or ""
        if not simulation_requirement:
            return jsonify({
                "success": False,
                "error": "프로젝트누락시뮬레이션 (simulation_requirement)"
            }), 400
        
        # 
        document_text = ProjectManager.get_extracted_text(state.project_id) or ""
        
        entity_types_list = data.get('entity_types')
        use_llm_for_profiles = data.get('use_llm_for_profiles', True)
        parallel_profile_count = data.get('parallel_profile_count', 5)
        
        # ========== 엔터티(작업 시작) ==========
        # 호출prepareAgent
        try:
            logger.info(f"엔터티: graph_id={state.graph_id}")
            reader = ZepEntityReader()
            # 읽기엔터티(엣지정보, )
            filtered_preview = reader.filter_defined_entities(
                graph_id=state.graph_id,
                defined_entity_types=entity_types_list,
                enrich_with_edges=False  # 엣지정보, 
            )
            # 저장엔터티상태()
            state.entities_count = filtered_preview.filtered_count
            state.entity_types = list(filtered_preview.entity_types)
            logger.info(f"엔터티: {filtered_preview.filtered_count}, 타입: {filtered_preview.entity_types}")
        except Exception as e:
            logger.warning(f"엔터티실패(작업진행 중: {e}")
            # 실패, 작업
        
        # 작업
        task_manager = TaskManager()
        task_id = task_manager.create_task(
            task_type="simulation_prepare",
            metadata={
                "simulation_id": simulation_id,
                "project_id": state.project_id
            }
        )
        
        # 시뮬레이션상태(엔터티)
        state.status = SimulationStatus.PREPARING
        manager._save_simulation_state(state)
        
        # 작업
        def run_prepare():
            try:
                task_manager.update_task(
                    task_id,
                    status=TaskStatus.PROCESSING,
                    progress=0,
                    message="시작시뮬레이션..."
                )
                
                # 시뮬레이션(진행률)
                # 진행률
                stage_details = {}
                
                def progress_callback(stage, progress, message, **kwargs):
                    # 진행률
                    stage_weights = {
                        "reading": (0, 20),           # 0-20%
                        "generating_profiles": (20, 70),  # 20-70%
                        "generating_config": (70, 90),    # 70-90%
                        "copying_scripts": (90, 100)       # 90-100%
                    }
                    
                    start, end = stage_weights.get(stage, (0, 100))
                    current_progress = int(start + (end - start) * progress / 100)
                    
                    # 상세진행률정보
                    stage_names = {
                        "reading": "읽기그래프엔터티",
                        "generating_profiles": "생성Agent",
                        "generating_config": "생성시뮬레이션설정",
                        "copying_scripts": "시뮬레이션"
                    }
                    
                    stage_index = list(stage_weights.keys()).index(stage) + 1 if stage in stage_weights else 1
                    total_stages = len(stage_weights)
                    
                    # 
                    stage_details[stage] = {
                        "stage_name": stage_names.get(stage, stage),
                        "stage_progress": progress,
                        "current": kwargs.get("current", 0),
                        "total": kwargs.get("total", 0),
                        "item_name": kwargs.get("item_name", "")
                    }
                    
                    # 상세진행률정보
                    detail = stage_details[stage]
                    progress_detail_data = {
                        "current_stage": stage,
                        "current_stage_name": stage_names.get(stage, stage),
                        "stage_index": stage_index,
                        "total_stages": total_stages,
                        "stage_progress": progress,
                        "current_item": detail["current"],
                        "total_items": detail["total"],
                        "item_description": message
                    }
                    
                    # 
                    if detail["total"] > 0:
                        detailed_message = (
                            f"[{stage_index}/{total_stages}] {stage_names.get(stage, stage)}: "
                            f"{detail['current']}/{detail['total']} - {message}"
                        )
                    else:
                        detailed_message = f"[{stage_index}/{total_stages}] {stage_names.get(stage, stage)}: {message}"
                    
                    task_manager.update_task(
                        task_id,
                        progress=current_progress,
                        message=detailed_message,
                        progress_detail=progress_detail_data
                    )
                
                result_state = manager.prepare_simulation(
                    simulation_id=simulation_id,
                    simulation_requirement=simulation_requirement,
                    document_text=document_text,
                    defined_entity_types=entity_types_list,
                    use_llm_for_profiles=use_llm_for_profiles,
                    progress_callback=progress_callback,
                    parallel_profile_count=parallel_profile_count
                )
                
                # 작업완료
                task_manager.complete_task(
                    task_id,
                    result=result_state.to_simple_dict()
                )
                
            except Exception as e:
                logger.error(f"시뮬레이션실패: {str(e)}")
                task_manager.fail_task(task_id, str(e))
                
                # 시뮬레이션상태실패
                state = manager.get_simulation(simulation_id)
                if state:
                    state.status = SimulationStatus.FAILED
                    state.error = str(e)
                    manager._save_simulation_state(state)
        
        # 시작
        thread = threading.Thread(target=run_prepare, daemon=True)
        thread.start()
        
        return jsonify({
            "success": True,
            "data": {
                "simulation_id": simulation_id,
                "task_id": task_id,
                "status": "preparing",
                "message": "작업 시작,  /api/simulation/prepare/status 진행률 조회",
                "already_prepared": False,
                "expected_entities_count": state.entities_count,  # Agent
                "entity_types": state.entity_types  # 엔터티타입목록
            }
        })
        
    except ValueError as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 404
        
    except Exception as e:
        logger.error(f"시작작업실패: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@simulation_bp.route('/prepare/status', methods=['POST'])
def get_prepare_status():
    """
    조회작업진행률
    
    조회:
    1. task_id조회진행 중작업진행률
    2. simulation_id완료
    
    요청(JSON):
        {
            "task_id": "task_xxxx",          // 선택, prepare반환task_id
            "simulation_id": "sim_xxxx"      // 선택, 시뮬레이션 ID(완료)
        }
    
    반환:
        {
            "success": true,
            "data": {
                "task_id": "task_xxxx",
                "status": "processing|completed|ready",
                "progress": 45,
                "message": "...",
                "already_prepared": true|false,  // 완료
                "prepare_info": {...}            // 완료상세정보
            }
        }
    """
    from ..models.task import TaskManager
    
    try:
        data = request.get_json() or {}
        
        task_id = data.get('task_id')
        simulation_id = data.get('simulation_id')
        
        # simulation_id, 완료
        if simulation_id:
            is_prepared, prepare_info = _check_simulation_prepared(simulation_id)
            if is_prepared:
                return jsonify({
                    "success": True,
                    "data": {
                        "simulation_id": simulation_id,
                        "status": "ready",
                        "progress": 100,
                        "message": "완료",
                        "already_prepared": True,
                        "prepare_info": prepare_info
                    }
                })
        
        # task_id, 반환오류
        if not task_id:
            if simulation_id:
                # simulation_id완료
                return jsonify({
                    "success": True,
                    "data": {
                        "simulation_id": simulation_id,
                        "status": "not_started",
                        "progress": 0,
                        "message": "시작, 호출 /api/simulation/prepare 시작",
                        "already_prepared": False
                    }
                })
            return jsonify({
                "success": False,
                "error": "task_id  simulation_id를 입력해 주세요."
            }), 400
        
        task_manager = TaskManager()
        task = task_manager.get_task(task_id)
        
        if not task:
            # 작업이 존재하지 않습니다, simulation_id, 완료
            if simulation_id:
                is_prepared, prepare_info = _check_simulation_prepared(simulation_id)
                if is_prepared:
                    return jsonify({
                        "success": True,
                        "data": {
                            "simulation_id": simulation_id,
                            "task_id": task_id,
                            "status": "ready",
                            "progress": 100,
                            "message": "작업 완료",
                            "already_prepared": True,
                            "prepare_info": prepare_info
                        }
                    })
            
            return jsonify({
                "success": False,
                "error": f"작업이 존재하지 않습니다: {task_id}"
            }), 404
        
        task_dict = task.to_dict()
        task_dict["already_prepared"] = False
        
        return jsonify({
            "success": True,
            "data": task_dict
        })
        
    except Exception as e:
        logger.error(f"조회작업상태실패: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500






# ============== Profile생성API() ==============

@simulation_bp.route('/generate-profiles', methods=['POST'])
def generate_profiles():
    """
    그래프생성OASIS Agent Profile(시뮬레이션)
    
    요청(JSON):
        {
            "graph_id": "mirofish_xxxx",     // 필수
            "entity_types": ["Student"],      // 선택
            "use_llm": true,                  // 선택
            "platform": "reddit"              // 선택
        }
    """
    try:
        data = request.get_json() or {}
        
        graph_id = data.get('graph_id')
        if not graph_id:
            return jsonify({
                "success": False,
                "error": "graph_id를 입력해 주세요."
            }), 400
        
        entity_types = data.get('entity_types')
        use_llm = data.get('use_llm', True)
        platform = data.get('platform', 'reddit')
        
        reader = ZepEntityReader()
        filtered = reader.filter_defined_entities(
            graph_id=graph_id,
            defined_entity_types=entity_types,
            enrich_with_edges=True
        )
        
        if filtered.filtered_count == 0:
            return jsonify({
                "success": False,
                "error": "찾지 못함엔터티"
            }), 400
        
        generator = OasisProfileGenerator()
        profiles = generator.generate_profiles_from_entities(
            entities=filtered.entities,
            use_llm=use_llm
        )
        
        if platform == "reddit":
            profiles_data = [p.to_reddit_format() for p in profiles]
        elif platform == "twitter":
            profiles_data = [p.to_twitter_format() for p in profiles]
        else:
            profiles_data = [p.to_dict() for p in profiles]
        
        return jsonify({
            "success": True,
            "data": {
                "platform": platform,
                "entity_types": list(filtered.entity_types),
                "count": len(profiles_data),
                "profiles": profiles_data
            }
        })
        
    except Exception as e:
        logger.error(f"생성Profile실패: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


# ============== 시뮬레이션 실행API ==============

@simulation_bp.route('/start', methods=['POST'])
def start_simulation():
    """
    시작실행시뮬레이션

    요청(JSON):
        {
            "simulation_id": "sim_xxxx",          // 필수, 시뮬레이션 ID
            "platform": "parallel",                // 선택: twitter / reddit / parallel ()
            "max_rounds": 100,                     // 선택: 시뮬레이션, 시뮬레이션
            "enable_graph_memory_update": false,   // 선택: AgentZep그래프
            "force": false                         // 선택: 시작(중지실행진행 중레이션로그)
        }

     force 파라미터:
        - , 시뮬레이션실행 중완료, 중지실행로그
        - :run_state.json, actions.jsonl, simulation.log 
        - 설정 파일(simulation_config.json) profile 파일
        - 실행시뮬레이션

     enable_graph_memory_update:
        - , 시뮬레이션에이전트(, , )Zep그래프
        - 그래프""시뮬레이션, 분석AI
        - 시뮬레이션프로젝트유효 graph_id
        - , API호출

    반환:
        {
            "success": true,
            "data": {
                "simulation_id": "sim_xxxx",
                "runner_status": "running",
                "process_pid": 12345,
                "twitter_running": true,
                "reddit_running": true,
                "started_at": "2025-12-01T10:00:00",
                "graph_memory_update_enabled": true,  // 그래프
                "force_restarted": true               // 시작
            }
        }
    """
    try:
        data = request.get_json() or {}

        simulation_id = data.get('simulation_id')
        if not simulation_id:
            return jsonify({
                "success": False,
                "error": "simulation_id를 입력해 주세요."
            }), 400

        platform = data.get('platform', 'parallel')
        max_rounds = data.get('max_rounds')  # 선택:시뮬레이션
        enable_graph_memory_update = data.get('enable_graph_memory_update', False)  # 선택:그래프
        force = data.get('force', False)  # 선택:시작

        #  max_rounds 파라미터
        if max_rounds is not None:
            try:
                max_rounds = int(max_rounds)
                if max_rounds <= 0:
                    return jsonify({
                        "success": False,
                        "error": "max_rounds "
                    }), 400
            except (ValueError, TypeError):
                return jsonify({
                    "success": False,
                    "error": "max_rounds 유효"
                }), 400

        if platform not in ['twitter', 'reddit', 'parallel']:
            return jsonify({
                "success": False,
                "error": f"플랫폼타입: {platform}, 선택: twitter/reddit/parallel"
            }), 400

        # 시뮬레이션
        manager = SimulationManager()
        state = manager.get_simulation(simulation_id)

        if not state:
            return jsonify({
                "success": False,
                "error": f"시뮬레이션이 존재하지 않습니다: {simulation_id}"
            }), 404

        force_restarted = False
        
        # 상태:완료, 시작
        if state.status != SimulationStatus.READY:
            # 완료
            is_prepared, prepare_info = _check_simulation_prepared(simulation_id)

            if is_prepared:
                # 완료, 실행 중
                if state.status == SimulationStatus.RUNNING:
                    # 시뮬레이션 실행
                    run_state = SimulationRunner.get_run_state(simulation_id)
                    if run_state and run_state.runner_status.value == "running":
                        # 실행
                        if force:
                            # :중지실행진행 중레이션
                            logger.info(f":중지실행진행 중레이션 {simulation_id}")
                            try:
                                SimulationRunner.stop_simulation(simulation_id)
                            except Exception as e:
                                logger.warning(f"중지시뮬레이션경고: {str(e)}")
                        else:
                            return jsonify({
                                "success": False,
                                "error": f"시뮬레이션실행 중진행 중호출 /stop API중지,  force=true 시작"
                            }), 400

                # , 실행로그
                if force:
                    logger.info(f":시뮬레이션로그 {simulation_id}")
                    cleanup_result = SimulationRunner.cleanup_simulation_logs(simulation_id)
                    if not cleanup_result.get("success"):
                        logger.warning(f"로그경고: {cleanup_result.get('errors')}")
                    force_restarted = True

                # 존재하지 않습니다, 초기화상태 ready
                logger.info(f"시뮬레이션 {simulation_id} 완료, 초기화상태 ready(상태: {state.status.value})")
                state.status = SimulationStatus.READY
                manager._save_simulation_state(state)
            else:
                # 완료
                return jsonify({
                    "success": False,
                    "error": f"시뮬레이션, 현재상태: {state.status.value}, 호출 /prepare API"
                }), 400
        
        # 그래프 ID(그래프)
        graph_id = None
        if enable_graph_memory_update:
            # 시뮬레이션상태프로젝트graph_id
            graph_id = state.graph_id
            if not graph_id:
                # 프로젝트
                project = ProjectManager.get_project(state.project_id)
                if project:
                    graph_id = project.graph_id
            
            if not graph_id:
                return jsonify({
                    "success": False,
                    "error": "그래프유효 graph_id, 프로젝트그래프"
                }), 400
            
            logger.info(f"그래프: simulation_id={simulation_id}, graph_id={graph_id}")
        
        # 시작시뮬레이션
        run_state = SimulationRunner.start_simulation(
            simulation_id=simulation_id,
            platform=platform,
            max_rounds=max_rounds,
            enable_graph_memory_update=enable_graph_memory_update,
            graph_id=graph_id
        )
        
        # 시뮬레이션상태
        state.status = SimulationStatus.RUNNING
        manager._save_simulation_state(state)
        
        response_data = run_state.to_dict()
        if max_rounds:
            response_data['max_rounds_applied'] = max_rounds
        response_data['graph_memory_update_enabled'] = enable_graph_memory_update
        response_data['force_restarted'] = force_restarted
        if enable_graph_memory_update:
            response_data['graph_id'] = graph_id
        
        return jsonify({
            "success": True,
            "data": response_data
        })
        
    except ValueError as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 400
        
    except Exception as e:
        logger.error(f"시작시뮬레이션실패: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@simulation_bp.route('/stop', methods=['POST'])
def stop_simulation():
    """
    중지시뮬레이션
    
    요청(JSON):
        {
            "simulation_id": "sim_xxxx"  // 필수, 시뮬레이션 ID
        }
    
    반환:
        {
            "success": true,
            "data": {
                "simulation_id": "sim_xxxx",
                "runner_status": "stopped",
                "completed_at": "2025-12-01T12:00:00"
            }
        }
    """
    try:
        data = request.get_json() or {}
        
        simulation_id = data.get('simulation_id')
        if not simulation_id:
            return jsonify({
                "success": False,
                "error": "simulation_id를 입력해 주세요."
            }), 400
        
        run_state = SimulationRunner.stop_simulation(simulation_id)
        
        # 시뮬레이션상태
        manager = SimulationManager()
        state = manager.get_simulation(simulation_id)
        if state:
            state.status = SimulationStatus.PAUSED
            manager._save_simulation_state(state)
        
        return jsonify({
            "success": True,
            "data": run_state.to_dict()
        })
        
    except ValueError as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 400
        
    except Exception as e:
        logger.error(f"중지시뮬레이션실패: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500






