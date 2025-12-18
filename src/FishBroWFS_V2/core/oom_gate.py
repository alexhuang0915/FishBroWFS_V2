"""OOM gate decision maker.

Pure functions for estimating memory usage and deciding PASS/BLOCK/AUTO_DOWNSAMPLE.
No engine dependencies, no file I/O - pure computation only.

This module provides two APIs:
1. New API (for B5-C): estimate_bytes(), decide_gate() with Pydantic schemas
2. Legacy API (for pipeline/tests): decide_oom_action() with dict I/O
"""

from __future__ import annotations

from typing import Any, Dict, Literal, Optional

import FishBroWFS_V2.core.oom_cost_model as oom_cost_model
from FishBroWFS_V2.core.schemas.oom_gate import OomGateDecision, OomGateInput

OomAction = Literal["PASS", "BLOCK", "AUTO_DOWNSAMPLE"]


def estimate_bytes(inp: OomGateInput) -> int:
    """
    Estimate memory usage in bytes.
    
    Formula (locked):
        estimated = bars * params * subsample * intents_per_bar * bytes_per_intent_est
    
    Args:
        inp: OomGateInput with bars, params, param_subsample_rate, etc.
        
    Returns:
        Estimated memory usage in bytes
    """
    estimated = (
        inp.bars
        * inp.params
        * inp.param_subsample_rate
        * inp.intents_per_bar
        * inp.bytes_per_intent_est
    )
    return int(estimated)


def decide_gate(inp: OomGateInput) -> OomGateDecision:
    """
    Decide OOM gate action: PASS, BLOCK, or AUTO_DOWNSAMPLE.
    
    Rules (locked):
    - PASS: estimated <= ram_budget * 0.6
    - BLOCK: estimated > ram_budget * 0.9
    - AUTO_DOWNSAMPLE: otherwise, recommended_rate = (ram_budget * 0.6) / (bars * params * intents_per_bar * bytes_per_intent_est)
    
    Args:
        inp: OomGateInput with configuration
        
    Returns:
        OomGateDecision with decision and recommendations
    """
    estimated = estimate_bytes(inp)
    ram_budget = inp.ram_budget_bytes
    
    # Thresholds (locked)
    pass_threshold = ram_budget * 0.6
    block_threshold = ram_budget * 0.9
    
    if estimated <= pass_threshold:
        return OomGateDecision(
            decision="PASS",
            estimated_bytes=estimated,
            ram_budget_bytes=ram_budget,
            recommended_subsample_rate=None,
            notes=f"Estimated {estimated:,} bytes <= {pass_threshold:,.0f} bytes (60% of budget)",
        )
    
    if estimated > block_threshold:
        return OomGateDecision(
            decision="BLOCK",
            estimated_bytes=estimated,
            ram_budget_bytes=ram_budget,
            recommended_subsample_rate=None,
            notes=f"Estimated {estimated:,} bytes > {block_threshold:,.0f} bytes (90% of budget) - BLOCKED",
        )
    
    # AUTO_DOWNSAMPLE: calculate recommended rate
    # recommended_rate = (ram_budget * 0.6) / (bars * params * intents_per_bar * bytes_per_intent_est)
    denominator = inp.bars * inp.params * inp.intents_per_bar * inp.bytes_per_intent_est
    if denominator > 0:
        recommended_rate = (ram_budget * 0.6) / denominator
        # Clamp to [0.0, 1.0]
        recommended_rate = max(0.0, min(1.0, recommended_rate))
    else:
        recommended_rate = 0.0
    
    return OomGateDecision(
        decision="AUTO_DOWNSAMPLE",
        estimated_bytes=estimated,
        ram_budget_bytes=ram_budget,
        recommended_subsample_rate=recommended_rate,
        notes=(
            f"Estimated {estimated:,} bytes between {pass_threshold:,.0f} and {block_threshold:,.0f} "
            f"- recommended subsample rate: {recommended_rate:.4f}"
        ),
    )


def _params_effective(params_total: int, rate: float) -> int:
    """Calculate effective params with floor rule (at least 1)."""
    return max(1, int(params_total * rate))


def _estimate_ops(cfg: dict, *, params_effective: int) -> int:
    """
    Safely estimate operations count.
    
    Priority:
    1. Use oom_cost_model.estimate_ops if available (most consistent)
    2. Fallback to deterministic formula
    
    Args:
        cfg: Configuration dictionary
        params_effective: Effective params count (already calculated)
        
    Returns:
        Estimated operations count
    """
    # If cost model has ops estimate, use it (most consistent)
    if hasattr(oom_cost_model, "estimate_ops"):
        return int(oom_cost_model.estimate_ops(cfg))
    if hasattr(oom_cost_model, "estimate_ops_est"):
        return int(oom_cost_model.estimate_ops_est(cfg))
    
    # Fallback: at least stable and monotonic
    bars = int(cfg.get("bars", 0))
    intents_per_bar = float(cfg.get("intents_per_bar", 2.0))
    return int(bars * params_effective * intents_per_bar)


