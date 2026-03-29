"""
Interview-related routes for the simulation API blueprint.
"""

import traceback

from flask import jsonify, request

from .blueprint import simulation_bp
from .helpers import optimize_interview_prompt
from ...services.simulation import SimulationManager, SimulationRunner, SimulationStatus
from ...utils.logger import get_logger

logger = get_logger("mirofish.api.simulation.interviews")


@simulation_bp.route("/interview", methods=["POST"])
def interview_agent():
    try:
        data = request.get_json() or {}

        simulation_id = data.get("simulation_id")
        agent_id = data.get("agent_id")
        prompt = data.get("prompt")
        platform = data.get("platform")
        timeout = data.get("timeout", 60)

        if not simulation_id:
            return jsonify({"success": False, "error": "simulation_id를 입력해 주세요."}), 400

        if agent_id is None:
            return jsonify({"success": False, "error": "agent_id를 입력해 주세요."}), 400

        if not prompt:
            return jsonify({"success": False, "error": "prompt를 입력해 주세요."}), 400

        if platform and platform not in ("twitter", "reddit"):
            return jsonify(
                {"success": False, "error": "platform 파라미터는 'twitter' 또는 'reddit' 이어야 합니다."}
            ), 400

        if not SimulationRunner.check_env_alive(simulation_id):
            return jsonify({"success": False, "error": "시뮬레이션이 실행 중이 아닙니다."}), 400

        result = SimulationRunner.interview_agent(
            simulation_id=simulation_id,
            agent_id=agent_id,
            prompt=optimize_interview_prompt(prompt),
            platform=platform,
            timeout=timeout,
        )

        return jsonify({"success": result.get("success", False), "data": result})

    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    except TimeoutError as e:
        return jsonify({"success": False, "error": f"Interview timeout: {str(e)}"}), 504
    except Exception as e:
        logger.error(f"Interview 실행 실패: {str(e)}")
        return jsonify(
            {"success": False, "error": str(e), "traceback": traceback.format_exc()}
        ), 500


@simulation_bp.route("/interview/batch", methods=["POST"])
def interview_agents_batch():
    try:
        data = request.get_json() or {}

        simulation_id = data.get("simulation_id")
        interviews = data.get("interviews")
        platform = data.get("platform")
        timeout = data.get("timeout", 120)

        if not simulation_id:
            return jsonify({"success": False, "error": "simulation_id를 입력해 주세요."}), 400

        if not interviews or not isinstance(interviews, list):
            return jsonify({"success": False, "error": "interviews를 배열로 입력해 주세요."}), 400

        if platform and platform not in ("twitter", "reddit"):
            return jsonify(
                {"success": False, "error": "platform 파라미터는 'twitter' 또는 'reddit' 이어야 합니다."}
            ), 400

        optimized_interviews = []
        for index, interview in enumerate(interviews, start=1):
            if "agent_id" not in interview:
                return jsonify(
                    {"success": False, "error": f"interviews[{index}]에 agent_id가 없습니다."}
                ), 400
            if "prompt" not in interview:
                return jsonify(
                    {"success": False, "error": f"interviews[{index}]에 prompt가 없습니다."}
                ), 400

            item_platform = interview.get("platform")
            if item_platform and item_platform not in ("twitter", "reddit"):
                return jsonify(
                    {
                        "success": False,
                        "error": f"interviews[{index}]의 platform은 'twitter' 또는 'reddit' 이어야 합니다.",
                    }
                ), 400

            optimized_interview = interview.copy()
            optimized_interview["prompt"] = optimize_interview_prompt(interview.get("prompt", ""))
            optimized_interviews.append(optimized_interview)

        if not SimulationRunner.check_env_alive(simulation_id):
            return jsonify({"success": False, "error": "시뮬레이션이 실행 중이 아닙니다."}), 400

        result = SimulationRunner.interview_agents_batch(
            simulation_id=simulation_id,
            interviews=optimized_interviews,
            platform=platform,
            timeout=timeout,
        )

        return jsonify({"success": result.get("success", False), "data": result})

    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    except TimeoutError as e:
        return jsonify({"success": False, "error": f"Interview timeout: {str(e)}"}), 504
    except Exception as e:
        logger.error(f"Batch interview 실행 실패: {str(e)}")
        return jsonify(
            {"success": False, "error": str(e), "traceback": traceback.format_exc()}
        ), 500


