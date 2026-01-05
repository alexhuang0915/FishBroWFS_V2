"""
Built-in job handlers for supervisor.
"""

from .ping import ping_handler
from .clean_cache import clean_cache_handler
from .build_data import build_data_handler
from .generate_reports import generate_reports_handler
from .run_research import run_research_handler

__all__ = [
    "ping_handler",
    "clean_cache_handler",
    "build_data_handler",
    "generate_reports_handler",
    "run_research_handler"
]