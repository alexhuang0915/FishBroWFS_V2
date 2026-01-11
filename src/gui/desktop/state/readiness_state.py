"""
Single Source of Truth (SSOT) readiness model for Desktop UI.

Computes missing prerequisites and reasons for UI actions.
Pure function that returns a dict of missing keys and human-readable reasons.
"""

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
from pathlib import Path

from ...services.supervisor_client import check_readiness, health, get_registry_strategies, SupervisorClientError
from config.registry.timeframes import load_timeframes

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ReadyState:
    """Immutable readiness state."""
    # Overall ready flag (all prerequisites satisfied)
    ready: bool
    # Missing prerequisites as dict key -> reason
    missing: Dict[str, str]
    # Human-readable summary
    summary: str


def compute_ready_state(
    primary_market: Optional[str] = None,
    timeframe: Optional[str] = None,
    season: Optional[str] = None,
    strategy_id: Optional[str] = None,
) -> ReadyState:
    """
    Compute readiness state for given parameters.
    
    Prerequisites checked:
    1. Supervisor health (API reachable)
    2. Bars data ready (if primary_market, timeframe, season provided)
    3. Features data ready (if primary_market, timeframe, season provided)
    4. Registry has strategies (if strategy_id needed)
    5. Timeframe valid (if timeframe provided)
    
    Returns ReadyState with missing dict and summary.
    """
    missing = {}
    
    # 1. Supervisor health
    try:
        health_result = health()
        if not health_result.get("ok", False):
            missing["supervisor"] = "Supervisor unhealthy"
    except Exception as e:
        missing["supervisor"] = f"Supervisor unreachable: {e}"
    
    # 2 & 3. Bars and features readiness (if we have enough parameters)
    if primary_market and timeframe and season:
        try:
            readiness = check_readiness(season, primary_market, timeframe)
            if not readiness.get("bars_ready", False):
                missing["bars"] = "Bars data not ready"
            if not readiness.get("features_ready", False):
                missing["features"] = "Features data not ready"
        except SupervisorClientError as e:
            missing["readiness_api"] = f"Readiness API error: {e}"
        except Exception as e:
            missing["readiness_api"] = f"Unexpected error checking readiness: {e}"
    else:
        # Not enough parameters to check bars/features
        missing["parameters"] = "Missing primary_market, timeframe, or season"
    
    # 4. Registry strategies (if strategy_id needed)
    if strategy_id:
        try:
            strategies = get_registry_strategies()
            if not strategies:
                missing["registry"] = "No strategies in registry"
            else:
                # Check if strategy_id exists
                strategy_ids = [s.get("id") for s in strategies if isinstance(s, dict)]
                if strategy_id not in strategy_ids:
                    missing["strategy"] = f"Strategy '{strategy_id}' not found in registry"
        except SupervisorClientError as e:
            missing["registry"] = f"Registry API error: {e}"
        except Exception as e:
            missing["registry"] = f"Unexpected error fetching registry: {e}"
    
    # 5. Timeframe validity (if timeframe provided)
    if timeframe:
        try:
            timeframe_registry = load_timeframes()
            # timeframe is string like "15m", "60m"
            # Parse minutes
            if timeframe.endswith("m"):
                minutes = int(timeframe[:-1])
            elif timeframe.endswith("h"):
                minutes = int(timeframe[:-1]) * 60
            else:
                # assume minutes integer
                minutes = int(timeframe)
            if minutes not in timeframe_registry.allowed_timeframes:
                missing["timeframe"] = f"Timeframe '{timeframe}' not in allowed list"
        except Exception as e:
            missing["timeframe"] = f"Could not validate timeframe: {e}"
    
    # Determine overall ready flag
    ready = len(missing) == 0
    
    # Build summary
    if ready:
        summary = "All prerequisites satisfied"
    else:
        missing_list = [f"{k}: {v}" for k, v in missing.items()]
        summary = f"Missing prerequisites: {', '.join(missing_list)}"
    
    return ReadyState(ready=ready, missing=missing, summary=summary)


def compute_ui_ready_state(
    primary_market: Optional[str] = None,
    timeframe: Optional[str] = None,
    season: Optional[str] = None,
    strategy_id: Optional[str] = None,
) -> Tuple[bool, str, Dict[str, str]]:
    """
    Convenience wrapper for UI consumption.
    
    Returns:
        (is_ready, tooltip_text, missing_dict)
    """
    state = compute_ready_state(primary_market, timeframe, season, strategy_id)
    if state.ready:
        tooltip = "Ready to run"
    else:
        # Build tooltip with bullet points
        lines = ["Missing prerequisites:"]
        for key, reason in state.missing.items():
            lines.append(f"• {key}: {reason}")
        tooltip = "\n".join(lines)
    return state.ready, tooltip, state.missing


# Example usage:
# ready, tooltip, missing = compute_ui_ready_state("ES", "15m", "2026Q1", "my_strategy")
# if not ready:
#     button.setEnabled(False)
#     button.setToolTip(tooltip)
#     button.setStyleSheet("...disabled style...")