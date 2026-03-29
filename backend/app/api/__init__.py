"""
API route modules.
"""

from flask import Blueprint

from .simulation import simulation_bp

graph_bp = Blueprint("graph", __name__)
report_bp = Blueprint("report", __name__)

from . import graph  # noqa: E402, F401
from . import simulation_assets  # noqa: E402, F401
from . import simulation_content  # noqa: E402, F401
from . import simulation_entities  # noqa: E402, F401
from . import simulation_execution  # noqa: E402, F401
from . import simulation_generation  # noqa: E402, F401
from . import simulation_interviews  # noqa: E402, F401
from . import simulation_listing  # noqa: E402, F401
from . import simulation_runtime  # noqa: E402, F401
from . import report  # noqa: E402, F401
