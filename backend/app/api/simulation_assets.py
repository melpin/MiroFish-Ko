"""
Asset and configuration retrieval routes for the simulation API blueprint.
"""

import csv
import json
import os
import traceback
from datetime import datetime

from flask import jsonify, request, send_file

from . import simulation_bp
from ..config import Config
from ..services.simulation_manager import SimulationManager
from ..utils.logger import get_logger

logger = get_logger("mirofish.api.simulation.assets")


@simulation_bp.route("/<simulation_id>/profiles", methods=["GET"])
def get_simulation_profiles(simulation_id: str):
    try:
        platform = request.args.get("platform", "reddit")

        manager = SimulationManager()
        profiles = manager.get_profiles(simulation_id, platform=platform)

        return jsonify(
            {
                "success": True,
                "data": {
                    "platform": platform,
                    "count": len(profiles),
                    "profiles": profiles,
                },
            }
        )

    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 404
    except Exception as e:
        logger.error(f"프로필 조회 실패: {str(e)}")
        return jsonify(
            {"success": False, "error": str(e), "traceback": traceback.format_exc()}
        ), 500


@simulation_bp.route("/<simulation_id>/profiles/realtime", methods=["GET"])
def get_simulation_profiles_realtime(simulation_id: str):
    try:
        platform = request.args.get("platform", "reddit")
        sim_dir = os.path.join(Config.OASIS_SIMULATION_DATA_DIR, simulation_id)

        if not os.path.exists(sim_dir):
            return jsonify(
                {"success": False, "error": f"시뮬레이션이 존재하지 않습니다: {simulation_id}"}
            ), 404

        profiles_file = (
            os.path.join(sim_dir, "reddit_profiles.json")
            if platform == "reddit"
            else os.path.join(sim_dir, "twitter_profiles.csv")
        )

        file_exists = os.path.exists(profiles_file)
        profiles = []
        file_modified_at = None

        if file_exists:
            file_modified_at = datetime.fromtimestamp(os.stat(profiles_file).st_mtime).isoformat()
            try:
                with open(profiles_file, "r", encoding="utf-8") as file:
                    if platform == "reddit":
                        profiles = json.load(file)
                    else:
                        profiles = list(csv.DictReader(file))
            except (json.JSONDecodeError, Exception) as e:
                logger.warning(f"프로필 파일 읽기 실패: {e}")
                profiles = []

        is_generating = False
        total_expected = None
        state_file = os.path.join(sim_dir, "state.json")
        if os.path.exists(state_file):
            try:
                with open(state_file, "r", encoding="utf-8") as file:
                    state_data = json.load(file)
                is_generating = state_data.get("status", "") == "preparing"
                total_expected = state_data.get("entities_count")
            except Exception:
                pass

        return jsonify(
            {
                "success": True,
                "data": {
                    "simulation_id": simulation_id,
                    "platform": platform,
                    "count": len(profiles),
                    "total_expected": total_expected,
                    "is_generating": is_generating,
                    "file_exists": file_exists,
                    "file_modified_at": file_modified_at,
                    "profiles": profiles,
                },
            }
        )

    except Exception as e:
        logger.error(f"실시간 프로필 조회 실패: {str(e)}")
        return jsonify(
            {"success": False, "error": str(e), "traceback": traceback.format_exc()}
        ), 500


