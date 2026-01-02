"""
Test the portfolio governance state machine (Article I).
"""
import pytest
from pathlib import Path
from unittest.mock import patch

from portfolio.models.governance_models import (
    StrategyIdentity,
    StrategyState,
    ReasonCode,
)
from portfolio.governance.state_machine import (
    PortfolioGovernanceStore,
    StrategyRecord,
    is_transition_allowed,
    transition,
    create_new_strategy_record,
)


@pytest.fixture
def tmp_governance_root(tmp_path):
    """Patch governance root to a temporary directory."""
    with patch("portfolio.governance.governance_logging.governance_root") as mock_root:
        mock_root.return_value = tmp_path / "governance"
        yield mock_root


@pytest.fixture
def sample_identity():
    return StrategyIdentity(
        strategy_id="S2_001",
        version_hash="hash1",
        universe={"symbol": "MNQ", "timeframe": "5m"},
        data_fingerprint="fp1",
        cost_model_id="cost_v1",
        tags=["Trend"],
    )


@pytest.fixture
def store():
    return PortfolioGovernanceStore()


class TestStateMachineTransitions:
    def test_allowed_transitions(self):
        """Verify the exact allowed transitions from Article I."""
        allowed = {
            (StrategyState.INCUBATION, StrategyState.CANDIDATE),
            (StrategyState.CANDIDATE, StrategyState.PAPER_TRADING),
            (StrategyState.PAPER_TRADING, StrategyState.LIVE),
            (StrategyState.LIVE, StrategyState.PROBATION),
            (StrategyState.PROBATION, StrategyState.LIVE),
            (StrategyState.PROBATION, StrategyState.RETIRED),
            (StrategyState.LIVE, StrategyState.RETIRED),
            (StrategyState.PROBATION, StrategyState.FREEZE),
            (StrategyState.LIVE, StrategyState.FREEZE),
            (StrategyState.FREEZE, StrategyState.RETIRED),
            (StrategyState.FREEZE, StrategyState.PROBATION),
            (StrategyState.FREEZE, StrategyState.LIVE),
        }
        # Ensure no extra transitions
        for from_state in StrategyState:
            for to_state in StrategyState:
                expected = (from_state, to_state) in allowed
                assert is_transition_allowed(from_state, to_state) == expected

    def test_disallow_skip_transitions(self, store, sample_identity, tmp_governance_root):
        """Cannot skip states, e.g., INCUBATION → LIVE."""
        key = sample_identity.identity_key()
        record = StrategyRecord(
            identity=sample_identity,
            state=StrategyState.INCUBATION,
            created_utc="2026-01-01T00:00:00Z",
            updated_utc="2026-01-01T00:00:00Z",
        )
        store.upsert(record)

        with pytest.raises(ValueError, match="is not allowed"):
            transition(
                store=store,
                strategy_key=key,
                to_state=StrategyState.LIVE,
                reason_code=ReasonCode.PROMOTE_TO_LIVE,
            )

    def test_transition_writes_log_event(self, store, sample_identity, tmp_governance_root):
        """A successful transition appends a line to the governance log."""
        key = sample_identity.identity_key()
        record = StrategyRecord(
            identity=sample_identity,
            state=StrategyState.CANDIDATE,
            created_utc="2026-01-01T00:00:00Z",
            updated_utc="2026-01-01T00:00:00Z",
        )
        store.upsert(record)

        log_file = tmp_governance_root.return_value / "governance_log.jsonl"
        assert not log_file.exists()

        transition(
            store=store,
            strategy_key=key,
            to_state=StrategyState.PAPER_TRADING,
            reason_code=ReasonCode.PROMOTE_TO_PAPER,
        )

        assert log_file.exists()
        lines = log_file.read_text().strip().split("\n")
        assert len(lines) == 1
        import json
        event = json.loads(lines[0])
        assert event["from_state"] == "CANDIDATE"
        assert event["to_state"] == "PAPER_TRADING"
        assert event["reason_code"] == "PROMOTE_TO_PAPER"

    def test_create_new_strategy_record_logs(self, sample_identity, tmp_governance_root):
        """Creating a new record logs a creation event."""
        log_file = tmp_governance_root.return_value / "governance_log.jsonl"
        assert not log_file.exists()

        record = create_new_strategy_record(
            sample_identity,
            initial_state=StrategyState.INCUBATION,
            actor="test",
        )

        assert log_file.exists()
        lines = log_file.read_text().strip().split("\n")
        assert len(lines) == 1
        import json
        event = json.loads(lines[0])
        assert event["to_state"] == "INCUBATION"
        assert event["actor"] == "test"

    def test_transition_updates_record(self, store, sample_identity, tmp_governance_root):
        """Transition updates state and timestamps."""
        key = sample_identity.identity_key()
        record = StrategyRecord(
            identity=sample_identity,
            state=StrategyState.LIVE,
            created_utc="2026-01-01T00:00:00Z",
            updated_utc="2026-01-01T00:00:00Z",
        )
        store.upsert(record)

        updated = transition(
            store=store,
            strategy_key=key,
            to_state=StrategyState.PROBATION,
            reason_code=ReasonCode.DEMOTE_TO_PROBATION,
        )

        assert updated.state == StrategyState.PROBATION
        assert updated.updated_utc != "2026-01-01T00:00:00Z"
        assert updated.last_reason == ReasonCode.DEMOTE_TO_PROBATION

        stored = store.get(key)
        assert stored.state == StrategyState.PROBATION