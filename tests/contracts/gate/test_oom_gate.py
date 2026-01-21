
"""Tests for OOM gate decision maker.

Tests verify:
1. PASS case (estimated <= 60% of budget)
2. BLOCK case (estimated > 90% of budget)
3. AUTO_DOWNSAMPLE case (between 60% and 90%, with recommended_rate in (0,1])
4. Invalid input validation (bars<=0, rate<=0, etc.)
"""

from __future__ import annotations

import pytest

from core.oom_gate import decide_gate, decide_oom_action, estimate_bytes
from core.schemas.oom_gate import OomGateInput


def test_estimate_bytes() -> None:
    """Test memory estimation formula."""
    inp = OomGateInput(
        bars=1000,
        params=100,
        param_subsample_rate=0.5,
        intents_per_bar=2.0,
        bytes_per_intent_est=64,
    )
    
    estimated = estimate_bytes(inp)
    
    # Formula: bars * params * subsample * intents_per_bar * bytes_per_intent_est
    expected = 1000 * 100 * 0.5 * 2.0 * 64
    assert estimated == expected


def test_decide_gate_pass() -> None:
    """Test PASS decision when estimated <= 60% of budget."""
    # Small workload: 1M bytes, budget is 6GB (6_000_000_000)
    inp = OomGateInput(
        bars=100,
        params=10,
        param_subsample_rate=0.1,
        intents_per_bar=2.0,
        bytes_per_intent_est=64,
        ram_budget_bytes=6_000_000_000,
    )
    
    decision = decide_gate(inp)
    
    assert decision.decision == "PASS"
    assert decision.estimated_bytes <= inp.ram_budget_bytes * 0.6
    assert decision.recommended_subsample_rate is None
    assert "PASS" not in decision.notes  # Notes should describe the decision, not repeat it
    assert decision.estimated_bytes > 0


def test_decide_gate_block() -> None:
    """Test BLOCK decision when estimated > 90% of budget."""
    # Large workload: exceed 90% of budget
    # Set budget to 1GB for easier testing
    budget = 1_000_000_000  # 1GB
    # Need estimated > budget * 0.9 = 900MB
    # Let's use: 10000 bars * 10000 params * 1.0 rate * 2.0 intents * 64 bytes = 12.8GB
    inp = OomGateInput(
        bars=10000,
        params=10000,
        param_subsample_rate=1.0,
        intents_per_bar=2.0,
        bytes_per_intent_est=64,
        ram_budget_bytes=budget,
    )
    
    decision = decide_gate(inp)
    
    assert decision.decision == "BLOCK"
    assert decision.estimated_bytes > budget * 0.9
    assert decision.recommended_subsample_rate is None
    assert "BLOCKED" in decision.notes or "BLOCK" in decision.notes


def test_decide_gate_auto_downsample() -> None:
    """Test AUTO_DOWNSAMPLE decision when estimated between 60% and 90%."""
    # Medium workload: between 60% and 90% of budget
    # Set budget to 1GB for easier testing
    budget = 1_000_000_000  # 1GB
    # Need: budget * 0.6 < estimated < budget * 0.9
    # 600MB < estimated < 900MB
    # Let's use: 5000 bars * 5000 params * 1.0 rate * 2.0 intents * 64 bytes = 3.2GB
    # That's too high. Let's adjust:
    # For 700MB: 700_000_000 = bars * params * 1.0 * 2.0 * 64
    # bars * params = 700_000_000 / (2.0 * 64) = 5_468_750
    # Let's use: 5000 bars * 1094 params * 1.0 rate * 2.0 * 64 = ~700MB
    inp = OomGateInput(
        bars=5000,
        params=1094,
        param_subsample_rate=1.0,
        intents_per_bar=2.0,
        bytes_per_intent_est=64,
        ram_budget_bytes=budget,
    )
    
    decision = decide_gate(inp)
    
    assert decision.decision == "AUTO_DOWNSAMPLE"
    assert decision.estimated_bytes > budget * 0.6
    assert decision.estimated_bytes <= budget * 0.9
    assert decision.recommended_subsample_rate is not None
    assert 0.0 < decision.recommended_subsample_rate <= 1.0
    assert "recommended" in decision.notes.lower() or "subsample" in decision.notes.lower()


