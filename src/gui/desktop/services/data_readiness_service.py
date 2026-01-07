"""
Data Readiness Service for Desktop UI - checks if bars and features are ready.

Implements API calls to supervisor (dumb client). No filesystem reads.
"""

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Readiness:
    """Data readiness status."""
    bars_ready: bool
    features_ready: bool
    bars_reason: str
    features_reason: str


def check_bars(
    primary_market: str,
    timeframe: int,
    season: str,
    outputs_root: Optional[Path] = None  # kept for backward compatibility, ignored
) -> tuple[bool, str]:
    """
    Check if bars data is ready via API.
    
    Returns (ready, reason) where reason is a human-readable string.
    """
    try:
        from gui.services.supervisor_client import check_readiness
        response = check_readiness(season, primary_market, f"{timeframe}m")
        bars_ready = response.get("bars_ready", False)
        bars_path = response.get("bars_path")
        if bars_ready:
            return True, f"Bars ready at {bars_path}" if bars_path else "Bars ready"
        else:
            return False, "Bars not ready (missing)"
    except Exception as e:
        logger.error(f"Error checking bars via API: {e}")
        return False, f"API error: {e}"


def check_features(
    primary_market: str,
    timeframe: int,
    season: str,
    outputs_root: Optional[Path] = None
) -> tuple[bool, str]:
    """
    Check if features data is ready via API.
    """
    try:
        from gui.services.supervisor_client import check_readiness
        response = check_readiness(season, primary_market, f"{timeframe}m")
        features_ready = response.get("features_ready", False)
        features_path = response.get("features_path")
        if features_ready:
            return True, f"Features ready at {features_path}" if features_path else "Features ready"
        else:
            return False, "Features not ready (missing)"
    except Exception as e:
        logger.error(f"Error checking features via API: {e}")
        return False, f"API error: {e}"


def check_all(
    primary_market: str,
    timeframe: int,
    season: str,
    outputs_root: Optional[Path] = None
) -> Readiness:
    """Check both bars and features readiness via a single API call."""
    try:
        from gui.services.supervisor_client import check_readiness
        response = check_readiness(season, primary_market, f"{timeframe}m")
        bars_ready = response.get("bars_ready", False)
        features_ready = response.get("features_ready", False)
        bars_reason = "Bars ready" if bars_ready else "Bars not ready"
        features_reason = "Features ready" if features_ready else "Features not ready"
        return Readiness(
            bars_ready=bars_ready,
            features_ready=features_ready,
            bars_reason=bars_reason,
            features_reason=features_reason
        )
    except Exception as e:
        logger.error(f"Error checking readiness via API: {e}")
        return Readiness(
            bars_ready=False,
            features_ready=False,
            bars_reason=f"API error: {e}",
            features_reason=f"API error: {e}"
        )