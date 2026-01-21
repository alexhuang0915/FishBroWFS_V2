"""Tests for portfolio engine V1."""

import pytest
from datetime import datetime
from typing import List

from core.schemas.portfolio_v1 import (
    PortfolioPolicyV1,
    SignalCandidateV1,
    OpenPositionV1,
)
from portfolio.engine_v1 import PortfolioEngineV1, admit_candidates


def create_test_policy() -> PortfolioPolicyV1:
    """Create test portfolio policy."""
    return PortfolioPolicyV1(
        version="PORTFOLIO_POLICY_V1",
        base_currency="TWD",
        instruments_config_sha256="test_sha256",
        max_slots_total=4,
        max_margin_ratio=0.35,  # 35%
        max_notional_ratio=None,
        max_slots_by_instrument={},
        strategy_priority={
            "S1": 10,
            "S2": 20,
            "S3": 30,
        },
        signal_strength_field="signal_strength",
        allow_force_kill=False,
        allow_queue=False,
    )


def create_test_candidate(
    strategy_id: str = "S1",
    instrument_id: str = "CME.MNQ",
    bar_index: int = 0,
    signal_strength: float = 1.0,
    candidate_score: float = 0.0,
    required_margin: float = 100000.0,  # 100k TWD
) -> SignalCandidateV1:
    """Create test candidate."""
    return SignalCandidateV1(
        strategy_id=strategy_id,
        instrument_id=instrument_id,
        bar_ts=datetime(2025, 1, 1, 9, 0, 0),
        bar_index=bar_index,
        signal_strength=signal_strength,
        candidate_score=candidate_score,
        required_margin_base=required_margin,
        required_slot=1,
    )


def test_4_1_determinism():
    """4.1 Determinism: same input candidates in different order → same output."""
    policy = create_test_policy()
    equity_base = 1_000_000.0  # 1M TWD
    
    # Create candidates with different order
    candidates1 = [
        create_test_candidate("S1", "CME.MNQ", 0, 0.8, candidate_score=0.0, required_margin=200000.0),
        create_test_candidate("S2", "CME.MNQ", 0, 0.9, candidate_score=0.0, required_margin=150000.0),
        create_test_candidate("S3", "CME.MNQ", 0, 0.7, candidate_score=0.0, required_margin=250000.0),
    ]
    
    candidates2 = [
        create_test_candidate("S3", "CME.MNQ", 0, 0.7, candidate_score=0.0, required_margin=250000.0),
        create_test_candidate("S1", "CME.MNQ", 0, 0.8, candidate_score=0.0, required_margin=200000.0),
        create_test_candidate("S2", "CME.MNQ", 0, 0.9, candidate_score=0.0, required_margin=150000.0),
    ]
    
    # Run admission with same policy and equity
    engine1 = PortfolioEngineV1(policy, equity_base)
    decisions1 = engine1.admit_candidates(candidates1)
    
    engine2 = PortfolioEngineV1(policy, equity_base)
    decisions2 = engine2.admit_candidates(candidates2)
    
    # Check same number of decisions
    assert len(decisions1) == len(decisions2)
    
    # Check same acceptance/rejection pattern
    accept_counts1 = sum(1 for d in decisions1 if d.accepted)
    accept_counts2 = sum(1 for d in decisions2 if d.accepted)
    assert accept_counts1 == accept_counts2
    
    # Check same final state
    assert engine1.slots_used == engine2.slots_used
    assert engine1.margin_used_base == engine2.margin_used_base
    
    # Check deterministic order of decisions (should be sorted by sort key)
    # The decisions should be in the same order regardless of input order
    for d1, d2 in zip(decisions1, decisions2):
        assert d1.strategy_id == d2.strategy_id
        assert d1.accepted == d2.accepted
        assert d1.reason == d2.reason


def test_4_2_full_reject_policy():
    """4.2 Full Reject Policy: max slots reached → REJECT_FULL, no force kill."""
    policy = create_test_policy()
    policy.max_slots_total = 2  # Only 2 slots total
    equity_base = 1_000_000.0
    
    # Create candidates that would use 1 slot each
    candidates = [
        create_test_candidate("S1", "CME.MNQ", 0, 0.9, candidate_score=0.0, required_margin=100000.0),
        create_test_candidate("S2", "CME.MNQ", 0, 0.8, candidate_score=0.0, required_margin=100000.0),
        create_test_candidate("S3", "CME.MNQ", 0, 0.7, candidate_score=0.0, required_margin=100000.0),  # Should be rejected
        create_test_candidate("S4", "CME.MNQ", 0, 0.6, candidate_score=0.0, required_margin=100000.0),  # Should be rejected
    ]
    
    engine = PortfolioEngineV1(policy, equity_base)
    decisions = engine.admit_candidates(candidates)
    
    # Check first two accepted
    assert decisions[0].accepted == True
    assert decisions[0].reason == "ACCEPT"
    assert decisions[1].accepted == True
    assert decisions[1].reason == "ACCEPT"
    
    # Check last two rejected with REJECT_FULL
    assert decisions[2].accepted == False
    assert decisions[2].reason == "REJECT_FULL"
    assert decisions[3].accepted == False
    assert decisions[3].reason == "REJECT_FULL"
    
    # Check slots used = 2 (max)
    assert engine.slots_used == 2
    
    # Verify no force kill (allow_force_kill=False by default)
    # Engine should not close existing positions to accept new ones
    assert len(engine.open_positions) == 2


