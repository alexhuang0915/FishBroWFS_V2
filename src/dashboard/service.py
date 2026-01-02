"""
Dashboard Service Bridge (Phase 9‑Alpha).

Provides async wrappers around portfolio governance for NiceGUI/UI calls.
All service actions are async and delegate sync domain logic to threads.
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, Optional, TYPE_CHECKING

import numpy as np
import pandas as pd

if TYPE_CHECKING:
    from portfolio.audit import AuditTrail
    from portfolio.store import PortfolioStore
    from portfolio.manager import PortfolioManager
    from portfolio.governance_state import StrategyRecord

from portfolio.audit import AuditTrail
from portfolio.store import PortfolioStore
from portfolio.manager import PortfolioManager
from portfolio.governance_state import (
    StrategyRecord,
    StrategyState,
    create_strategy_record,
)


class PortfolioService:
    """Service‑layer bridge for portfolio governance."""

    def __init__(self, data_root: str = "outputs/portfolio_store") -> None:
        self.root = Path(data_root)
        self.audit: AuditTrail = AuditTrail(root_dir=str(self.root))
        self.store: PortfolioStore = PortfolioStore(
            root_dir=str(self.root),
            audit=self.audit,
        )
        self.manager: PortfolioManager = PortfolioManager(audit=self.audit)
        self.reload_state()

    def reload_state(self) -> None:
        """Load persisted state into the manager."""
        d = self.store.load_state()
        self.manager.strategies = d["strategies"]
        self.manager.portfolio_returns = d["portfolio_returns"]

    def get_dashboard_state(self, tail_n: int = 50) -> dict:
        """
        Return a JSON‑serializable snapshot of the dashboard.

        Args:
            tail_n: number of most recent audit log lines to include.

        Returns:
            dict with keys:
                - strategies: list of strategy dicts (sorted by priority)
                - total_count: total number of strategies
                - live_count: number of LIVE strategies
                - audit_log: list of recent audit events (newest first)
                - updated_at: ISO timestamp of last state load
        """
        # Convert strategies to JSON‑serializable dicts
        strategies_list = []
        for record in self.manager.strategies.values():
            # Use model_dump(mode="json") for Pydantic v2
            if hasattr(record, "model_dump"):
                d = record.model_dump(mode="json")
            else:
                d = record.dict()
            strategies_list.append(d)

        # Sort by state priority: LIVE(0), CANDIDATE(1), PAPER_TRADING(2), INCUBATION(3), else(9)
        def priority(state: StrategyState) -> int:
            order = {
                StrategyState.LIVE: 0,
                StrategyState.CANDIDATE: 1,
                StrategyState.PAPER_TRADING: 2,
                StrategyState.INCUBATION: 3,
            }
            return order.get(state, 9)

        strategies_list.sort(key=lambda r: priority(r["state"]))

        # Read audit log
        audit_log = []
        audit_path = self.root / "audit" / "events.jsonl"
        if audit_path.exists():
            lines = []
            try:
                with open(audit_path, "r", encoding="utf-8") as f:
                    lines = f.readlines()
            except (OSError, UnicodeDecodeError):
                lines = []
            # Take last tail_n lines, parse JSON
            for line in lines[-tail_n:]:
                line = line.strip()
                if not line:
                    continue
                try:
                    audit_log.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        # Reverse so newest first
        audit_log.reverse()

        # Count LIVE strategies
        live_count = sum(
            1 for r in self.manager.strategies.values()
            if r.state == StrategyState.LIVE
        )

        return {
            "strategies": strategies_list,
            "total_count": len(self.manager.strategies),
            "live_count": live_count,
            "audit_log": audit_log,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

    async def register_strategy(self, strategy_id: str, config: dict) -> dict:
        """
        Register a new strategy in INCUBATION state.

        Args:
            strategy_id: unique identifier
            config: arbitrary configuration dict

        Returns:
            {"status": "success", "strategy_id": ...}
        """
        def _sync_register() -> dict:
            # Build a version hash (simplified for now)
            # In a real implementation this would be derived from config + source
            version_hash = f"v0_{strategy_id}"
            record = create_strategy_record(
                strategy_id=strategy_id,
                version_hash=version_hash,
                config=config,
                initial_state=StrategyState.INCUBATION,
            )
            self.manager.onboard_strategy(record)
            self.store.save_state(self.manager)
            return {"status": "success", "strategy_id": strategy_id}

        return await asyncio.to_thread(_sync_register)

    async def run_admission(self, strategy_id: str) -> dict:
        """
        Request admission for a strategy (correlation gate).

        Generates deterministic returns for testing.

        Args:
            strategy_id: identifier of an INCUBATION strategy

        Returns:
            AdmissionResult as dict (or error dict).
        """
        def _sync_admission() -> dict:
            # Generate deterministic returns
            # index = pd.date_range("2020-01-01", periods=120, freq="D", tz="UTC")
            # values = numpy with fixed RandomState(0) OR deterministic sine series
            # DO NOT use np.random without fixed seed
            np.random.seed(0)
            periods = 120
            index = pd.date_range("2020-01-01", periods=periods, freq="D", tz="UTC")
            # Use sine + small noise for deterministic series
            t = np.linspace(0, 4 * np.pi, periods)
            values = 0.01 * np.sin(t) + 0.001 * np.random.randn(periods)
            candidate_returns = pd.Series(values, index=index, name="candidate")

            result = self.manager.request_admission(strategy_id, candidate_returns)
            self.store.save_state(self.manager)

            # Convert AdmissionResult to dict
            if hasattr(result, "model_dump"):
                return result.model_dump(mode="json")
            else:
                return {
                    "allowed": result.allowed,
                    "correlation": result.correlation,
                    "reason": result.reason,
                }

        return await asyncio.to_thread(_sync_admission)

    async def activate(self, strategy_id: str) -> dict:
        """
        Promote a CANDIDATE strategy to LIVE via PAPER_TRADING.

        Args:
            strategy_id: identifier of a CANDIDATE strategy

        Returns:
            {"status": "success", "strategy_id": ...}
        """
        def _sync_activate() -> dict:
            self.manager.activate_strategy(strategy_id)
            self.store.save_state(self.manager)
            return {"status": "success", "strategy_id": strategy_id}

        return await asyncio.to_thread(_sync_activate)

    async def run_rebalance(self, total_capital: float = 1.0) -> dict:
        """
        Compute risk‑parity allocations for LIVE strategies.

        Args:
            total_capital: total capital to allocate (default 1.0)

        Returns:
            allocations dict {strategy_id: capital}
        """
        def _sync_rebalance() -> dict:
            allocations = self.manager.rebalance_portfolio(total_capital)
            self.store.snapshot(self.manager, tag="ui_rebalance")
            self.store.save_state(self.manager)
            return allocations

        return await asyncio.to_thread(_sync_rebalance)