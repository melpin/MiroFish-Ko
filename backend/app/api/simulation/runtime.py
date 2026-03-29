"""
Runtime status routes for the simulation API blueprint.
"""

import traceback

from flask import jsonify, request

from .blueprint import simulation_bp
from ...services.simulation import SimulationRunner
from ...utils.logger import get_logger

logger = get_logger("mirofish.api.simulation.runtime")


@simulation_bp.route("/<simulation_id>/run-status", methods=["GET"])
def get_run_status(simulation_id: str):
    try:
        run_state = SimulationRunner.get_run_state(simulation_id)
        if not run_state:
            return jsonify(
                {
                    "success": True,
                    "data": {
                        "simulation_id": simulation_id,
                        "runner_status": "idle",
                        "current_round": 0,
                        "total_rounds": 0,
                        "progress_percent": 0,
                        "twitter_actions_count": 0,
                        "reddit_actions_count": 0,
                        "total_actions_count": 0,
                    },
                }
            )

        return jsonify({"success": True, "data": run_state.to_dict()})

    except Exception as e:
        logger.error(f"실행 상태 조회 실패: {str(e)}")
        return jsonify(
            {"success": False, "error": str(e), "traceback": traceback.format_exc()}
        ), 500


@simulation_bp.route("/<simulation_id>/run-status/detail", methods=["GET"])
def get_run_status_detail(simulation_id: str):
    try:
        run_state = SimulationRunner.get_run_state(simulation_id)
        platform_filter = request.args.get("platform")

        if not run_state:
            return jsonify(
                {
                    "success": True,
                    "data": {
                        "simulation_id": simulation_id,
                        "runner_status": "idle",
                        "all_actions": [],
                        "twitter_actions": [],
                        "reddit_actions": [],
                    },
                }
            )

        all_actions = SimulationRunner.get_all_actions(
            simulation_id=simulation_id,
            platform=platform_filter,
        )
        twitter_actions = (
            SimulationRunner.get_all_actions(simulation_id=simulation_id, platform="twitter")
            if not platform_filter or platform_filter == "twitter"
            else []
        )
        reddit_actions = (
            SimulationRunner.get_all_actions(simulation_id=simulation_id, platform="reddit")
            if not platform_filter or platform_filter == "reddit"
            else []
        )

        current_round = run_state.current_round
        recent_actions = (
            SimulationRunner.get_all_actions(
                simulation_id=simulation_id,
                platform=platform_filter,
                round_num=current_round,
            )
            if current_round > 0
            else []
        )

        result = run_state.to_dict()
        result["all_actions"] = [action.to_dict() for action in all_actions]
        result["twitter_actions"] = [action.to_dict() for action in twitter_actions]
        result["reddit_actions"] = [action.to_dict() for action in reddit_actions]
        result["rounds_count"] = len(run_state.rounds)
        result["recent_actions"] = [action.to_dict() for action in recent_actions]

        return jsonify({"success": True, "data": result})

    except Exception as e:
        logger.error(f"실행 상세 상태 조회 실패: {str(e)}")
        return jsonify(
            {"success": False, "error": str(e), "traceback": traceback.format_exc()}
        ), 500


@simulation_bp.route("/<simulation_id>/actions", methods=["GET"])
def get_simulation_actions(simulation_id: str):
    try:
        limit = request.args.get("limit", 100, type=int)
        offset = request.args.get("offset", 0, type=int)
        platform = request.args.get("platform")
        agent_id = request.args.get("agent_id", type=int)
        round_num = request.args.get("round_num", type=int)

        actions = SimulationRunner.get_actions(
            simulation_id=simulation_id,
            limit=limit,
            offset=offset,
            platform=platform,
            agent_id=agent_id,
            round_num=round_num,
        )

        return jsonify(
            {
                "success": True,
                "data": {"count": len(actions), "actions": [action.to_dict() for action in actions]},
            }
        )

    except Exception as e:
        logger.error(f"액션 조회 실패: {str(e)}")
        return jsonify(
            {"success": False, "error": str(e), "traceback": traceback.format_exc()}
        ), 500


@simulation_bp.route("/<simulation_id>/timeline", methods=["GET"])
def get_simulation_timeline(simulation_id: str):
    try:
        start_round = request.args.get("start_round", 0, type=int)
        end_round = request.args.get("end_round", type=int)

        timeline = SimulationRunner.get_timeline(
            simulation_id=simulation_id,
            start_round=start_round,
            end_round=end_round,
        )

        return jsonify(
            {
                "success": True,
                "data": {"rounds_count": len(timeline), "timeline": timeline},
            }
        )

    except Exception as e:
        logger.error(f"타임라인 조회 실패: {str(e)}")
        return jsonify(
            {"success": False, "error": str(e), "traceback": traceback.format_exc()}
        ), 500


@simulation_bp.route("/<simulation_id>/agent-stats", methods=["GET"])
def get_agent_stats(simulation_id: str):
    try:
        stats = SimulationRunner.get_agent_stats(simulation_id)
        return jsonify({"success": True, "data": {"agents_count": len(stats), "stats": stats}})

    except Exception as e:
        logger.error(f"에이전트 통계 조회 실패: {str(e)}")
        return jsonify(
            {"success": False, "error": str(e), "traceback": traceback.format_exc()}
        ), 500
