
"""Funnel plan builder.

Builds default funnel plan with three stages:
- Stage 0: Coarse subsample (config rate)
- Stage 1: Increased subsample (min(1.0, stage0_rate * 2))
- Stage 2: Full confirm (1.0)
"""

from __future__ import annotations

from FishBroWFS_V2.pipeline.funnel_schema import FunnelPlan, StageName, StageSpec


def build_default_funnel_plan(cfg: dict) -> FunnelPlan:
    """
    Build default funnel plan with three stages.
    
    Rules (locked):
    - Stage 0: subsample = config's param_subsample_rate (coarse exploration)
    - Stage 1: subsample = min(1.0, stage0_rate * 2) (increased density)
    - Stage 2: subsample = 1.0 (full confirm, mandatory)
    
    Args:
        cfg: Configuration dictionary containing:
            - param_subsample_rate: Base subsample rate for Stage 0
            - topk_stage0: Optional top-K for Stage 0 (default: 50)
            - topk_stage1: Optional top-K for Stage 1 (default: 20)
    
    Returns:
        FunnelPlan with three stages
    """
    s0_rate = float(cfg["param_subsample_rate"])
    s1_rate = min(1.0, s0_rate * 2.0)
    s2_rate = 1.0  # Stage2 must be 1.0
    
    return FunnelPlan(stages=[
        StageSpec(
            name=StageName.STAGE0_COARSE,
            param_subsample_rate=s0_rate,
            topk=int(cfg.get("topk_stage0", 50)),
            notes={"rule": "default", "description": "Coarse exploration"},
        ),
        StageSpec(
            name=StageName.STAGE1_TOPK,
            param_subsample_rate=s1_rate,
            topk=int(cfg.get("topk_stage1", 20)),
            notes={"rule": "default", "description": "Top-K refinement"},
        ),
        StageSpec(
            name=StageName.STAGE2_CONFIRM,
            param_subsample_rate=s2_rate,
            topk=None,
            notes={"rule": "default", "description": "Full confirmation"},
        ),
    ])


