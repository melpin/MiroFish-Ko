"""
API route modules.
"""

from flask import Blueprint

from .simulation import simulation_bp
from .report import report_bp
from .graph import graph_bp