@simulation_bp.route("/interview/all", methods=["POST"])
def interview_all_agents():
    try:
        data = request.get_json() or {}

        simulation_id = data.get("simulation_id")
        prompt = data.get("prompt")
        platform = data.get("platform")
        timeout = data.get("timeout", 180)

        if not simulation_id:
            return jsonify({"success": False, "error": "simulation_id를 입력해 주세요."}), 400

        if not prompt:
            return jsonify({"success": False, "error": "prompt를 입력해 주세요."}), 400

        if platform and platform not in ("twitter", "reddit"):
            return jsonify(
                {"success": False, "error": "platform 파라미터는 'twitter' 또는 'reddit' 이어야 합니다."}
            ), 400

        if not SimulationRunner.check_env_alive(simulation_id):
            return jsonify({"success": False, "error": "시뮬레이션이 실행 중이 아닙니다."}), 400

        result = SimulationRunner.interview_all_agents(
            simulation_id=simulation_id,
            prompt=optimize_interview_prompt(prompt),
            platform=platform,
            timeout=timeout,
        )

        return jsonify({"success": result.get("success", False), "data": result})

    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    except TimeoutError as e:
        return jsonify({"success": False, "error": f"Interview timeout: {str(e)}"}), 504
    except Exception as e:
        logger.error(f"Interview all 실행 실패: {str(e)}")
        return jsonify(
            {"success": False, "error": str(e), "traceback": traceback.format_exc()}
        ), 500


@simulation_bp.route("/interview/history", methods=["POST"])
def get_interview_history():
    try:
        data = request.get_json() or {}

        simulation_id = data.get("simulation_id")
        platform = data.get("platform")
        agent_id = data.get("agent_id")
        limit = data.get("limit", 100)

        if not simulation_id:
            return jsonify({"success": False, "error": "simulation_id를 입력해 주세요."}), 400

        history = SimulationRunner.get_interview_history(
            simulation_id=simulation_id,
            platform=platform,
            agent_id=agent_id,
            limit=limit,
        )

        return jsonify({"success": True, "data": {"count": len(history), "history": history}})

    except Exception as e:
        logger.error(f"Interview history 조회 실패: {str(e)}")
        return jsonify(
            {"success": False, "error": str(e), "traceback": traceback.format_exc()}
        ), 500


@simulation_bp.route("/env-status", methods=["POST"])
def get_env_status():
    try:
        data = request.get_json() or {}

        simulation_id = data.get("simulation_id")
        if not simulation_id:
            return jsonify({"success": False, "error": "simulation_id를 입력해 주세요."}), 400

        env_alive = SimulationRunner.check_env_alive(simulation_id)
        env_status = SimulationRunner.get_env_status_detail(simulation_id)
        message = "실행 중, Interview 가능" if env_alive else "실행 종료"

        return jsonify(
            {
                "success": True,
                "data": {
                    "simulation_id": simulation_id,
                    "env_alive": env_alive,
                    "twitter_available": env_status.get("twitter_available", False),
                    "reddit_available": env_status.get("reddit_available", False),
                    "message": message,
                },
            }
        )

    except Exception as e:
        logger.error(f"환경 상태 조회 실패: {str(e)}")
        return jsonify(
            {"success": False, "error": str(e), "traceback": traceback.format_exc()}
        ), 500


@simulation_bp.route("/close-env", methods=["POST"])
def close_simulation_env():
    try:
        data = request.get_json() or {}

        simulation_id = data.get("simulation_id")
        timeout = data.get("timeout", 30)

        if not simulation_id:
            return jsonify({"success": False, "error": "simulation_id를 입력해 주세요."}), 400

        result = SimulationRunner.close_simulation_env(
            simulation_id=simulation_id,
            timeout=timeout,
        )

        manager = SimulationManager()
        state = manager.get_simulation(simulation_id)
        if state:
            state.status = SimulationStatus.COMPLETED
            manager._save_simulation_state(state)

        return jsonify({"success": result.get("success", False), "data": result})

    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    except Exception as e:
        logger.error(f"환경 종료 실패: {str(e)}")
        return jsonify(
            {"success": False, "error": str(e), "traceback": traceback.format_exc()}
        ), 500
