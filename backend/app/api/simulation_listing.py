"""
Listing and history routes for the simulation API blueprint.
"""

import json
import os
import traceback

from flask import jsonify, request

from .simulation import simulation_bp
from ..models.project import ProjectManager
from ..services.simulation_manager import SimulationManager, SimulationStatus
from ..services.simulation_runner import SimulationRunner
from ..utils.logger import get_logger

logger = get_logger("mirofish.api.simulation.listing")


def _get_report_id_for_simulation(simulation_id: str) -> str | None:
    reports_dir = os.path.join(os.path.dirname(__file__), "../../uploads/reports")
    if not os.path.exists(reports_dir):
        return None

    matching_reports = []
    try:
        for report_folder in os.listdir(reports_dir):
            report_path = os.path.join(reports_dir, report_folder)
            if not os.path.isdir(report_path):
                continue

            meta_file = os.path.join(report_path, "meta.json")
            if not os.path.exists(meta_file):
                continue

            try:
                with open(meta_file, "r", encoding="utf-8") as file:
                    meta = json.load(file)
            except Exception:
                continue

            if meta.get("simulation_id") == simulation_id:
                matching_reports.append(
                    {
                        "report_id": meta.get("report_id"),
                        "created_at": meta.get("created_at", ""),
                    }
                )

        if not matching_reports:
            return None

        matching_reports.sort(key=lambda item: item.get("created_at", ""), reverse=True)
        return matching_reports[0].get("report_id")

    except Exception as e:
        logger.warning(f"simulation {simulation_id} report 조회 실패: {e}")
        return None


@simulation_bp.route("/<simulation_id>", methods=["GET"])
def get_simulation(simulation_id: str):
    try:
        manager = SimulationManager()
        state = manager.get_simulation(simulation_id)
        if not state:
            return jsonify(
                {"success": False, "error": f"시뮬레이션이 존재하지 않습니다: {simulation_id}"}
            ), 404

        result = state.to_dict()
        if state.status == SimulationStatus.READY:
            result["run_instructions"] = manager.get_run_instructions(simulation_id)

        return jsonify({"success": True, "data": result})

    except Exception as e:
        logger.error(f"시뮬레이션 상태 조회 실패: {str(e)}")
        return jsonify(
            {"success": False, "error": str(e), "traceback": traceback.format_exc()}
        ), 500


@simulation_bp.route("/list", methods=["GET"])
def list_simulations():
    try:
        project_id = request.args.get("project_id")
        manager = SimulationManager()
        simulations = manager.list_simulations(project_id=project_id)

        return jsonify(
            {
                "success": True,
                "data": [simulation.to_dict() for simulation in simulations],
                "count": len(simulations),
            }
        )

    except Exception as e:
        logger.error(f"시뮬레이션 목록 조회 실패: {str(e)}")
        return jsonify(
            {"success": False, "error": str(e), "traceback": traceback.format_exc()}
        ), 500


@simulation_bp.route("/history", methods=["GET"])
def get_simulation_history():
    try:
        limit = request.args.get("limit", 20, type=int)

        manager = SimulationManager()
        simulations = manager.list_simulations()[:limit]

        enriched_simulations = []
        for simulation in simulations:
            sim_dict = simulation.to_dict()

            config = manager.get_simulation_config(simulation.simulation_id)
            if config:
                sim_dict["simulation_requirement"] = config.get("simulation_requirement", "")
                time_config = config.get("time_config", {})
                sim_dict["total_simulation_hours"] = time_config.get("total_simulation_hours", 0)
                recommended_rounds = int(
                    time_config.get("total_simulation_hours", 0) * 60
                    / max(time_config.get("minutes_per_round", 60), 1)
                )
            else:
                sim_dict["simulation_requirement"] = ""
                sim_dict["total_simulation_hours"] = 0
                recommended_rounds = 0

            run_state = SimulationRunner.get_run_state(simulation.simulation_id)
            if run_state:
                sim_dict["current_round"] = run_state.current_round
                sim_dict["runner_status"] = run_state.runner_status.value
                sim_dict["total_rounds"] = (
                    run_state.total_rounds if run_state.total_rounds > 0 else recommended_rounds
                )
            else:
                sim_dict["current_round"] = 0
                sim_dict["runner_status"] = "idle"
                sim_dict["total_rounds"] = recommended_rounds

            project = ProjectManager.get_project(simulation.project_id)
            if project and hasattr(project, "files") and project.files:
                sim_dict["files"] = [{"filename": file.get("filename", "파일")} for file in project.files[:3]]
            else:
                sim_dict["files"] = []

            sim_dict["report_id"] = _get_report_id_for_simulation(simulation.simulation_id)
            sim_dict["version"] = "v1.0.2"
            sim_dict["created_date"] = sim_dict.get("created_at", "")[:10]
            enriched_simulations.append(sim_dict)

        return jsonify(
            {
                "success": True,
                "data": enriched_simulations,
                "count": len(enriched_simulations),
            }
        )

    except Exception as e:
        logger.error(f"시뮬레이션 히스토리 조회 실패: {str(e)}")
        return jsonify(
            {"success": False, "error": str(e), "traceback": traceback.format_exc()}
        ), 500
