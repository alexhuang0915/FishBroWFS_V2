
"""Funnel schema definitions.

Defines stage names, specifications, and result indexing for funnel pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class StageName(str, Enum):
    """Stage names for funnel pipeline."""
    STAGE0_COARSE = "stage0_coarse"
    STAGE1_TOPK = "stage1_topk"
    STAGE2_CONFIRM = "stage2_confirm"


@dataclass(frozen=True)
class StageSpec:
    """
    Stage specification for funnel pipeline.
    
    Each stage defines:
    - name: Stage identifier
    - param_subsample_rate: Subsample rate for this stage
    - topk: Optional top-K count (None for Stage2)
    - notes: Additional metadata
    """
    name: StageName
    param_subsample_rate: float
    topk: Optional[int] = None
    notes: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class FunnelPlan:
    """
    Funnel plan containing ordered list of stages.
    
    Stages are executed in order: Stage0 -> Stage1 -> Stage2
    """
    stages: List[StageSpec]


@dataclass(frozen=True)
class FunnelStageIndex:
    """
    Index entry for a single stage execution.
    
    Records:
    - stage: Stage name
    - run_id: Run ID for this stage
    - run_dir: Relative path to run directory
    """
    stage: StageName
    run_id: str
    run_dir: str  # Relative path string


@dataclass(frozen=True)
class FunnelResultIndex:
    """
    Complete funnel execution result index.
    
    Contains:
    - plan: Original funnel plan
    - stages: List of stage execution indices
    """
    plan: FunnelPlan
    stages: List[FunnelStageIndex]


