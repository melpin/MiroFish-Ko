"""
Profile generation routes for the simulation API blueprint.
"""

import traceback

from flask import jsonify, request

from .blueprint import simulation_bp
from ...services.oasis import OasisProfileGenerator
from ...services.zep import ZepEntityReader
from ...utils.logger import get_logger

logger = get_logger("mirofish.api.simulation.generation")


@simulation_bp.route("/generate-profiles", methods=["POST"])
def generate_profiles():
    try:
        data = request.get_json() or {}

        graph_id = data.get("graph_id")
        if not graph_id:
            return jsonify({"success": False, "error": "graph_id를 입력해 주세요."}), 400

        entity_types = data.get("entity_types")
        use_llm = data.get("use_llm", True)
        platform = data.get("platform", "reddit")

        reader = ZepEntityReader()
        filtered = reader.filter_defined_entities(
            graph_id=graph_id,
            defined_entity_types=entity_types,
            enrich_with_edges=True,
        )

        if filtered.filtered_count == 0:
            return jsonify({"success": False, "error": "조건에 맞는 엔터티를 찾지 못했습니다."}), 400

        generator = OasisProfileGenerator()
        profiles = generator.generate_profiles_from_entities(
            entities=filtered.entities,
            use_llm=use_llm,
        )

        if platform == "reddit":
            profiles_data = [profile.to_reddit_format() for profile in profiles]
        elif platform == "twitter":
            profiles_data = [profile.to_twitter_format() for profile in profiles]
        else:
            profiles_data = [profile.to_dict() for profile in profiles]

        return jsonify(
            {
                "success": True,
                "data": {
                    "platform": platform,
                    "entity_types": list(filtered.entity_types),
                    "count": len(profiles_data),
                    "profiles": profiles_data,
                },
            }
        )

    except Exception as e:
        logger.error(f"프로필 생성 실패: {str(e)}")
        return jsonify(
            {"success": False, "error": str(e), "traceback": traceback.format_exc()}
        ), 500
