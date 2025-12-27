"""
Season Context - Single Source of Truth (SSOT) for season management.

Phase 4: Consolidate season management to avoid scattered os.getenv() calls.
"""

import os
from pathlib import Path
from typing import Optional


def current_season() -> str:
    """Return current season from env FISHBRO_CURRENT_SEASON or default '2026Q1'."""
    return os.getenv("FISHBRO_CURRENT_SEASON", "2026Q1")


def outputs_root() -> str:
    """Return outputs root from env FISHBRO_OUTPUTS_ROOT or default 'outputs'."""
    return os.getenv("FISHBRO_OUTPUTS_ROOT", "outputs")


def season_dir(season: Optional[str] = None) -> Path:
    """Return outputs/seasons/{season} as Path object.
    
    Args:
        season: Season identifier (e.g., "2026Q1"). If None, uses current_season().
    
    Returns:
        Path to season directory.
    """
    if season is None:
        season = current_season()
    return Path(outputs_root()) / "seasons" / season


def research_dir(season: Optional[str] = None) -> Path:
    """Return outputs/seasons/{season}/research as Path object."""
    return season_dir(season) / "research"


def portfolio_dir(season: Optional[str] = None) -> Path:
    """Return outputs/seasons/{season}/portfolio as Path object."""
    return season_dir(season) / "portfolio"


def governance_dir(season: Optional[str] = None) -> Path:
    """Return outputs/seasons/{season}/governance as Path object."""
    return season_dir(season) / "governance"


def canonical_results_path(season: Optional[str] = None) -> Path:
    """Return path to canonical_results.json."""
    return research_dir(season) / "canonical_results.json"


def research_index_path(season: Optional[str] = None) -> Path:
    """Return path to research_index.json."""
    return research_dir(season) / "research_index.json"


def portfolio_summary_path(season: Optional[str] = None) -> Path:
    """Return path to portfolio_summary.json."""
    return portfolio_dir(season) / "portfolio_summary.json"


def portfolio_manifest_path(season: Optional[str] = None) -> Path:
    """Return path to portfolio_manifest.json."""
    return portfolio_dir(season) / "portfolio_manifest.json"


# Convenience function for backward compatibility
def get_season_context() -> dict:
    """Return a dict with current season context for debugging/logging."""
    season = current_season()
    root = outputs_root()
    return {
        "season": season,
        "outputs_root": root,
        "season_dir": str(season_dir(season)),
        "research_dir": str(research_dir(season)),
        "portfolio_dir": str(portfolio_dir(season)),
        "governance_dir": str(governance_dir(season)),
    }