"""Contract tests for governance lifecycle state transitions.

Tests transition matrix: prev_state × decision → next_state
"""

from __future__ import annotations

import pytest

from FishBroWFS_V2.core.governance.transition import governance_transition
from FishBroWFS_V2.core.schemas.governance import Decision, LifecycleState


# Transition test matrix: (prev_state, decision, expected_next_state)
TRANSITION_TEST_CASES = [
    # INCUBATION transitions
    ("INCUBATION", Decision.KEEP, "CANDIDATE"),
    ("INCUBATION", Decision.DROP, "RETIRED"),
    ("INCUBATION", Decision.FREEZE, "INCUBATION"),
    
    # CANDIDATE transitions
    ("CANDIDATE", Decision.KEEP, "LIVE"),
    ("CANDIDATE", Decision.DROP, "RETIRED"),
    ("CANDIDATE", Decision.FREEZE, "CANDIDATE"),
    
    # LIVE transitions
    ("LIVE", Decision.KEEP, "LIVE"),
    ("LIVE", Decision.DROP, "RETIRED"),
    ("LIVE", Decision.FREEZE, "LIVE"),
    
    # RETIRED is terminal (no transitions)
    ("RETIRED", Decision.KEEP, "RETIRED"),
    ("RETIRED", Decision.DROP, "RETIRED"),
    ("RETIRED", Decision.FREEZE, "RETIRED"),
]


@pytest.mark.parametrize("prev_state,decision,expected_next_state", TRANSITION_TEST_CASES)
def test_governance_transition_matrix(
    prev_state: LifecycleState,
    decision: Decision,
    expected_next_state: LifecycleState,
) -> None:
    """
    Test governance transition for all state × decision combinations.
    
    This is a table-driven test covering the complete transition matrix.
    """
    result = governance_transition(prev_state, decision)
    
    assert result == expected_next_state, (
        f"Transition failed: {prev_state} + {decision.value} → {result}, "
        f"expected {expected_next_state}"
    )


def test_governance_transition_incubation_to_candidate() -> None:
    """Test INCUBATION → CANDIDATE transition."""
    result = governance_transition("INCUBATION", Decision.KEEP)
    assert result == "CANDIDATE"


def test_governance_transition_incubation_to_retired() -> None:
    """Test INCUBATION → RETIRED transition."""
    result = governance_transition("INCUBATION", Decision.DROP)
    assert result == "RETIRED"


def test_governance_transition_candidate_to_live() -> None:
    """Test CANDIDATE → LIVE transition."""
    result = governance_transition("CANDIDATE", Decision.KEEP)
    assert result == "LIVE"


def test_governance_transition_retired_terminal() -> None:
    """Test that RETIRED is terminal state (no transitions)."""
    # RETIRED should remain RETIRED regardless of decision
    assert governance_transition("RETIRED", Decision.KEEP) == "RETIRED"
    assert governance_transition("RETIRED", Decision.DROP) == "RETIRED"
    assert governance_transition("RETIRED", Decision.FREEZE) == "RETIRED"
