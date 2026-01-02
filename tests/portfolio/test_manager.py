"""
Unit tests for PortfolioManager orchestrator.
"""
import pytest
import numpy as np
import pandas as pd

from portfolio.governance_state import (
    StrategyRecord,
    StrategyState,
    create_strategy_record,
)
from portfolio.manager import PortfolioManager


class TestPortfolioManager:
    """Test suite for PortfolioManager."""

    def test_onboard_requires_incubation_and_unique_id(self):
        """onboard_strategy accepts INCUBATION, rejects duplicates and non‑INCUBATION."""
        manager = PortfolioManager()

        # Valid INCUBATION record
        s1 = create_strategy_record(
            strategy_id="S1",
            version_hash="hash1",
            initial_state=StrategyState.INCUBATION,
        )
        manager.onboard_strategy(s1)
        assert "S1" in manager.strategies

        # Duplicate ID raises ValueError
        s1_dup = create_strategy_record(
            strategy_id="S1",
            version_hash="hash2",
            initial_state=StrategyState.INCUBATION,
        )
        with pytest.raises(ValueError, match="already onboarded"):
            manager.onboard_strategy(s1_dup)

        # Non‑INCUBATION raises ValueError
        s2 = create_strategy_record(
            strategy_id="S2",
            version_hash="hash3",
            initial_state=StrategyState.CANDIDATE,
        )
        with pytest.raises(ValueError, match="must be in INCUBATION"):
            manager.onboard_strategy(s2)

    def test_request_admission_genesis_allows_and_promotes_to_candidate(self):
        """When portfolio_returns is None (genesis), admission passes and state becomes CANDIDATE."""
        manager = PortfolioManager()
        assert manager.portfolio_returns is None

        s1 = create_strategy_record(
            strategy_id="S1",
            version_hash="hash1",
            initial_state=StrategyState.INCUBATION,
        )
        manager.onboard_strategy(s1)

        # Create deterministic returns series
        candidate_returns = pd.Series(
            np.linspace(0.0, 1.0, 100),
            index=pd.RangeIndex(start=0, stop=100, step=1),
        )

        result = manager.request_admission("S1", candidate_returns)
        assert result.allowed is True
        assert manager.strategies["S1"].state == StrategyState.CANDIDATE

    def test_activate_promotes_candidate_to_live(self):
        """activate_strategy transitions CANDIDATE → LIVE."""
        manager = PortfolioManager()

        # Start in INCUBATION
        s1 = create_strategy_record(
            strategy_id="S1",
            version_hash="hash1",
            initial_state=StrategyState.INCUBATION,
        )
        manager.onboard_strategy(s1)

        # First admit to become CANDIDATE (genesis passes)
        candidate_returns = pd.Series(
            np.linspace(0.0, 1.0, 100),
            index=pd.RangeIndex(start=0, stop=100, step=1),
        )
        manager.request_admission("S1", candidate_returns)
        assert manager.strategies["S1"].state == StrategyState.CANDIDATE

        # Activate to LIVE
        manager.activate_strategy("S1")
        assert manager.strategies["S1"].state == StrategyState.LIVE

    def test_rebalance_only_allocates_live(self):
        """rebalance_portfolio includes only LIVE strategies."""
        manager = PortfolioManager()

        # S1: LIVE with volatility metric
        s1 = create_strategy_record(
            strategy_id="S1",
            version_hash="hash1",
            initial_state=StrategyState.LIVE,
        )
        s1.metrics["volatility"] = 0.10
        manager.strategies["S1"] = s1  # bypass onboarding for simplicity

        # S2: CANDIDATE with volatility metric (should be ignored)
        s2 = create_strategy_record(
            strategy_id="S2",
            version_hash="hash2",
            initial_state=StrategyState.CANDIDATE,
        )
        s2.metrics["volatility"] = 0.20
        manager.strategies["S2"] = s2

        allocations = manager.rebalance_portfolio(total_capital=1.0)
        # Only S1 should receive allocation
        assert "S1" in allocations
        assert allocations["S1"] > 0.0
        # S2 should not appear (allocator returns only LIVE strategies)
        assert "S2" not in allocations

    def test_request_admission_rejects_high_correlation_and_state_unchanged(self):
        """When candidate correlates highly with portfolio, admission is denied and state stays INCUBATION."""
        manager = PortfolioManager()

        # Set portfolio returns (genesis already passed)
        portfolio_returns = pd.Series(
            np.random.RandomState(42).randn(100),
            index=pd.RangeIndex(start=0, stop=100, step=1),
        )
        manager.update_portfolio_history(portfolio_returns)

        # Onboard a new strategy
        s1 = create_strategy_record(
            strategy_id="S1",
            version_hash="hash1",
            initial_state=StrategyState.INCUBATION,
        )
        manager.onboard_strategy(s1)

        # Candidate returns identical to portfolio → high correlation → rejection
        candidate_returns = portfolio_returns.copy()
        result = manager.request_admission("S1", candidate_returns)

        assert result.allowed is False
        assert "Correlation Violation" in result.reason
        # State remains INCUBATION
        assert manager.strategies["S1"].state == StrategyState.INCUBATION

    def test_update_portfolio_history_concatenates_and_dedupes(self):
        """update_portfolio_history merges new returns, keeping last observation per index."""
        manager = PortfolioManager()

        # First update
        series1 = pd.Series(
            [0.01, 0.02, 0.03],
            index=pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-03"]),
        )
        manager.update_portfolio_history(series1)
        pd.testing.assert_series_equal(manager.portfolio_returns, series1)

        # Second update with overlapping index
        series2 = pd.Series(
            [0.04, 0.05],
            index=pd.to_datetime(["2024-01-02", "2024-01-04"]),
        )
        manager.update_portfolio_history(series2)

        # Expected: concatenated, sorted, last observation kept for duplicate 2024-01-02
        expected = pd.Series(
            [0.01, 0.04, 0.03, 0.05],
            index=pd.to_datetime([
                "2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04"
            ]),
        )
        pd.testing.assert_series_equal(manager.portfolio_returns, expected)

    def test_activate_strategy_raises_for_unknown_id(self):
        """activate_strategy raises ValueError for unknown strategy_id."""
        manager = PortfolioManager()
        with pytest.raises(ValueError, match="Unknown strategy"):
            manager.activate_strategy("nonexistent")

    def test_request_admission_raises_for_unknown_id(self):
        """request_admission raises ValueError for unknown strategy_id."""
        manager = PortfolioManager()
        candidate_returns = pd.Series([0.01, 0.02])
        with pytest.raises(ValueError, match="Unknown strategy"):
            manager.request_admission("nonexistent", candidate_returns)

    def test_rebalance_empty_when_no_live(self):
        """rebalance_portfolio returns empty dict when no LIVE strategies."""
        manager = PortfolioManager()
        # Add only a CANDIDATE strategy
        s1 = create_strategy_record(
            strategy_id="S1",
            version_hash="hash1",
            initial_state=StrategyState.CANDIDATE,
        )
        manager.strategies["S1"] = s1

        allocations = manager.rebalance_portfolio()
        assert allocations == {}