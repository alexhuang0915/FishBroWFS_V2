"""
Test kill‑switch engine (strategy‑level and portfolio‑level).
"""
import pytest
from pathlib import Path
from unittest.mock import patch

from portfolio.models.governance_models import (
    StrategyIdentity,
    StrategyState,
    GovernanceParams,
)
from portfolio.governance.state_machine import PortfolioGovernanceStore, StrategyRecord
from portfolio.governance.kill_switch import (
    should_kill_strategy,
    handle_strategy_kill,
    should_trigger_portfolio_breaker,
    apply_portfolio_breaker,
    handle_portfolio_breaker,
)


@pytest.fixture
def tmp_governance_root(tmp_path):
    with patch("portfolio.governance.governance_logging.governance_root") as mock_logging_root, \
         patch("portfolio.governance.kill_switch.governance_root") as mock_kill_root:
        mock_logging_root.return_value = tmp_path / "governance"
        mock_kill_root.return_value = tmp_path / "governance"
        yield mock_logging_root


@pytest.fixture
def sample_params():
    return GovernanceParams(
        dd_absolute_cap=0.35,
        dd_k_multiplier=1.0,
        portfolio_dd_cap=0.20,
        exposure_reduction_on_breaker=0.5,
    )


@pytest.fixture
def sample_identity():
    return StrategyIdentity(
        strategy_id="S2_KILL",
        version_hash="v1",
        universe={"symbol": "MNQ"},
        data_fingerprint="fp1",
        cost_model_id="cost",
        tags=["Trend"],
    )


@pytest.fixture
def store_with_live_strategy(sample_identity):
    store = PortfolioGovernanceStore()
    record = StrategyRecord(
        identity=sample_identity,
        state=StrategyState.LIVE,
        created_utc="2026-01-01T00:00:00Z",
        updated_utc="2026-01-01T00:00:00Z",
    )
    store.upsert(record)
    return store, sample_identity.identity_key()


class TestStrategyKillSwitch:
    def test_should_kill_strategy_threshold(self, sample_params):
        """Threshold = max(dd_reference * multiplier, absolute_cap)."""
        # dd_reference * multiplier = 0.25 * 1.0 = 0.25, absolute_cap = 0.35 → threshold = 0.35
        triggered, threshold = should_kill_strategy(
            dd_live=0.40,
            dd_reference=0.25,
            params=sample_params,
        )
        assert threshold == 0.35
        assert triggered is True  # 0.40 > 0.35

        # dd_live below threshold
        triggered, _ = should_kill_strategy(
            dd_live=0.30,
            dd_reference=0.25,
            params=sample_params,
        )
        assert triggered is False

    def test_kill_trigger_with_k_multiplier(self):
        """If multiplier raises threshold above absolute cap, use that."""
        params = GovernanceParams(
            dd_absolute_cap=0.35,
            dd_k_multiplier=2.0,  # multiplier > 1
        )
        # dd_reference * multiplier = 0.20 * 2.0 = 0.40, absolute_cap = 0.35 → threshold = 0.40
        triggered, threshold = should_kill_strategy(
            dd_live=0.41,
            dd_reference=0.20,
            params=params,
        )
        assert threshold == 0.40
        assert triggered is True

    def test_handle_strategy_kill_writes_artifact(
        self, store_with_live_strategy, sample_params, tmp_governance_root
    ):
        """Kill‑switch writes a KillSwitchReport artifact."""
        store, key = store_with_live_strategy
        artifact_path = handle_strategy_kill(
            store=store,
            strategy_key=key,
            dd_live=0.50,
            dd_reference=0.25,
            params=sample_params,
        )
        assert artifact_path
        full_path = tmp_governance_root.return_value / artifact_path
        assert full_path.exists()
        assert full_path.suffix == ".json"

    def test_handle_strategy_kill_transitions_to_retired(
        self, store_with_live_strategy, sample_params, tmp_governance_root
    ):
        """If triggered, LIVE → RETIRED."""
        store, key = store_with_live_strategy
        record_before = store.get(key)
        assert record_before.state == StrategyState.LIVE

        handle_strategy_kill(
            store=store,
            strategy_key=key,
            dd_live=0.50,  # above threshold
            dd_reference=0.25,
            params=sample_params,
        )

        record_after = store.get(key)
        assert record_after.state == StrategyState.RETIRED

    def test_handle_strategy_kill_no_transition_if_not_triggered(
        self, store_with_live_strategy, sample_params, tmp_governance_root
    ):
        """If not triggered, state remains unchanged."""
        store, key = store_with_live_strategy
        handle_strategy_kill(
            store=store,
            strategy_key=key,
            dd_live=0.10,  # below threshold
            dd_reference=0.25,
            params=sample_params,
        )
        record = store.get(key)
        assert record.state == StrategyState.LIVE

    def test_kill_switch_on_probation_also_retires(
        self, sample_identity, sample_params, tmp_governance_root
    ):
        """A strategy in PROBATION can also be retired by kill‑switch."""
        store = PortfolioGovernanceStore()
        record = StrategyRecord(
            identity=sample_identity,
            state=StrategyState.PROBATION,
            created_utc="2026-01-01T00:00:00Z",
            updated_utc="2026-01-01T00:00:00Z",
        )
        store.upsert(record)
        key = sample_identity.identity_key()

        handle_strategy_kill(
            store=store,
            strategy_key=key,
            dd_live=0.50,
            dd_reference=0.25,
            params=sample_params,
        )
        assert store.get(key).state == StrategyState.RETIRED