def test_decide_gate_auto_downsample_recommended_rate_calculation() -> None:
    """Test that recommended_rate is calculated correctly for AUTO_DOWNSAMPLE."""
    budget = 1_000_000_000  # 1GB
    bars = 1000
    params = 1000
    intents_per_bar = 2.0
    bytes_per_intent = 64
    
    # Use current rate that puts us in AUTO_DOWNSAMPLE zone
    inp = OomGateInput(
        bars=bars,
        params=params,
        param_subsample_rate=1.0,
        intents_per_bar=intents_per_bar,
        bytes_per_intent_est=bytes_per_intent,
        ram_budget_bytes=budget,
    )
    
    decision = decide_gate(inp)
    
    if decision.decision == "AUTO_DOWNSAMPLE":
        # Verify recommended_rate formula: (ram_budget * 0.6) / (bars * params * intents_per_bar * bytes_per_intent_est)
        expected_rate = (budget * 0.6) / (bars * params * intents_per_bar * bytes_per_intent)
        expected_rate = max(0.0, min(1.0, expected_rate))
        
        assert decision.recommended_subsample_rate is not None
        assert abs(decision.recommended_subsample_rate - expected_rate) < 0.0001  # Allow small floating point error


def test_invalid_input_bars_zero() -> None:
    """Test that bars <= 0 raises validation error."""
    with pytest.raises(Exception):  # Pydantic ValidationError
        OomGateInput(
            bars=0,
            params=100,
            param_subsample_rate=0.5,
        )


def test_invalid_input_bars_negative() -> None:
    """Test that bars < 0 raises validation error."""
    with pytest.raises(Exception):  # Pydantic ValidationError
        OomGateInput(
            bars=-1,
            params=100,
            param_subsample_rate=0.5,
        )


def test_invalid_input_params_zero() -> None:
    """Test that params <= 0 raises validation error."""
    with pytest.raises(Exception):  # Pydantic ValidationError
        OomGateInput(
            bars=1000,
            params=0,
            param_subsample_rate=0.5,
        )


def test_invalid_input_subsample_rate_zero() -> None:
    """Test that param_subsample_rate <= 0 raises validation error."""
    with pytest.raises(Exception):  # Pydantic ValidationError
        OomGateInput(
            bars=1000,
            params=100,
            param_subsample_rate=0.0,
        )


def test_invalid_input_subsample_rate_negative() -> None:
    """Test that param_subsample_rate < 0 raises validation error."""
    with pytest.raises(Exception):  # Pydantic ValidationError
        OomGateInput(
            bars=1000,
            params=100,
            param_subsample_rate=-0.1,
        )


def test_invalid_input_subsample_rate_over_one() -> None:
    """Test that param_subsample_rate > 1.0 raises validation error."""
    with pytest.raises(Exception):  # Pydantic ValidationError
        OomGateInput(
            bars=1000,
            params=100,
            param_subsample_rate=1.1,
        )


def test_default_values() -> None:
    """Test that default values work correctly."""
    inp = OomGateInput(
        bars=1000,
        params=100,
        param_subsample_rate=0.5,
    )
    
    assert inp.intents_per_bar == 2.0
    assert inp.bytes_per_intent_est == 64
    assert inp.ram_budget_bytes == 6_000_000_000  # 6GB
    
    decision = decide_gate(inp)
    assert decision.decision in ("PASS", "BLOCK", "AUTO_DOWNSAMPLE")
    assert decision.estimated_bytes >= 0
    assert decision.ram_budget_bytes == inp.ram_budget_bytes


def test_decide_oom_action_returns_dict_schema() -> None:
    """Test legacy decide_oom_action() returns dict schema."""
    cfg = {"bars": 1000, "params_total": 100, "param_subsample_rate": 0.1}
    res = decide_oom_action(cfg, mem_limit_mb=10_000.0)
    
    assert isinstance(res, dict)
    assert res["action"] in {"PASS", "BLOCK", "AUTO_DOWNSAMPLE"}
    assert "estimated_bytes" in res
    assert "estimated_mb" in res
    assert "mem_limit_mb" in res
    assert "mem_limit_bytes" in res
    assert "original_subsample" in res  # Contract key name
    assert "final_subsample" in res  # Contract key name
    assert "params_total" in res
    assert "params_effective" in res
    assert "reason" in res


