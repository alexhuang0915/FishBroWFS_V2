
"""Portfolio package exports.

Single source of truth: PortfolioSpec in spec.py
Phase 11 research bridge uses PortfolioSpec (no spec split).
"""

from __future__ import annotations

from portfolio.decisions_reader import parse_decisions_log_lines, read_decisions_log
from portfolio.research_bridge import build_portfolio_from_research
from portfolio.spec import PortfolioLeg, PortfolioSpec
from portfolio.writer import write_portfolio_artifacts

__all__ = [
    "PortfolioLeg",
    "PortfolioSpec",
    "parse_decisions_log_lines",
    "read_decisions_log",
    "build_portfolio_from_research",
    "write_portfolio_artifacts",
]


