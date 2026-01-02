"""
Article IV.3 Risk Budgeting - Naive Risk Parity (Inverse Volatility Weighting).

Implements the RiskParityAllocator class for deterministic allocation based on
inverse volatility with a minimum volatility floor.
"""
from __future__ import annotations
from typing import Dict, List
import logging
import math

from portfolio.governance_state import StrategyRecord

logger = logging.getLogger(__name__)


class RiskParityAllocator:
    """Article IV.3 Risk Budgeting - Naive Risk Parity (Inverse Volatility)."""

    MIN_VOL_FLOOR: float = 0.02

    @classmethod
    def allocate(cls, strategies: List[StrategyRecord], total_capital: float = 1.0) -> Dict[str, float]:
        """
        Compute risk‑parity allocations using inverse volatility weighting.

        Args:
            strategies: List of StrategyRecord instances.
            total_capital: Total capital to allocate (default 1.0).

        Returns:
            Dict mapping each strategy_id to its allocated capital.
            Invalid strategies (missing/NaN/≤0 volatility) receive 0.0.
            Empty input returns empty dict.
        """
        if not strategies:
            return {}

        inv: Dict[str, float] = {}
        out: Dict[str, float] = {}

        # Pre-fill outputs with zeros (explicitness for reporting)
        for s in strategies:
            out[s.strategy_id] = 0.0

        # Compute inverse vol for valid strategies
        for s in strategies:
            sid = s.strategy_id
            vol = None
            try:
                vol = s.metrics.get("volatility", None) if getattr(s, "metrics", None) is not None else None
            except Exception:
                vol = None

            # invalid handling
            if vol is None:
                logger.warning("RiskParityAllocator: strategy %s missing/invalid volatility=%r; allocation forced to 0", sid, vol)
                continue
            if isinstance(vol, float) and math.isnan(vol):
                logger.warning("RiskParityAllocator: strategy %s missing/invalid volatility=%r; allocation forced to 0", sid, vol)
                continue
            try:
                vol_f = float(vol)
            except Exception:
                logger.warning("RiskParityAllocator: strategy %s missing/invalid volatility=%r; allocation forced to 0", sid, vol)
                continue
            if vol_f <= 0:
                logger.warning("RiskParityAllocator: strategy %s missing/invalid volatility=%r; allocation forced to 0", sid, vol_f)
                continue

            safe_vol = max(vol_f, cls.MIN_VOL_FLOOR)
            inv[sid] = 1.0 / safe_vol

        denom = sum(inv.values())
        if denom <= 0:
            return out

        for sid, invv in inv.items():
            w = invv / denom
            out[sid] = w * float(total_capital)

        return out