@simulation_bp.route("/<simulation_id>/config/realtime", methods=["GET"])
def get_simulation_config_realtime(simulation_id: str):
    try:
        sim_dir = os.path.join(Config.OASIS_SIMULATION_DATA_DIR, simulation_id)
        if not os.path.exists(sim_dir):
            return jsonify(
                {"success": False, "error": f"시뮬레이션이 존재하지 않습니다: {simulation_id}"}
            ), 404

        config_file = os.path.join(sim_dir, "simulation_config.json")
        file_exists = os.path.exists(config_file)
        config = None
        file_modified_at = None

        if file_exists:
            file_modified_at = datetime.fromtimestamp(os.stat(config_file).st_mtime).isoformat()
            try:
                with open(config_file, "r", encoding="utf-8") as file:
                    config = json.load(file)
            except (json.JSONDecodeError, Exception) as e:
                logger.warning(f"설정 파일 읽기 실패: {e}")
                config = None

        is_generating = False
        generation_stage = None
        config_generated = False
        state_file = os.path.join(sim_dir, "state.json")
        if os.path.exists(state_file):
            try:
                with open(state_file, "r", encoding="utf-8") as file:
                    state_data = json.load(file)

                status = state_data.get("status", "")
                is_generating = status == "preparing"
                config_generated = state_data.get("config_generated", False)

                if is_generating:
                    generation_stage = (
                        "generating_config"
                        if state_data.get("profiles_generated", False)
                        else "generating_profiles"
                    )
                elif status == "ready":
                    generation_stage = "completed"
            except Exception:
                pass

        response_data = {
            "simulation_id": simulation_id,
            "file_exists": file_exists,
            "file_modified_at": file_modified_at,
            "is_generating": is_generating,
            "generation_stage": generation_stage,
            "config_generated": config_generated,
            "config": config,
        }

        if config:
            response_data["summary"] = {
                "total_agents": len(config.get("agent_configs", [])),
                "simulation_hours": config.get("time_config", {}).get("total_simulation_hours"),
                "initial_posts_count": len(config.get("event_config", {}).get("initial_posts", [])),
                "hot_topics_count": len(config.get("event_config", {}).get("hot_topics", [])),
                "has_twitter_config": "twitter_config" in config,
                "has_reddit_config": "reddit_config" in config,
                "generated_at": config.get("generated_at"),
                "llm_model": config.get("llm_model"),
            }

        return jsonify({"success": True, "data": response_data})

    except Exception as e:
        logger.error(f"실시간 설정 조회 실패: {str(e)}")
        return jsonify(
            {"success": False, "error": str(e), "traceback": traceback.format_exc()}
        ), 500


@simulation_bp.route("/<simulation_id>/config", methods=["GET"])
def get_simulation_config(simulation_id: str):
    try:
        manager = SimulationManager()
        config = manager.get_simulation_config(simulation_id)
        if not config:
            return jsonify(
                {"success": False, "error": "시뮬레이션 설정이 없습니다. /prepare API를 먼저 호출해 주세요."}
            ), 404

        return jsonify({"success": True, "data": config})

    except Exception as e:
        logger.error(f"설정 조회 실패: {str(e)}")
        return jsonify(
            {"success": False, "error": str(e), "traceback": traceback.format_exc()}
        ), 500


@simulation_bp.route("/<simulation_id>/config/download", methods=["GET"])
def download_simulation_config(simulation_id: str):
    try:
        manager = SimulationManager()
        sim_dir = manager._get_simulation_dir(simulation_id)
        config_path = os.path.join(sim_dir, "simulation_config.json")

        if not os.path.exists(config_path):
            return jsonify(
                {"success": False, "error": "설정 파일이 없습니다. /prepare API를 먼저 호출해 주세요."}
            ), 404

        return send_file(config_path, as_attachment=True, download_name="simulation_config.json")

    except Exception as e:
        logger.error(f"설정 다운로드 실패: {str(e)}")
        return jsonify(
            {"success": False, "error": str(e), "traceback": traceback.format_exc()}
        ), 500


@simulation_bp.route("/script/<script_name>/download", methods=["GET"])
def download_simulation_script(script_name: str):
    try:
        scripts_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../scripts"))
        allowed_scripts = [
            "run_twitter_simulation.py",
            "run_reddit_simulation.py",
            "run_parallel_simulation.py",
            "action_logger.py",
        ]

        if script_name not in allowed_scripts:
            return jsonify(
                {
                    "success": False,
                    "error": f"허용되지 않은 스크립트입니다: {script_name}",
                }
            ), 400

        script_path = os.path.join(scripts_dir, script_name)
        if not os.path.exists(script_path):
            return jsonify({"success": False, "error": f"파일이 존재하지 않습니다: {script_name}"}), 404

        return send_file(script_path, as_attachment=True, download_name=script_name)

    except Exception as e:
        logger.error(f"스크립트 다운로드 실패: {str(e)}")
        return jsonify(
            {"success": False, "error": str(e), "traceback": traceback.format_exc()}
        ), 500
