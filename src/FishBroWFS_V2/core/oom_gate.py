
"""OOM gate decision maker.

Pure functions for estimating memory usage and deciding PASS/BLOCK/AUTO_DOWNSAMPLE.
No engine dependencies, no file I/O - pure computation only.

This module provides two APIs:
1. New API (for B5-C): estimate_bytes(), decide_gate() with Pydantic schemas
2. Legacy API (for pipeline/tests): decide_oom_action() with dict I/O
"""

from __future__ import annotations

from collections.abc import Mapping
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


def _estimate_bytes_legacy(cfg: Mapping[str, Any] | Dict[str, Any]) -> int:
    """
    Estimate memory bytes using unified formula when keys are available.
    
    Formula (locked): bars * params_total * param_subsample_rate * intents_per_bar * bytes_per_intent_est
    
    Falls back to oom_cost_model.estimate_memory_bytes if keys are missing.
    
    Args:
        cfg: Configuration dictionary
        
    Returns:
        Estimated memory usage in bytes
    """
    keys = ("bars", "params_total", "param_subsample_rate", "intents_per_bar", "bytes_per_intent_est")
    if all(k in cfg for k in keys):
        return int(
            int(cfg["bars"])
            * int(cfg["params_total"])
            * float(cfg["param_subsample_rate"])
            * float(cfg["intents_per_bar"])
            * int(cfg["bytes_per_intent_est"])
        )
    # Fallback to cost model
    return int(oom_cost_model.estimate_memory_bytes(dict(cfg), work_factor=2.0))


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
    cfg: Mapping[str, Any] | Dict[str, Any],
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
    This function NEVER mutates cfg - returns new_cfg in result dict.
    
    Uses estimate_memory_bytes() from oom_cost_model (tests monkeypatch this).
    Must use module import (oom_cost_model.estimate_memory_bytes) for monkeypatch to work.
    
    Algorithm: Monotonic step-based downsample search
    - If mem_est(original_subsample) <= limit → PASS
    - If over limit and allow_auto_downsample=False → BLOCK
    - If over limit and allow_auto_downsample=True:
      - Step-based search: cur * step (e.g., 0.5 → 0.25 → 0.125...)
      - Re-estimate mem_est at each candidate subsample
      - If mem_est <= limit → AUTO_DOWNSAMPLE with that subsample
      - If reach min_rate and still over limit → BLOCK
    
    Args:
        cfg: Configuration dictionary with bars, params_total, param_subsample_rate, etc.
        mem_limit_mb: Memory limit in MB
        allow_auto_downsample: Whether to allow automatic downsample
        auto_downsample_step: Multiplier for each downsample step (default: 0.5, must be < 1.0)
        auto_downsample_min: Minimum subsample rate (default: 0.02)
        work_factor: Work factor for memory estimation (default: 2.0)
        
    Returns:
        Dictionary with action, reason, estimated_bytes, new_cfg, and metadata
    """
    # pure: never mutate caller
    base_cfg = dict(cfg)
    
    bars = int(base_cfg.get("bars", 0))
    params_total = int(base_cfg.get("params_total", 0))
    
    def _mem_mb(cfg_dict: dict[str, Any], work_factor: float) -> float:
        """
        Estimate memory in MB.
        
        Always uses oom_cost_model.estimate_memory_bytes to respect monkeypatch.
        """
        b = oom_cost_model.estimate_memory_bytes(cfg_dict, work_factor=work_factor)
        return float(b) / (1024.0 * 1024.0)
    
    original = float(base_cfg.get("param_subsample_rate", 1.0))
    original = max(0.0, min(1.0, original))
    
    # invalid input → BLOCK
    if bars <= 0 or params_total <= 0:
        mem0 = _mem_mb(base_cfg, work_factor)
        return _build_result(
            action="BLOCK",
            reason="invalid_input",
            new_cfg=base_cfg,
            original_subsample=original,
            final_subsample=original,
            mem_est_mb=mem0,
            mem_limit_mb=mem_limit_mb,
            params_total=params_total,
            allow_auto_downsample=allow_auto_downsample,
            auto_downsample_step=auto_downsample_step,
            auto_downsample_min=auto_downsample_min,
            work_factor=work_factor,
        )
    
    mem0 = _mem_mb(base_cfg, work_factor)
    
    if mem0 <= mem_limit_mb:
        return _build_result(
            action="PASS",
            reason="pass_under_limit",
            new_cfg=dict(base_cfg),
            original_subsample=original,
            final_subsample=original,
            mem_est_mb=mem0,
            mem_limit_mb=mem_limit_mb,
            params_total=params_total,
            allow_auto_downsample=allow_auto_downsample,
            auto_downsample_step=auto_downsample_step,
            auto_downsample_min=auto_downsample_min,
            work_factor=work_factor,
        )
    
    if not allow_auto_downsample:
        return _build_result(
            action="BLOCK",
            reason="block: over limit (auto-downsample disabled)",
            new_cfg=dict(base_cfg),
            original_subsample=original,
            final_subsample=original,
            mem_est_mb=mem0,
            mem_limit_mb=mem_limit_mb,
            params_total=params_total,
            allow_auto_downsample=allow_auto_downsample,
            auto_downsample_step=auto_downsample_step,
            auto_downsample_min=auto_downsample_min,
            work_factor=work_factor,
        )
    
    step = float(auto_downsample_step)
    if not (0.0 < step < 1.0):
        # contract: step must reduce
        step = 0.5
    
    min_rate = float(auto_downsample_min)
    min_rate = max(0.0, min(1.0, min_rate))
    
    # Monotonic step-search: always decrease
    cur = original
    best_cfg: dict[str, Any] | None = None
    best_mem: float | None = None
    
    while True:
        nxt = cur * step
        # Clamp to min_rate before evaluating
        if nxt < min_rate:
            nxt = min_rate
        
        # if we can no longer decrease, break
        if nxt >= cur:
            break
        
        cand = dict(base_cfg)
        cand["param_subsample_rate"] = float(nxt)
        mem_c = _mem_mb(cand, work_factor)
        
        if mem_c <= mem_limit_mb:
            best_cfg = cand
            best_mem = mem_c
            break
        
        # still over limit
        cur = nxt
        # Only break if we've evaluated min_rate and it's still over
        if cur <= min_rate + 1e-12:
            # We *have evaluated* min_rate and it's still over => BLOCK
            break
    
    if best_cfg is not None and best_mem is not None:
        final_subsample = float(best_cfg["param_subsample_rate"])
        # Ensure monotonicity: final_subsample <= original
        assert final_subsample <= original, f"final_subsample {final_subsample} > original {original}"
        return _build_result(
            action="AUTO_DOWNSAMPLE",
            reason="auto-downsample: over limit, reduced subsample",
            new_cfg=best_cfg,
            original_subsample=original,
            final_subsample=final_subsample,
            mem_est_mb=best_mem,
            mem_limit_mb=mem_limit_mb,
            params_total=params_total,
            allow_auto_downsample=allow_auto_downsample,
            auto_downsample_step=auto_downsample_step,
            auto_downsample_min=auto_downsample_min,
            work_factor=work_factor,
        )
    
    # even at minimum still over limit => BLOCK
    # Only reach here if we've evaluated min_rate and it's still over
    min_cfg = dict(base_cfg)
    min_cfg["param_subsample_rate"] = float(min_rate)
    mem_min = _mem_mb(min_cfg, work_factor)
    
    return _build_result(
        action="BLOCK",
        reason="block: min_subsample still too large",
        new_cfg=min_cfg,  # keep audit: this is the best we can do
        original_subsample=original,
        final_subsample=float(min_rate),
        mem_est_mb=mem_min,
        mem_limit_mb=mem_limit_mb,
        params_total=params_total,
        allow_auto_downsample=allow_auto_downsample,
        auto_downsample_step=auto_downsample_step,
        auto_downsample_min=auto_downsample_min,
        work_factor=work_factor,
    )


def _build_result(
    *,
    action: str,
    reason: str,
    new_cfg: dict[str, Any],
    original_subsample: float,
    final_subsample: float,
    mem_est_mb: float,
    mem_limit_mb: float,
    params_total: int,
    allow_auto_downsample: bool,
    auto_downsample_step: float,
    auto_downsample_min: float,
    work_factor: float,
) -> Dict[str, Any]:
    """Helper to build consistent result dict."""
    params_eff = _params_effective(params_total, final_subsample)
    ops_est = _estimate_ops(new_cfg, params_effective=params_eff)
    
    # Calculate time estimate from ops_est
    ops_per_sec_est = float(new_cfg.get("ops_per_sec_est", 2.0e7))
    time_est_s = float(ops_est) / ops_per_sec_est if ops_per_sec_est > 0 else 0.0
    
    mem_est_bytes = int(mem_est_mb * 1024.0 * 1024.0)
    mem_limit_bytes = int(mem_limit_mb * 1024.0 * 1024.0)
    
    estimates = {
        "mem_est_bytes": int(mem_est_bytes),
        "mem_est_mb": float(mem_est_mb),
        "mem_limit_mb": float(mem_limit_mb),
        "mem_limit_bytes": int(mem_limit_bytes),
        "ops_est": int(ops_est),
        "time_est_s": float(time_est_s),
    }
    return {
        "action": action,
        "reason": reason,
        # ✅ tests/test_oom_gate.py needs this
        "estimated_bytes": int(mem_est_bytes),
        "estimated_mb": float(mem_est_mb),
        # ✅ NEW: required by tests/test_oom_gate.py
        "mem_limit_mb": float(mem_limit_mb),
        "mem_limit_bytes": int(mem_limit_bytes),
        # Original subsample contract
        "original_subsample": float(original_subsample),
        "final_subsample": float(final_subsample),
        # ✅ NEW: new_cfg SSOT (never mutate original cfg)
        "new_cfg": new_cfg,
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


