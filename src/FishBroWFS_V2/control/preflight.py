"""Preflight check - OOM gate and cost summary."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from FishBroWFS_V2.core.oom_gate import decide_oom_action


@dataclass(frozen=True)
class PreflightResult:
    """Preflight check result."""

    action: Literal["PASS", "BLOCK", "AUTO_DOWNSAMPLE"]
    reason: str
    original_subsample: float
    final_subsample: float
    estimated_bytes: int
    estimated_mb: float
    mem_limit_mb: float
    mem_limit_bytes: int
    estimates: dict[str, Any]  # must include ops_est, time_est_s, mem_est_mb, ...


def run_preflight(cfg_snapshot: dict[str, Any]) -> PreflightResult:
    """
    Run preflight check (pure, no I/O).
    
    Returns what UI shows in CHECK panel.
    
    Args:
        cfg_snapshot: Sanitized config snapshot (no ndarrays)
        
    Returns:
        PreflightResult with OOM gate decision and estimates
    """
    # Extract mem_limit_mb from config (default: 6000 MB = 6GB)
    mem_limit_mb = float(cfg_snapshot.get("mem_limit_mb", 6000.0))
    
    # Run OOM gate decision
    gate_result = decide_oom_action(
        cfg_snapshot,
        mem_limit_mb=mem_limit_mb,
        allow_auto_downsample=cfg_snapshot.get("allow_auto_downsample", True),
        auto_downsample_step=cfg_snapshot.get("auto_downsample_step", 0.5),
        auto_downsample_min=cfg_snapshot.get("auto_downsample_min", 0.02),
        work_factor=cfg_snapshot.get("work_factor", 2.0),
    )
    
    return PreflightResult(
        action=gate_result["action"],
        reason=gate_result["reason"],
        original_subsample=gate_result["original_subsample"],
        final_subsample=gate_result["final_subsample"],
        estimated_bytes=gate_result["estimated_bytes"],
        estimated_mb=gate_result["estimated_mb"],
        mem_limit_mb=gate_result["mem_limit_mb"],
        mem_limit_bytes=gate_result["mem_limit_bytes"],
        estimates=gate_result["estimates"],
    )

