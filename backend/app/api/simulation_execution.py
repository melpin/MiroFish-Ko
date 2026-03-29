"""
Execution routes for the simulation API blueprint.
"""

import traceback

from flask import jsonify, request

from . import simulation_bp
from .simulation import _check_simulation_prepared
from ..models.project import ProjectManager
from ..services.simulation_manager import SimulationManager, SimulationStatus
from ..services.simulation_runner import SimulationRunner
from ..utils.logger import get_logger

logger = get_logger("mirofish.api.simulation.execution")


@simulation_bp.route("/start", methods=["POST"])
def start_simulation():
    try:
        data = request.get_json() or {}

        simulation_id = data.get("simulation_id")
        if not simulation_id:
            return jsonify({"success": False, "error": "simulation_id를 입력해 주세요."}), 400

        platform = data.get("platform", "parallel")
        max_rounds = data.get("max_rounds")
        enable_graph_memory_update = data.get("enable_graph_memory_update", False)
        force = data.get("force", False)

        if max_rounds is not None:
            try:
                max_rounds = int(max_rounds)
                if max_rounds <= 0:
                    return jsonify({"success": False, "error": "max_rounds는 1 이상이어야 합니다."}), 400
            except (ValueError, TypeError):
                return jsonify({"success": False, "error": "max_rounds가 유효하지 않습니다."}), 400

        if platform not in ["twitter", "reddit", "parallel"]:
            return jsonify(
                {
                    "success": False,
                    "error": f"지원하지 않는 플랫폼입니다: {platform}",
                }
            ), 400

        manager = SimulationManager()
        state = manager.get_simulation(simulation_id)
        if not state:
            return jsonify(
                {"success": False, "error": f"시뮬레이션이 존재하지 않습니다: {simulation_id}"}
            ), 404

        force_restarted = False
        if state.status != SimulationStatus.READY:
            is_prepared, _ = _check_simulation_prepared(simulation_id)
            if not is_prepared:
                return jsonify(
                    {
                        "success": False,
                        "error": f"시뮬레이션 준비가 필요합니다. 현재 상태: {state.status.value}",
                    }
                ), 400

            if state.status == SimulationStatus.RUNNING:
                run_state = SimulationRunner.get_run_state(simulation_id)
                if run_state and run_state.runner_status.value == "running":
                    if force:
                        logger.info(f"강제 재시작을 위해 기존 시뮬레이션 중지: {simulation_id}")
                        try:
                            SimulationRunner.stop_simulation(simulation_id)
                        except Exception as e:
                            logger.warning(f"기존 시뮬레이션 중지 경고: {str(e)}")
                    else:
                        return jsonify(
                            {
                                "success": False,
                                "error": "이미 실행 중입니다. /stop 호출 또는 force=true로 재시작해 주세요.",
                            }
                        ), 400

            if force:
                cleanup_result = SimulationRunner.cleanup_simulation_logs(simulation_id)
                if not cleanup_result.get("success"):
                    logger.warning(f"실행 로그 정리 경고: {cleanup_result.get('errors')}")
                force_restarted = True

            state.status = SimulationStatus.READY
            manager._save_simulation_state(state)

        graph_id = None
        if enable_graph_memory_update:
            graph_id = state.graph_id
            if not graph_id:
                project = ProjectManager.get_project(state.project_id)
                if project:
                    graph_id = project.graph_id

            if not graph_id:
                return jsonify({"success": False, "error": "유효한 graph_id가 필요합니다."}), 400

            logger.info(f"그래프 메모리 업데이트 활성화: simulation_id={simulation_id}, graph_id={graph_id}")

        run_state = SimulationRunner.start_simulation(
            simulation_id=simulation_id,
            platform=platform,
            max_rounds=max_rounds,
            enable_graph_memory_update=enable_graph_memory_update,
            graph_id=graph_id,
        )

        state.status = SimulationStatus.RUNNING
        manager._save_simulation_state(state)

        response_data = run_state.to_dict()
        if max_rounds:
            response_data["max_rounds_applied"] = max_rounds
        response_data["graph_memory_update_enabled"] = enable_graph_memory_update
        response_data["force_restarted"] = force_restarted
        if enable_graph_memory_update:
            response_data["graph_id"] = graph_id

        return jsonify({"success": True, "data": response_data})

    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    except Exception as e:
        logger.error(f"시뮬레이션 시작 실패: {str(e)}")
        return jsonify(
            {"success": False, "error": str(e), "traceback": traceback.format_exc()}
        ), 500


@simulation_bp.route("/stop", methods=["POST"])
def stop_simulation():
    try:
        data = request.get_json() or {}

        simulation_id = data.get("simulation_id")
        if not simulation_id:
            return jsonify({"success": False, "error": "simulation_id를 입력해 주세요."}), 400

        run_state = SimulationRunner.stop_simulation(simulation_id)

        manager = SimulationManager()
        state = manager.get_simulation(simulation_id)
        if state:
            state.status = SimulationStatus.PAUSED
            manager._save_simulation_state(state)

        return jsonify({"success": True, "data": run_state.to_dict()})

    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    except Exception as e:
        logger.error(f"시뮬레이션 중지 실패: {str(e)}")
        return jsonify(
            {"success": False, "error": str(e), "traceback": traceback.format_exc()}
        ), 500
