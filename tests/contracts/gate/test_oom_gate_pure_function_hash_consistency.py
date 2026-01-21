
"""Tests for OOM gate pure function hash consistency.

Tests that decide_oom_action never mutates input cfg and returns new_cfg SSOT.
"""

from __future__ import annotations

import pytest

from core.config_hash import stable_config_hash
from core.config_snapshot import make_config_snapshot
from core.oom_gate import decide_oom_action


def test_oom_gate_pure_function_hash_consistency(monkeypatch) -> None:
    """
    Test that decide_oom_action is pure function (no mutation).
    
    Uses monkeypatch to ensure subsample-sensitive memory estimation,
    guaranteeing that subsample=1.0 exceeds limit and subsample reduction
    triggers AUTO_DOWNSAMPLE.
    
    Verifies:
    - Original cfg subsample remains unchanged
    - decision.new_cfg has modified subsample
    - Hash computed from new_cfg differs from original
    - manifest/snapshot records final_subsample correctly
    """
    def mock_estimate_memory_bytes(cfg, work_factor=2.0):
        """Make mem scale with subsample so AUTO_DOWNSAMPLE is meaningful."""
        subsample = float(cfg.get("param_subsample_rate", 1.0))
        # 100MB at subsample=1.0, 50MB at 0.5, etc.
        base = 100 * 1024 * 1024
        return int(base * subsample)
    
    monkeypatch.setattr(
        "core.oom_cost_model.estimate_memory_bytes",
        mock_estimate_memory_bytes,
    )
    
    cfg = {
        "bars": 1,
        "params_total": 1,
        "param_subsample_rate": 1.0,
    }
    mem_limit_mb = 60.0  # 1.0 => 100MB (over), 0.5 => 50MB (under)
    
    decision = decide_oom_action(cfg, mem_limit_mb=mem_limit_mb, allow_auto_downsample=True)
    
    # Verify original cfg unchanged
    assert cfg["param_subsample_rate"] == 1.0, "Original cfg must not be mutated"
    
    # Verify decision has new_cfg
    assert "new_cfg" in decision, "decision must contain new_cfg"
    new_cfg = decision["new_cfg"]
    
    # Lock behavior: allow_auto_downsample=True 時不得 PASS，必須 AUTO_DOWNSAMPLE（除非低於 min）
    assert decision["action"] == "AUTO_DOWNSAMPLE", "Should trigger AUTO_DOWNSAMPLE when allow_auto_downsample=True"
    
    # Verify new_cfg has modified subsample
    assert new_cfg["param_subsample_rate"] < 1.0, "new_cfg should have reduced subsample"
    assert decision["final_subsample"] < 1.0, "final_subsample should be reduced"
    assert decision["final_subsample"] < decision["original_subsample"], "final_subsample must be < original_subsample"
    assert decision["new_cfg"]["param_subsample_rate"] == decision["final_subsample"], "new_cfg subsample must match final_subsample"
    
    # Verify hash consistency
    original_snapshot = make_config_snapshot(cfg)
    original_hash = stable_config_hash(original_snapshot)
    
    new_snapshot = make_config_snapshot(new_cfg)
    new_hash = stable_config_hash(new_snapshot)
    
    assert original_hash != new_hash, "Hash should differ after subsample change"
    
    # Verify final_subsample matches new_cfg
    assert decision["final_subsample"] == new_cfg["param_subsample_rate"], (
        "final_subsample must match new_cfg subsample"
    )
    
    # Verify original_subsample preserved
    assert decision["original_subsample"] == 1.0, "original_subsample must be preserved"


