import threading
import traceback

from flask import jsonify, request

from .blueprint import simulation_bp
from .helpers import check_simulation_prepared, logger
from ...models.project import ProjectManager
from ...models.task import TaskManager, TaskStatus
from ...services.simulation import SimulationManager, SimulationStatus
from ...services.zep import ZepEntityReader


@simulation_bp.route("/create", methods=["POST"])
def create_simulation():
    try:
        data = request.get_json() or {}

        project_id = data.get("project_id")
        if not project_id:
            return jsonify({"success": False, "error": "project_id를 입력해 주세요."}), 400

        project = ProjectManager.get_project(project_id)
        if not project:
            return jsonify(
                {"success": False, "error": f"프로젝트가 존재하지 않습니다: {project_id}"}
            ), 404

        graph_id = data.get("graph_id") or project.graph_id
        if not graph_id:
            return jsonify({"success": False, "error": "프로젝트 그래프가 없습니다."}), 400

        manager = SimulationManager()
        state = manager.create_simulation(
            project_id=project_id,
            graph_id=graph_id,
            enable_twitter=data.get("enable_twitter", True),
            enable_reddit=data.get("enable_reddit", True),
        )

        return jsonify({"success": True, "data": state.to_dict()})

    except Exception as e:
        logger.error(f"시뮬레이션 생성 실패: {str(e)}")
        return jsonify(
            {"success": False, "error": str(e), "traceback": traceback.format_exc()}
        ), 500


@simulation_bp.route("/prepare", methods=["POST"])
def prepare_simulation():
    try:
        data = request.get_json() or {}

        simulation_id = data.get("simulation_id")
        if not simulation_id:
            return jsonify({"success": False, "error": "simulation_id를 입력해 주세요."}), 400

        manager = SimulationManager()
        state = manager.get_simulation(simulation_id)
        if not state:
            return jsonify(
                {"success": False, "error": f"시뮬레이션이 존재하지 않습니다: {simulation_id}"}
            ), 404

        force_regenerate = data.get("force_regenerate", False)
        logger.info(f"/prepare 요청: simulation_id={simulation_id}, force_regenerate={force_regenerate}")

        if not force_regenerate:
            is_prepared, prepare_info = check_simulation_prepared(simulation_id)
            if is_prepared:
                return jsonify(
                    {
                        "success": True,
                        "data": {
                            "simulation_id": simulation_id,
                            "status": "ready",
                            "message": "이미 준비가 완료되었습니다.",
                            "already_prepared": True,
                            "prepare_info": prepare_info,
                        },
                    }
                )

        project = ProjectManager.get_project(state.project_id)
        if not project:
            return jsonify(
                {"success": False, "error": f"프로젝트가 존재하지 않습니다: {state.project_id}"}
            ), 404

        simulation_requirement = project.simulation_requirement or ""
        if not simulation_requirement:
            return jsonify(
                {"success": False, "error": "프로젝트에 simulation_requirement가 없습니다."}
            ), 400

        document_text = ProjectManager.get_extracted_text(state.project_id) or ""
        entity_types_list = data.get("entity_types")
        use_llm_for_profiles = data.get("use_llm_for_profiles", True)
        parallel_profile_count = data.get("parallel_profile_count", 5)

        try:
            reader = ZepEntityReader()
            filtered_preview = reader.filter_defined_entities(
                graph_id=state.graph_id,
                defined_entity_types=entity_types_list,
                enrich_with_edges=False,
            )
            state.entities_count = filtered_preview.filtered_count
            state.entity_types = list(filtered_preview.entity_types)
        except Exception as e:
            logger.warning(f"엔터티 미리보기 실패: {e}")

        task_manager = TaskManager()
        task_id = task_manager.create_task(
            task_type="simulation_prepare",
            metadata={"simulation_id": simulation_id, "project_id": state.project_id},
        )

        state.status = SimulationStatus.PREPARING
        manager._save_simulation_state(state)

        def run_prepare():
            try:
                task_manager.update_task(
                    task_id,
                    status=TaskStatus.PROCESSING,
                    progress=0,
                    message="시뮬레이션 준비를 시작합니다.",
                )

                stage_details = {}

                def progress_callback(stage, progress, message, **kwargs):
                    stage_weights = {
                        "reading": (0, 20),
                        "generating_profiles": (20, 70),
                        "generating_config": (70, 90),
                        "copying_scripts": (90, 100),
                    }
                    start, end = stage_weights.get(stage, (0, 100))
                    current_progress = int(start + (end - start) * progress / 100)

                    stage_names = {
                        "reading": "그래프 엔터티 읽기",
                        "generating_profiles": "에이전트 프로필 생성",
                        "generating_config": "시뮬레이션 설정 생성",
                        "copying_scripts": "실행 스크립트 준비",
                    }
                    stage_index = list(stage_weights.keys()).index(stage) + 1 if stage in stage_weights else 1
                    total_stages = len(stage_weights)

                    stage_details[stage] = {
                        "stage_name": stage_names.get(stage, stage),
                        "stage_progress": progress,
                        "current": kwargs.get("current", 0),
                        "total": kwargs.get("total", 0),
                    }
                    detail = stage_details[stage]

                    progress_detail_data = {
                        "current_stage": stage,
                        "current_stage_name": stage_names.get(stage, stage),
                        "stage_index": stage_index,
                        "total_stages": total_stages,
                        "stage_progress": progress,
                        "current_item": detail["current"],
                        "total_items": detail["total"],
                        "item_description": message,
                    }

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
                        progress_detail=progress_detail_data,
                    )

                result_state = manager.prepare_simulation(
                    simulation_id=simulation_id,
                    simulation_requirement=simulation_requirement,
                    document_text=document_text,
                    defined_entity_types=entity_types_list,
                    use_llm_for_profiles=use_llm_for_profiles,
                    progress_callback=progress_callback,
                    parallel_profile_count=parallel_profile_count,
                )

                task_manager.complete_task(task_id, result=result_state.to_simple_dict())

            except Exception as e:
                logger.error(f"시뮬레이션 준비 실패: {str(e)}")
                task_manager.fail_task(task_id, str(e))

                latest_state = manager.get_simulation(simulation_id)
                if latest_state:
                    latest_state.status = SimulationStatus.FAILED
                    latest_state.error = str(e)
                    manager._save_simulation_state(latest_state)

        thread = threading.Thread(target=run_prepare, daemon=True)
        thread.start()

        return jsonify(
            {
                "success": True,
                "data": {
                    "simulation_id": simulation_id,
                    "task_id": task_id,
                    "status": "preparing",
                    "message": "준비 작업이 시작되었습니다.",
                    "already_prepared": False,
                    "expected_entities_count": state.entities_count,
                    "entity_types": state.entity_types,
                },
            }
        )

    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 404
    except Exception as e:
        logger.error(f"시뮬레이션 준비 시작 실패: {str(e)}")
        return jsonify(
            {"success": False, "error": str(e), "traceback": traceback.format_exc()}
        ), 500