def test_4_3_margin_reject():
    """4.3 Margin Reject: margin ratio exceeded → REJECT_MARGIN."""
    policy = create_test_policy()
    policy.max_margin_ratio = 0.25  # 25% margin ratio
    equity_base = 1_000_000.0  # 1M TWD
    
    # Candidate 1: uses 200k margin (20% of equity)
    candidate1 = create_test_candidate("S1", "CME.MNQ", 0, 0.9, candidate_score=0.0, required_margin=200000.0)
    
    # Candidate 2: would use another 100k margin (total 30% > 25% limit)
    candidate2 = create_test_candidate("S2", "CME.MNQ", 0, 0.8, candidate_score=0.0, required_margin=100000.0)
    
    engine = PortfolioEngineV1(policy, equity_base)
    decisions = engine.admit_candidates([candidate1, candidate2])
    
    # First candidate should be accepted
    assert decisions[0].accepted == True
    assert decisions[0].reason == "ACCEPT"
    
    # Second candidate should be rejected due to margin limit
    assert decisions[1].accepted == False
    assert decisions[1].reason == "REJECT_MARGIN"
    
    # Check margin used = 200k (20% of equity)
    assert engine.margin_used_base == 200000.0
    assert engine.margin_used_base / equity_base == 0.2


def test_4_4_mixed_instruments_mnq_mxf():
    """4.4 Mixed Instruments (MNQ + MXF): per-instrument cap生效."""
    policy = create_test_policy()
    policy.max_slots_total = 6  # Total slots
    policy.max_slots_by_instrument = {
        "CME.MNQ": 2,  # Max 2 slots for MNQ
        "TWF.MXF": 3,  # Max 3 slots for MXF
    }
    equity_base = 2_000_000.0  # 2M TWD
    
    # Create candidates for both instruments
    candidates = [
        # MNQ candidates (should accept first 2, reject 3rd)
        create_test_candidate("S1", "CME.MNQ", 0, 0.9, candidate_score=0.0, required_margin=100000.0),
        create_test_candidate("S2", "CME.MNQ", 0, 0.8, candidate_score=0.0, required_margin=100000.0),
        create_test_candidate("S3", "CME.MNQ", 0, 0.7, candidate_score=0.0, required_margin=100000.0),  # Should be rejected (MNQ cap)
        
        # MXF candidates (should accept first 3, reject 4th)
        create_test_candidate("S4", "TWF.MXF", 0, 0.9, candidate_score=0.0, required_margin=100000.0),
        create_test_candidate("S5", "TWF.MXF", 0, 0.8, candidate_score=0.0, required_margin=100000.0),
        create_test_candidate("S6", "TWF.MXF", 0, 0.7, candidate_score=0.0, required_margin=100000.0),
        create_test_candidate("S7", "TWF.MXF", 0, 0.6, candidate_score=0.0, required_margin=100000.0),  # Should be rejected (MXF cap)
    ]
    
    engine = PortfolioEngineV1(policy, equity_base)
    decisions = engine.admit_candidates(candidates)
    
    # Count acceptances by instrument
    mnq_accept = sum(1 for d in decisions if d.accepted and d.instrument_id == "CME.MNQ")
    mxf_accept = sum(1 for d in decisions if d.accepted and d.instrument_id == "TWF.MXF")
    
    # Should have 2 MNQ and 3 MXF accepted
    assert mnq_accept == 2
    assert mxf_accept == 3
    
    # Check specific rejections
    mnq_reject = [d for d in decisions if not d.accepted and d.instrument_id == "CME.MNQ"]
    mxf_reject = [d for d in decisions if not d.accepted and d.instrument_id == "TWF.MXF"]
    
    assert len(mnq_reject) == 1
    assert len(mxf_reject) == 1
    
    # Both should be REJECT_FULL (instrument-specific full)
    assert mnq_reject[0].reason == "REJECT_FULL"
    assert mxf_reject[0].reason == "REJECT_FULL"
    
    # Check total slots used = 5 (2 MNQ + 3 MXF)
    assert engine.slots_used == 5
    
    # Check instrument-specific counts
    mnq_positions = [p for p in engine.open_positions if p.instrument_id == "CME.MNQ"]
    mxf_positions = [p for p in engine.open_positions if p.instrument_id == "TWF.MXF"]
    
    assert len(mnq_positions) == 2
    assert len(mxf_positions) == 3