def decide_oom_action(
    cfg: Dict[str, Any],
    *,
    mem_limit_mb: float,
    allow_auto_downsample: bool = True,
    auto_downsample_step: float = 0.5,
    auto_downsample_min: float = 0.02,
    work_factor: float = 2.0,
) -> Dict[str, Any]:
    """
    Backward-compatible OOM gate used by funnel_runner + contract tests.

    Returns a dict (schema-as-dict) consumed by pipeline and written to artifacts/README.
    This function MAY mutate cfg['param_subsample_rate'] when AUTO_DOWNSAMPLE.
    
    Uses estimate_memory_bytes() from oom_cost_model (tests monkeypatch this).
    Must use module import (oom_cost_model.estimate_memory_bytes) for monkeypatch to work.
    
    Args:
        cfg: Configuration dictionary with bars, params_total, param_subsample_rate, etc.
        mem_limit_mb: Memory limit in MB
        allow_auto_downsample: Whether to allow automatic downsample
        auto_downsample_step: Multiplier for each downsample step (default: 0.5)
        auto_downsample_min: Minimum subsample rate (default: 0.02)
        work_factor: Work factor for memory estimation (default: 2.0)
        
    Returns:
        Dictionary with action, reason, estimated_bytes, and metadata
    """
    bars = int(cfg.get("bars", 0))
    params_total = int(cfg.get("params_total", 0))
    original = float(cfg.get("param_subsample_rate", 1.0))
    mem_limit_bytes = int(mem_limit_mb * 1024.0 * 1024.0)

    def _result(action: str, reason: str, est_bytes: int, final_rate: float) -> Dict[str, Any]:
        """Helper to build consistent result dict."""
        params_eff = _params_effective(params_total, final_rate)
        ops_est = _estimate_ops(cfg, params_effective=params_eff)
        
        # Calculate time estimate from ops_est
        ops_per_sec_est = float(cfg.get("ops_per_sec_est", 2.0e7))
        time_est_s = float(ops_est) / ops_per_sec_est if ops_per_sec_est > 0 else 0.0
        
        estimates = {
            "mem_est_bytes": int(est_bytes),
            "mem_est_mb": float(est_bytes) / (1024.0 * 1024.0),
            "mem_limit_mb": float(mem_limit_mb),
            "mem_limit_bytes": int(mem_limit_bytes),
            "ops_est": int(ops_est),
            "time_est_s": float(time_est_s),
        }
        return {
            "action": action,
            "reason": reason,
            # ✅ tests/test_oom_gate.py needs this
            "estimated_bytes": int(est_bytes),
            "estimated_mb": float(est_bytes) / (1024.0 * 1024.0),
            # ✅ NEW: required by tests/test_oom_gate.py
            "mem_limit_mb": float(mem_limit_mb),
            "mem_limit_bytes": int(mem_limit_bytes),
            # Original subsample contract
            "original_subsample": float(original),
            "final_subsample": float(final_rate),
            # Funnel/README common fields (preserved)
            "params_total": int(params_total),
            "params_effective": int(params_eff),
            # ✅ funnel_runner/tests needs estimates.ops_est / estimates.mem_est_mb
            "estimates": estimates,
            # Other debug fields
            "allow_auto_downsample": bool(allow_auto_downsample),
            "auto_downsample_step": float(auto_downsample_step),
            "auto_downsample_min": float(auto_downsample_min),
            "work_factor": float(work_factor),
        }

    # invalid input → BLOCK（但仍回 schema）
    if bars <= 0 or params_total <= 0:
        return _result("BLOCK", "invalid_input", 0, original)

    # estimate at original
    est0 = int(oom_cost_model.estimate_memory_bytes(cfg, work_factor=work_factor))
    if est0 <= mem_limit_bytes:
        return _result("PASS", "pass_under_limit", est0, original)

    if not allow_auto_downsample:
        return _result("BLOCK", "block: over limit (auto-downsample disabled)", est0, original)

    # auto-downsample loop
    rate = original
    while rate > auto_downsample_min:
        rate = max(auto_downsample_min, rate * auto_downsample_step)
        cfg["param_subsample_rate"] = float(rate)  # NOTE: mutation expected by integration tests
        est = int(oom_cost_model.estimate_memory_bytes(cfg, work_factor=work_factor))
        if est <= mem_limit_bytes:
            return _result("AUTO_DOWNSAMPLE", "auto-downsample: over limit, reduced subsample", est, rate)

    # still over limit at min
    cfg["param_subsample_rate"] = float(auto_downsample_min)
    est_min = int(oom_cost_model.estimate_memory_bytes(cfg, work_factor=work_factor))
    return _result("BLOCK", "block: min_subsample still too large", est_min, auto_downsample_min)
