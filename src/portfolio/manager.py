"""
Portfolio Manager orchestrator.

Wires State Machine + Gatekeeper + Allocator into one enforceable governance flow.
"""
from __future__ import annotations

from typing import Dict, Optional
import pandas as pd

from portfolio.governance_state import (
    StrategyRecord,
    StrategyState,
    GovernanceStateMachine,
    transition_strategy,
)
from portfolio.gatekeeper import AdmissionGate, AdmissionResult
from portfolio.allocator import RiskParityAllocator


class PortfolioManager:
    """
    Orchestrates portfolio governance lifecycle.

    Maintains:
    - strategies: dict[str, StrategyRecord] (in‑memory store)
    - portfolio_returns: Optional[pd.Series] (reference series for correlation gate)
    """

    def __init__(self) -> None:
        self.strategies: Dict[str, StrategyRecord] = {}
        self.portfolio_returns: Optional[pd.Series] = None

    def onboard_strategy(self, record: StrategyRecord) -> None:
        """
        Register a new strategy.

        Raises:
            ValueError: if strategy_id already exists
            ValueError: if initial state is not INCUBATION
        """
        if record.strategy_id in self.strategies:
            raise ValueError(
                f"Strategy {record.strategy_id} already onboarded"
            )
        if record.state != StrategyState.INCUBATION:
            raise ValueError(
                f"New strategy must be in INCUBATION state, got {record.state}"
            )
        self.strategies[record.strategy_id] = record

    def request_admission(
        self, strategy_id: str, candidate_returns: pd.Series
    ) -> AdmissionResult:
        """
        Request admission for a strategy (correlation gate).

        Steps:
          1. Validate strategy exists and is in INCUBATION.
          2. Call AdmissionGate.check_correlation.
          3. If allowed, attempt state transition INCUBATION → CANDIDATE.
          4. If transition fails, override result to denied.
          5. Return AdmissionResult.

        Raises:
            ValueError: if strategy_id unknown
        """
        if strategy_id not in self.strategies:
            raise ValueError(f"Unknown strategy {strategy_id}")

        record = self.strategies[strategy_id]
        if record.state != StrategyState.INCUBATION:
            # Gatekeeper may still be called, but transition will be blocked.
            pass

        # Call gatekeeper
        result = AdmissionGate.check_correlation(
            candidate_returns=candidate_returns,
            portfolio_returns=self.portfolio_returns,
            threshold=0.7,
            min_overlap=30,
        )

        # If gatekeeper allows, attempt state promotion
        if result.allowed:
            try:
                # Ensure transition is allowed by state machine
                GovernanceStateMachine.assert_transition(
                    from_state=record.state,
                    to_state=StrategyState.CANDIDATE,
                )
                # Apply transition
                new_record = transition_strategy(
                    record, to_state=StrategyState.CANDIDATE
                )
                self.strategies[strategy_id] = new_record
            except ValueError as e:
                # Transition not allowed (e.g., already beyond INCUBATION)
                result = AdmissionResult(
                    allowed=False,
                    correlation=result.correlation,
                    reason=f"State Machine Violation: {e}",
                )

        return result

    def activate_strategy(self, strategy_id: str) -> None:
        """
        Promote a CANDIDATE strategy to LIVE via PAPER_TRADING.

        Raises:
            ValueError: if strategy_id unknown
            ValueError: if transition CANDIDATE → PAPER_TRADING or PAPER_TRADING → LIVE is not allowed
        """
        if strategy_id not in self.strategies:
            raise ValueError(f"Unknown strategy {strategy_id}")

        record = self.strategies[strategy_id]
        # First transition: CANDIDATE → PAPER_TRADING
        record = transition_strategy(record, to_state=StrategyState.PAPER_TRADING)
        # Second transition: PAPER_TRADING → LIVE
        new_record = transition_strategy(record, to_state=StrategyState.LIVE)
        self.strategies[strategy_id] = new_record

    def rebalance_portfolio(
        self, total_capital: float = 1.0
    ) -> Dict[str, float]:
        """
        Compute allocations for LIVE strategies using RiskParityAllocator.

        Returns:
            Dict mapping strategy_id → allocated capital.
            Empty dict if no LIVE strategies.
        """
        live_records = [
            record
            for record in self.strategies.values()
            if record.state == StrategyState.LIVE
        ]
        if not live_records:
            return {}

        return RiskParityAllocator.allocate(
            strategies=live_records,
            total_capital=total_capital,
        )

    def update_portfolio_history(self, new_returns: pd.Series) -> None:
        """
        Update the portfolio reference returns series.

        If portfolio_returns is None, set to new_returns.
        Otherwise, concatenate and deduplicate by index (keep last).
        """
        if self.portfolio_returns is None:
            self.portfolio_returns = new_returns.copy()
            return

        # Concatenate, sort by index, keep last observation for duplicate indices
        combined = pd.concat(
            [self.portfolio_returns, new_returns]
        ).sort_index()
        # Deduplicate: keep last observation per index
        self.portfolio_returns = combined[~combined.index.duplicated(keep="last")]