def test_strategy_priority_sorting():
    """Test that candidates are sorted by strategy priority, then candidate_score."""
    policy = create_test_policy()
    equity_base = 1_000_000.0
    
    # Create candidates with different priorities and scores
    candidates = [
        create_test_candidate("S3", "CME.MNQ", 0, 0.9, candidate_score=0.5, required_margin=100000.0),  # Priority 30, score 0.5
        create_test_candidate("S1", "CME.MNQ", 0, 0.7, candidate_score=0.3, required_margin=100000.0),  # Priority 10, score 0.3
        create_test_candidate("S2", "CME.MNQ", 0, 0.8, candidate_score=0.4, required_margin=100000.0),  # Priority 20, score 0.4
    ]
    
    engine = PortfolioEngineV1(policy, equity_base)
    decisions = engine.admit_candidates(candidates)
    
    # Should be sorted by: priority (10, 20, 30), then candidate_score (descending)
    # S1 (priority 10) first, then S2 (priority 20), then S3 (priority 30)
    assert decisions[0].strategy_id == "S1"
    assert decisions[1].strategy_id == "S2"
    assert decisions[2].strategy_id == "S3"
    
    # All should be accepted (enough slots and margin)
    assert all(d.accepted for d in decisions)


def test_sortkey_priority_then_score_then_sha():
    """Test SortKey: priority → score → sha tie-breaking."""
    policy = create_test_policy()
    equity_base = 1_000_000.0
    
    # Test 1: priority相同，score不同 → score高者先 admit
    candidates1 = [
        create_test_candidate("S1", "CME.MNQ", 0, 1.0, candidate_score=0.3, required_margin=50000.0),
        create_test_candidate("S1", "CME.MNQ", 0, 1.0, candidate_score=0.7, required_margin=50000.0),
    ]
    
    engine1 = PortfolioEngineV1(policy, equity_base)
    decisions1 = engine1.admit_candidates(candidates1)
    
    # Both have same priority, higher score (0.7) should be first
    assert decisions1[0].candidate_score == 0.7
    assert decisions1[1].candidate_score == 0.3
    
    # Test 2: priority/score相同，sha不同 → sha字典序小者先 admit
    # Need to create candidates with different signal_series_sha256
    from core.schemas.portfolio_v1 import SignalCandidateV1
    from datetime import datetime
    
    candidate_a = SignalCandidateV1(
        strategy_id="S1",
        instrument_id="CME.MNQ",
        bar_ts=datetime(2025, 1, 1, 9, 0, 0),
        bar_index=0,
        signal_strength=1.0,
        candidate_score=0.5,
        required_margin_base=50000.0,
        required_slot=1,
        signal_series_sha256="aaa111",  # lexicographically smaller
    )
    
    candidate_b = SignalCandidateV1(
        strategy_id="S1",
        instrument_id="CME.MNQ",
        bar_ts=datetime(2025, 1, 1, 9, 0, 0),
        bar_index=0,
        signal_strength=1.0,
        candidate_score=0.5,
        required_margin_base=50000.0,
        required_slot=1,
        signal_series_sha256="bbb222",  # lexicographically larger
    )
    
    candidates2 = [candidate_b, candidate_a]  # Reverse order
    engine2 = PortfolioEngineV1(policy, equity_base)
    decisions2 = engine2.admit_candidates(candidates2)
    
    # Should be sorted by sha (aaa111 before bbb222)
    assert decisions2[0].signal_series_sha256 == "aaa111"
    assert decisions2[1].signal_series_sha256 == "bbb222"
    
    # All should be accepted (enough slots and margin)
    assert all(d.accepted for d in decisions1)
    assert all(d.accepted for d in decisions2)


def test_convenience_function():
    """Test the admit_candidates convenience function."""
    policy = create_test_policy()
    equity_base = 1_000_000.0
    
    candidates = [
        create_test_candidate("S1", "CME.MNQ", 0, 0.9, candidate_score=0.0, required_margin=100000.0),
        create_test_candidate("S2", "CME.MNQ", 0, 0.8, candidate_score=0.0, required_margin=200000.0),
    ]
    
    decisions, summary = admit_candidates(policy, equity_base, candidates)
    
    assert len(decisions) == 2
    assert summary.total_candidates == 2
    assert summary.accepted_count + summary.rejected_count == 2
    
    # Check summary fields
    assert summary.final_slots_used >= 0
    assert summary.final_margin_used_base >= 0.0
    assert 0.0 <= summary.final_margin_ratio <= 1.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])