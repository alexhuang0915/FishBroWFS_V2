"""Governance lifecycle state transition logic.

Pure functions for state transitions based on decisions.
"""

from __future__ import annotations

from FishBroWFS_V2.core.schemas.governance import Decision, LifecycleState


def governance_transition(
    prev_state: LifecycleState,
    decision: Decision,
) -> LifecycleState:
    """
    Compute next lifecycle state based on previous state and decision.
    
    Transition rules:
    - INCUBATION + KEEP → CANDIDATE
    - INCUBATION + DROP → RETIRED
    - INCUBATION + FREEZE → INCUBATION (no change)
    - CANDIDATE + KEEP → LIVE
    - CANDIDATE + DROP → RETIRED
    - CANDIDATE + FREEZE → CANDIDATE (no change)
    - LIVE + KEEP → LIVE (no change)
    - LIVE + DROP → RETIRED
    - LIVE + FREEZE → LIVE (no change)
    - RETIRED + any → RETIRED (terminal state, no transitions)
    
    Args:
        prev_state: Previous lifecycle state
        decision: Governance decision (KEEP/DROP/FREEZE)
        
    Returns:
        Next lifecycle state
    """
    # RETIRED is terminal state
    if prev_state == "RETIRED":
        return "RETIRED"
    
    # State transition matrix
    transitions: dict[tuple[LifecycleState, Decision], LifecycleState] = {
        # INCUBATION transitions
        ("INCUBATION", Decision.KEEP): "CANDIDATE",
        ("INCUBATION", Decision.DROP): "RETIRED",
        ("INCUBATION", Decision.FREEZE): "INCUBATION",
        
        # CANDIDATE transitions
        ("CANDIDATE", Decision.KEEP): "LIVE",
        ("CANDIDATE", Decision.DROP): "RETIRED",
        ("CANDIDATE", Decision.FREEZE): "CANDIDATE",
        
        # LIVE transitions
        ("LIVE", Decision.KEEP): "LIVE",
        ("LIVE", Decision.DROP): "RETIRED",
        ("LIVE", Decision.FREEZE): "LIVE",
    }
    
    return transitions.get((prev_state, decision), prev_state)
