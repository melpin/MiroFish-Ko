"""
API route modules.
"""

from flask import Blueprint

from .simulation import simulation_bp
from .report import report_bp

graph_bp = Blueprint("graph", __name__)

from . import graph  # noqa: E402, F401