class TestPortfolioCircuitBreaker:
    def test_should_trigger_portfolio_breaker(self, sample_params):
        """Trigger when portfolio drawdown exceeds cap."""
        triggered = should_trigger_portfolio_breaker(
            dd_portfolio=0.25,
            params=sample_params,
        )
        assert triggered is True  # 0.25 > 0.20

        not_triggered = should_trigger_portfolio_breaker(
            dd_portfolio=0.15,
            params=sample_params,
        )
        assert not_triggered is False

    def test_apply_portfolio_breaker_adds_cash(self, sample_params):
        """Breaker reduces exposure and adds _CASH bucket."""
        weights = {"A": 0.6, "B": 0.4}
        new_weights = apply_portfolio_breaker(weights, sample_params)
        # exposure_reduction = 0.5
        expected = {
            "A": 0.6 * 0.5,
            "B": 0.4 * 0.5,
            "_CASH": 1.0 - (0.6 * 0.5 + 0.4 * 0.5),
        }
        for k, v in expected.items():
            assert pytest.approx(new_weights[k], rel=1e-9) == v
        # Sum should still be 1
        assert pytest.approx(sum(new_weights.values()), rel=1e-9) == 1.0

    def test_apply_portfolio_breaker_zero_reduction(self):
        """If reduction = 0, all weight goes to cash."""
        params = GovernanceParams(exposure_reduction_on_breaker=0.0)
        weights = {"A": 0.7, "B": 0.3}
        new_weights = apply_portfolio_breaker(weights, params)
        assert new_weights["A"] == 0.0
        assert new_weights["B"] == 0.0
        assert new_weights["_CASH"] == 1.0

    def test_apply_portfolio_breaker_full_reduction(self):
        """If reduction = 1, weights unchanged, cash = 0."""
        params = GovernanceParams(exposure_reduction_on_breaker=1.0)
        weights = {"A": 0.7, "B": 0.3}
        new_weights = apply_portfolio_breaker(weights, params)
        assert new_weights["A"] == 0.7
        assert new_weights["B"] == 0.3
        assert new_weights["_CASH"] == 0.0

    def test_handle_portfolio_breaker_logs_event(
        self, sample_params, tmp_governance_root
    ):
        """Portfolio breaker logs a governance event."""
        store = PortfolioGovernanceStore()
        current_weights = {"A": 0.6, "B": 0.4}
        triggered, new_weights, artifact_path = handle_portfolio_breaker(
            store=store,
            dd_portfolio=0.25,  # above cap
            current_weights=current_weights,
            params=sample_params,
        )
        assert triggered is True
        assert "_CASH" in new_weights
        assert artifact_path != ""

        # Check that log file was written
        log_file = tmp_governance_root.return_value / "governance_log.jsonl"
        if log_file.exists():
            lines = log_file.read_text().strip().split("\n")
            assert any("PORTFOLIO_CIRCUIT_BREAKER" in line for line in lines)

    def test_handle_portfolio_breaker_no_trigger(
        self, sample_params, tmp_governance_root
    ):
        """If dd_portfolio ≤ cap, no change, no log."""
        store = PortfolioGovernanceStore()
        current_weights = {"A": 0.6, "B": 0.4}
        triggered, new_weights, artifact_path = handle_portfolio_breaker(
            store=store,
            dd_portfolio=0.15,  # below cap
            current_weights=current_weights,
            params=sample_params,
        )
        assert triggered is False
        assert new_weights == current_weights  # unchanged
        assert artifact_path == ""