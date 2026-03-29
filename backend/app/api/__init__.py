"""
API route modules.
"""

from flask import Blueprint

from .simulation import simulation_bp

graph_bp = Blueprint("graph", __name__)
report_bp = Blueprint("report", __name__)

from . import graph  # noqa: E402, F401
from . import report  # noqa: E402, F401
