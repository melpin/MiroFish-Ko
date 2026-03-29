"""
Entity lookup routes for the simulation API blueprint.
"""

import traceback

from flask import jsonify, request

from .simulation import simulation_bp
from ..config import Config
from ..services.zep_entity_reader import ZepEntityReader
from ..utils.logger import get_logger

logger = get_logger("mirofish.api.simulation.entities")


@simulation_bp.route("/entities/<graph_id>", methods=["GET"])
def get_graph_entities(graph_id: str):
    try:
        if not Config.ZEP_API_KEY:
            return jsonify({"success": False, "error": "ZEP_API_KEY?ㅼ젙"}), 500

        entity_types_str = request.args.get("entity_types", "")
        entity_types = [t.strip() for t in entity_types_str.split(",") if t.strip()] if entity_types_str else None
        enrich = request.args.get("enrich", "true").lower() == "true"

        logger.info(f"洹몃옒?꾩뿏?고떚: graph_id={graph_id}, entity_types={entity_types}, enrich={enrich}")

        reader = ZepEntityReader()
        result = reader.filter_defined_entities(
            graph_id=graph_id,
            defined_entity_types=entity_types,
            enrich_with_edges=enrich,
        )

        return jsonify({"success": True, "data": result.to_dict()})

    except Exception as e:
        logger.error(f"洹몃옒?꾩뿏?고떚?ㅽ뙣: {str(e)}")
        return jsonify(
            {"success": False, "error": str(e), "traceback": traceback.format_exc()}
        ), 500


@simulation_bp.route("/entities/<graph_id>/<entity_uuid>", methods=["GET"])
def get_entity_detail(graph_id: str, entity_uuid: str):
    try:
        if not Config.ZEP_API_KEY:
            return jsonify({"success": False, "error": "ZEP_API_KEY?ㅼ젙"}), 500

        reader = ZepEntityReader()
        entity = reader.get_entity_with_context(graph_id, entity_uuid)

        if not entity:
            return jsonify(
                {
                    "success": False,
                    "error": f"?뷀꽣?곌? 議댁옱?섏? ?딆뒿?덈떎: {entity_uuid}",
                }
            ), 404

        return jsonify({"success": True, "data": entity.to_dict()})

    except Exception as e:
        logger.error(f"?뷀꽣?곗떎?? {str(e)}")
        return jsonify(
            {"success": False, "error": str(e), "traceback": traceback.format_exc()}
        ), 500


@simulation_bp.route("/entities/<graph_id>/by-type/<entity_type>", methods=["GET"])
def get_entities_by_type(graph_id: str, entity_type: str):
    try:
        if not Config.ZEP_API_KEY:
            return jsonify({"success": False, "error": "ZEP_API_KEY?ㅼ젙"}), 500

        enrich = request.args.get("enrich", "true").lower() == "true"

        reader = ZepEntityReader()
        entities = reader.get_entities_by_type(
            graph_id=graph_id,
            entity_type=entity_type,
            enrich_with_edges=enrich,
        )

        return jsonify(
            {
                "success": True,
                "data": {
                    "entity_type": entity_type,
                    "count": len(entities),
                    "entities": [e.to_dict() for e in entities],
                },
            }
        )

    except Exception as e:
        logger.error(f"?뷀꽣?곗떎?? {str(e)}")
        return jsonify(
            {"success": False, "error": str(e), "traceback": traceback.format_exc()}
        ), 500
