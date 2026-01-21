"""
Test the Portfolio Governance State Machine (Constitution‑compliant).

Validates:
- Death is final (RETIRED cannot transition)
- Promotion ladder (no shortcuts)
- Risk transitions (PROBATION ↔ LIVE, FREEZE)
- Immutability enforcement (version_hash and config frozen after INCUBATION)
"""
import pytest
from datetime import datetime, timezone

from portfolio.models.governance_models import StrategyState
from portfolio.governance_state import (
    StrategyRecord,
    GovernanceStateMachine,
    create_strategy_record,
    transition_strategy,
)


# ========== Fixtures ==========

@pytest.fixture
def incubation_record():
    """A strategy in INCUBATION state (mutable)."""
    return create_strategy_record(
        strategy_id="S2_001",
        version_hash="hash1",
        config={"param": 1.0},
        initial_state=StrategyState.INCUBATION,
    )


@pytest.fixture
def candidate_record():
    """A strategy in CANDIDATE state (immutable)."""
    return create_strategy_record(
        strategy_id="S2_002",
        version_hash="hash2",
        config={"param": 2.0},
        initial_state=StrategyState.CANDIDATE,
    )


@pytest.fixture
def live_record():
    """A strategy in LIVE state (immutable)."""
    return create_strategy_record(
        strategy_id="S2_003",
        version_hash="hash3",
        config={"param": 3.0},
        initial_state=StrategyState.LIVE,
    )


@pytest.fixture
def retired_record():
    """A strategy in RETIRED state (dead)."""
    return create_strategy_record(
        strategy_id="S2_004",
        version_hash="hash4",
        config={"param": 4.0},
        initial_state=StrategyState.RETIRED,
    )


# ========== Test Adjacency ==========

class TestAdjacencyList:
    """Verify the adjacency list matches the Constitution."""

    def test_allowed_transitions(self):
        """Every allowed transition must be present."""
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
        for from_state, to_state in allowed:
            assert GovernanceStateMachine.can_transition(from_state, to_state), \
                f"Transition {from_state} → {to_state} should be allowed"

    def test_disallowed_transitions(self):
        """Verify that illegal transitions are rejected."""
        # Death is final: RETIRED cannot transition to any state
        for to_state in StrategyState:
            assert not GovernanceStateMachine.can_transition(StrategyState.RETIRED, to_state), \
                f"RETIRED → {to_state} should be forbidden"

        # Promotion ladder: no skipping states
        illegal_skips = [
            (StrategyState.INCUBATION, StrategyState.PAPER_TRADING),
            (StrategyState.INCUBATION, StrategyState.LIVE),
            (StrategyState.INCUBATION, StrategyState.PROBATION),
            (StrategyState.INCUBATION, StrategyState.FREEZE),
            (StrategyState.INCUBATION, StrategyState.RETIRED),
            (StrategyState.CANDIDATE, StrategyState.LIVE),
            (StrategyState.CANDIDATE, StrategyState.PROBATION),
            (StrategyState.CANDIDATE, StrategyState.FREEZE),
            (StrategyState.CANDIDATE, StrategyState.RETIRED),
            (StrategyState.PAPER_TRADING, StrategyState.PROBATION),
            (StrategyState.PAPER_TRADING, StrategyState.FREEZE),
            (StrategyState.PAPER_TRADING, StrategyState.RETIRED),
        ]
        for from_state, to_state in illegal_skips:
            assert not GovernanceStateMachine.can_transition(from_state, to_state), \
                f"Transition {from_state} → {to_state} should be forbidden (skip)"

        # No reverse transitions that violate adjacency
        illegal_reverse = [
            (StrategyState.CANDIDATE, StrategyState.INCUBATION),
            (StrategyState.PAPER_TRADING, StrategyState.CANDIDATE),
            (StrategyState.LIVE, StrategyState.PAPER_TRADING),
            (StrategyState.PROBATION, StrategyState.INCUBATION),
            (StrategyState.FREEZE, StrategyState.INCUBATION),
            (StrategyState.FREEZE, StrategyState.CANDIDATE),
            (StrategyState.FREEZE, StrategyState.PAPER_TRADING),
        ]
        for from_state, to_state in illegal_reverse:
            assert not GovernanceStateMachine.can_transition(from_state, to_state), \
                f"Transition {from_state} → {to_state} should be forbidden (reverse)"


