import json
import os
from datetime import datetime

from ...config import Config
from ...prompts import get_prompt
from ...utils.logger import get_logger

logger = get_logger("mirofish.api.simulation")

INTERVIEW_PROMPT_PREFIX = get_prompt("simulation.interview_prompt_prefix")


def optimize_interview_prompt(prompt: str) -> str:
    if not prompt:
        return prompt
    if prompt.startswith(INTERVIEW_PROMPT_PREFIX):
        return prompt
    return f"{INTERVIEW_PROMPT_PREFIX}{prompt}"


def check_simulation_prepared(simulation_id: str) -> tuple[bool, dict]:
    simulation_dir = os.path.join(Config.OASIS_SIMULATION_DATA_DIR, simulation_id)
    if not os.path.exists(simulation_dir):
        return False, {"reason": "시뮬레이션 디렉터리가 존재하지 않습니다."}

    required_files = [
        "state.json",
        "simulation_config.json",
        "reddit_profiles.json",
        "twitter_profiles.csv",
    ]
    existing_files = []
    missing_files = []
    for filename in required_files:
        file_path = os.path.join(simulation_dir, filename)
        if os.path.exists(file_path):
            existing_files.append(filename)
        else:
            missing_files.append(filename)

    if missing_files:
        return False, {
            "reason": "필수 파일이 누락되었습니다.",
            "missing_files": missing_files,
            "existing_files": existing_files,
        }

    state_file = os.path.join(simulation_dir, "state.json")
    try:
        with open(state_file, "r", encoding="utf-8") as file:
            state_data = json.load(file)
    except Exception as e:
        return False, {"reason": f"state.json 읽기 실패: {str(e)}"}

    status = state_data.get("status", "")
    config_generated = state_data.get("config_generated", False)
    logger.debug(
        f"시뮬레이션 상태 확인: simulation_id={simulation_id}, status={status}, "
        f"config_generated={config_generated}"
    )

    prepared_statuses = {"ready", "preparing", "running", "completed", "stopped", "failed"}
    if status not in prepared_statuses or not config_generated:
        return False, {
            "reason": f"준비되지 않은 상태입니다: status={status}, config_generated={config_generated}",
            "status": status,
            "config_generated": config_generated,
        }

    profiles_file = os.path.join(simulation_dir, "reddit_profiles.json")
    profiles_count = 0
    if os.path.exists(profiles_file):
        with open(profiles_file, "r", encoding="utf-8") as file:
            profiles_data = json.load(file)
        if isinstance(profiles_data, list):
            profiles_count = len(profiles_data)

    if status == "preparing":
        try:
            state_data["status"] = "ready"
            state_data["updated_at"] = datetime.now().isoformat()
            with open(state_file, "w", encoding="utf-8") as file:
                json.dump(state_data, file, ensure_ascii=False, indent=2)
            status = "ready"
            logger.info(f"시뮬레이션 상태 자동 보정: {simulation_id} preparing -> ready")
        except Exception as e:
            logger.warning(f"시뮬레이션 상태 보정 실패: {e}")

    return True, {
        "status": status,
        "entities_count": state_data.get("entities_count", 0),
        "profiles_count": profiles_count,
        "entity_types": state_data.get("entity_types", []),
        "config_generated": config_generated,
        "created_at": state_data.get("created_at"),
        "updated_at": state_data.get("updated_at"),
        "existing_files": existing_files,
    }
