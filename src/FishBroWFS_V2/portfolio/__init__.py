"""Portfolio package exports.

Single source of truth: PortfolioSpec in spec.py
Phase 11 research bridge uses PortfolioSpec (no spec split).
"""

from __future__ import annotations

from FishBroWFS_V2.portfolio.decisions_reader import parse_decisions_log_lines, read_decisions_log
from FishBroWFS_V2.portfolio.research_bridge import build_portfolio_from_research
from FishBroWFS_V2.portfolio.spec import PortfolioLeg, PortfolioSpec
from FishBroWFS_V2.portfolio.writer import write_portfolio_artifacts

__all__ = [
    "PortfolioLeg",
    "PortfolioSpec",
    "parse_decisions_log_lines",
    "read_decisions_log",
    "build_portfolio_from_research",
    "write_portfolio_artifacts",
]