# ========== Test Death Is Final ==========

class TestDeathIsFinal:
    """RETIRED cannot transition to any other state."""

    def test_retired_cannot_transition(self, retired_record):
        """Any attempt to move out of RETIRED raises ValueError."""
        for to_state in StrategyState:
            if to_state == StrategyState.RETIRED:
                continue
            with pytest.raises(ValueError, match="is not allowed"):
                GovernanceStateMachine.apply_update(retired_record, to_state)

    def test_retired_cannot_be_updated(self, retired_record):
        """Even if state unchanged, immutability still applies (but that's fine)."""
        # Updating metrics should be allowed (since RETIRED is immutable? Actually version_hash/config frozen)
        # But we can still update metrics because they are not frozen.
        updated = GovernanceStateMachine.apply_update(
            retired_record,
            StrategyState.RETIRED,  # same state
            metrics={"sharpe": -1.0},
        )
        assert updated.metrics["sharpe"] == -1.0


# ========== Test Promotion Ladder ==========

class TestPromotionLadder:
    """No shortcuts allowed (e.g., INCUBATION → LIVE)."""

    def test_incubation_to_live_forbidden(self, incubation_record):
        with pytest.raises(ValueError, match="is not allowed"):
            GovernanceStateMachine.apply_update(incubation_record, StrategyState.LIVE)

    def test_candidate_to_live_forbidden(self, candidate_record):
        with pytest.raises(ValueError, match="is not allowed"):
            GovernanceStateMachine.apply_update(candidate_record, StrategyState.LIVE)

    def test_paper_trading_to_retired_forbidden(self):
        record = create_strategy_record(
            strategy_id="S2_005",
            version_hash="hash5",
            initial_state=StrategyState.PAPER_TRADING,
        )
        with pytest.raises(ValueError, match="is not allowed"):
            GovernanceStateMachine.apply_update(record, StrategyState.RETIRED)

    def test_valid_promotion_path(self, incubation_record):
        """INCUBATION → CANDIDATE → PAPER_TRADING → LIVE is allowed."""
        r1 = GovernanceStateMachine.apply_update(incubation_record, StrategyState.CANDIDATE)
        assert r1.state == StrategyState.CANDIDATE

        r2 = GovernanceStateMachine.apply_update(r1, StrategyState.PAPER_TRADING)
        assert r2.state == StrategyState.PAPER_TRADING

        r3 = GovernanceStateMachine.apply_update(r2, StrategyState.LIVE)
        assert r3.state == StrategyState.LIVE


# ========== Test Risk Transitions ==========

class TestRiskTransitions:
    """PROBATION ↔ LIVE, FREEZE transitions."""

    def test_live_to_probation(self, live_record):
        updated = GovernanceStateMachine.apply_update(live_record, StrategyState.PROBATION)
        assert updated.state == StrategyState.PROBATION

    def test_probation_to_live(self):
        record = create_strategy_record(
            strategy_id="S2_006",
            version_hash="hash6",
            initial_state=StrategyState.PROBATION,
        )
        updated = GovernanceStateMachine.apply_update(record, StrategyState.LIVE)
        assert updated.state == StrategyState.LIVE

    def test_probation_to_freeze(self):
        record = create_strategy_record(
            strategy_id="S2_007",
            version_hash="hash7",
            initial_state=StrategyState.PROBATION,
        )
        updated = GovernanceStateMachine.apply_update(record, StrategyState.FREEZE)
        assert updated.state == StrategyState.FREEZE

    def test_live_to_freeze(self, live_record):
        updated = GovernanceStateMachine.apply_update(live_record, StrategyState.FREEZE)
        assert updated.state == StrategyState.FREEZE

    def test_freeze_to_probation(self):
        record = create_strategy_record(
            strategy_id="S2_008",
            version_hash="hash8",
            initial_state=StrategyState.FREEZE,
        )
        updated = GovernanceStateMachine.apply_update(record, StrategyState.PROBATION)
        assert updated.state == StrategyState.PROBATION

    def test_freeze_to_live(self):
        record = create_strategy_record(
            strategy_id="S2_009",
            version_hash="hash9",
            initial_state=StrategyState.FREEZE,
        )
        updated = GovernanceStateMachine.apply_update(record, StrategyState.LIVE)
        assert updated.state == StrategyState.LIVE

    def test_freeze_to_retired(self):
        record = create_strategy_record(
            strategy_id="S2_010",
            version_hash="hash10",
            initial_state=StrategyState.FREEZE,
        )
        updated = GovernanceStateMachine.apply_update(record, StrategyState.RETIRED)
        assert updated.state == StrategyState.RETIRED