@simulation_bp.route("/prepare/status", methods=["POST"])
def get_prepare_status():
    try:
        data = request.get_json() or {}

        task_id = data.get("task_id")
        simulation_id = data.get("simulation_id")

        if simulation_id:
            is_prepared, prepare_info = check_simulation_prepared(simulation_id)
            if is_prepared:
                return jsonify(
                    {
                        "success": True,
                        "data": {
                            "simulation_id": simulation_id,
                            "status": "ready",
                            "progress": 100,
                            "message": "준비가 완료되었습니다.",
                            "already_prepared": True,
                            "prepare_info": prepare_info,
                        },
                    }
                )

        if not task_id:
            if simulation_id:
                return jsonify(
                    {
                        "success": True,
                        "data": {
                            "simulation_id": simulation_id,
                            "status": "not_started",
                            "progress": 0,
                            "message": "아직 준비 작업이 시작되지 않았습니다.",
                            "already_prepared": False,
                        },
                    }
                )
            return jsonify({"success": False, "error": "task_id 또는 simulation_id를 입력해 주세요."}), 400

        task_manager = TaskManager()
        task = task_manager.get_task(task_id)
        if not task:
            if simulation_id:
                is_prepared, prepare_info = check_simulation_prepared(simulation_id)
                if is_prepared:
                    return jsonify(
                        {
                            "success": True,
                            "data": {
                                "simulation_id": simulation_id,
                                "task_id": task_id,
                                "status": "ready",
                                "progress": 100,
                                "message": "작업이 이미 완료되었습니다.",
                                "already_prepared": True,
                                "prepare_info": prepare_info,
                            },
                        }
                    )
            return jsonify({"success": False, "error": f"작업이 존재하지 않습니다: {task_id}"}), 404

        task_dict = task.to_dict()
        task_dict["already_prepared"] = False
        return jsonify({"success": True, "data": task_dict})

    except Exception as e:
        logger.error(f"prepare 상태 조회 실패: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500
