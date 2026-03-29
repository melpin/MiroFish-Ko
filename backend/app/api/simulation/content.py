"""
Content retrieval routes for the simulation API blueprint.
"""

import os
import sqlite3
import traceback

from flask import jsonify, request

from .blueprint import simulation_bp
from ...utils.logger import get_logger

logger = get_logger("mirofish.api.simulation.content")


def _get_simulation_dir(simulation_id: str) -> str:
    return os.path.join(
        os.path.dirname(__file__),
        f"../../../uploads/simulations/{simulation_id}",
    )


@simulation_bp.route("/<simulation_id>/posts", methods=["GET"])
def get_simulation_posts(simulation_id: str):
    try:
        platform = request.args.get("platform", "reddit")
        limit = request.args.get("limit", 50, type=int)
        offset = request.args.get("offset", 0, type=int)

        db_path = os.path.join(_get_simulation_dir(simulation_id), f"{platform}_simulation.db")
        if not os.path.exists(db_path):
            return jsonify(
                {
                    "success": True,
                    "data": {
                        "platform": platform,
                        "count": 0,
                        "posts": [],
                        "message": "DB가 아직 없어서 게시물을 조회할 수 없습니다.",
                    },
                }
            )

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        try:
            cursor.execute(
                """
                SELECT * FROM post
                ORDER BY created_at DESC
                LIMIT ? OFFSET ?
                """,
                (limit, offset),
            )
            posts = [dict(row) for row in cursor.fetchall()]

            cursor.execute("SELECT COUNT(*) FROM post")
            total = cursor.fetchone()[0]
        except sqlite3.OperationalError:
            posts = []
            total = 0
        finally:
            conn.close()

        return jsonify(
            {
                "success": True,
                "data": {
                    "platform": platform,
                    "total": total,
                    "count": len(posts),
                    "posts": posts,
                },
            }
        )

    except Exception as e:
        logger.error(f"게시물 조회 실패: {str(e)}")
        return jsonify(
            {"success": False, "error": str(e), "traceback": traceback.format_exc()}
        ), 500


@simulation_bp.route("/<simulation_id>/comments", methods=["GET"])
def get_simulation_comments(simulation_id: str):
    try:
        post_id = request.args.get("post_id")
        limit = request.args.get("limit", 50, type=int)
        offset = request.args.get("offset", 0, type=int)

        db_path = os.path.join(_get_simulation_dir(simulation_id), "reddit_simulation.db")
        if not os.path.exists(db_path):
            return jsonify({"success": True, "data": {"count": 0, "comments": []}})

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        try:
            if post_id:
                cursor.execute(
                    """
                    SELECT * FROM comment
                    WHERE post_id = ?
                    ORDER BY created_at DESC
                    LIMIT ? OFFSET ?
                    """,
                    (post_id, limit, offset),
                )
            else:
                cursor.execute(
                    """
                    SELECT * FROM comment
                    ORDER BY created_at DESC
                    LIMIT ? OFFSET ?
                    """,
                    (limit, offset),
                )
            comments = [dict(row) for row in cursor.fetchall()]
        except sqlite3.OperationalError:
            comments = []
        finally:
            conn.close()

        return jsonify({"success": True, "data": {"count": len(comments), "comments": comments}})

    except Exception as e:
        logger.error(f"댓글 조회 실패: {str(e)}")
        return jsonify(
            {"success": False, "error": str(e), "traceback": traceback.format_exc()}
        ), 500