# ========== Test Immutability Enforcement ==========

class TestImmutability:
    """version_hash and config cannot be changed after INCUBATION."""

    def test_incubation_mutable(self, incubation_record):
        """INCUBATION allows changes to version_hash and config."""
        updated = GovernanceStateMachine.apply_update(
            incubation_record,
            StrategyState.CANDIDATE,
            version_hash="new_hash",
            config={"new": 2.0},
        )
        assert updated.version_hash == "new_hash"
        assert updated.config == {"new": 2.0}

    def test_candidate_immutable_version_hash(self, candidate_record):
        """CANDIDATE cannot change version_hash."""
        with pytest.raises(ValueError, match="version_hash cannot be changed"):
            GovernanceStateMachine.apply_update(
                candidate_record,
                StrategyState.PAPER_TRADING,
                version_hash="new_hash",
            )

    def test_candidate_immutable_config(self, candidate_record):
        """CANDIDATE cannot change config."""
        with pytest.raises(ValueError, match="config cannot be changed"):
            GovernanceStateMachine.apply_update(
                candidate_record,
                StrategyState.PAPER_TRADING,
                config={"new": 2.0},
            )

    def test_live_immutable_version_hash(self, live_record):
        """LIVE cannot change version_hash."""
        with pytest.raises(ValueError, match="version_hash cannot be changed"):
            GovernanceStateMachine.apply_update(
                live_record,
                StrategyState.PROBATION,
                version_hash="new_hash",
            )

    def test_metrics_can_be_updated_anytime(self, candidate_record):
        """Metrics are not frozen and can be updated even in immutable states."""
        updated = GovernanceStateMachine.apply_update(
            candidate_record,
            StrategyState.PAPER_TRADING,
            metrics={"sharpe": 1.5},
        )
        assert updated.metrics["sharpe"] == 1.5

    def test_strategy_id_and_created_at_never_updatable(self, incubation_record):
        """strategy_id and created_at cannot be updated even in INCUBATION."""
        with pytest.raises(ValueError, match="strategy_id cannot be updated"):
            GovernanceStateMachine.apply_update(
                incubation_record,
                StrategyState.CANDIDATE,
                strategy_id="new_id",
            )
        with pytest.raises(ValueError, match="created_at cannot be updated"):
            GovernanceStateMachine.apply_update(
                incubation_record,
                StrategyState.CANDIDATE,
                created_at=datetime.now(timezone.utc),
            )


# ========== Test Convenience Functions ==========

class TestConvenienceFunctions:
    """Test create_strategy_record and transition_strategy."""

    def test_create_strategy_record_defaults(self):
        record = create_strategy_record("S2_011", "hash11")
        assert record.strategy_id == "S2_011"
        assert record.version_hash == "hash11"
        assert record.state == StrategyState.INCUBATION
        assert record.config == {}
        assert record.metrics == {}
        assert record.is_immutable() is False

    def test_transition_strategy_wrapper(self, incubation_record):
        updated = transition_strategy(
            incubation_record,
            StrategyState.CANDIDATE,
            metrics={"win_rate": 0.6},
        )
        assert updated.state == StrategyState.CANDIDATE
        assert updated.metrics["win_rate"] == 0.6

    def test_transition_strategy_invalid_raises(self, incubation_record):
        with pytest.raises(ValueError):
            transition_strategy(incubation_record, StrategyState.LIVE)