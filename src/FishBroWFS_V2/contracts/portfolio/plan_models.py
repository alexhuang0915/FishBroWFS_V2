# src/FishBroWFS_V2/contracts/portfolio/plan_models.py
from __future__ import annotations

from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field, model_validator, field_validator


class SourceRef(BaseModel):
    season: str
    export_name: str
    export_manifest_sha256: str

    # legacy contract: tests expect this key
    candidates_sha256: str

    # keep rev2 fields as optional for forward compat
    candidates_file_sha256: Optional[str] = None
    candidates_items_sha256: Optional[str] = None


class PlannedCandidate(BaseModel):
    candidate_id: str
    strategy_id: str
    dataset_id: str
    params: Dict[str, Any]
    score: float
    season: str
    source_batch: str
    source_export: str

    # rev2 enrichment (optional)
    batch_state: Optional[str] = None
    batch_counts: Optional[Dict[str, Any]] = None
    batch_metrics: Optional[Dict[str, Any]] = None


class PlannedWeight(BaseModel):
    candidate_id: str
    weight: float
    reason: str


class ConstraintsReport(BaseModel):
    # dict of truncated counts: {"ds1": 3, ...} / {"stratA": 3, ...}
    max_per_strategy_truncated: Dict[str, int] = Field(default_factory=dict)
    max_per_dataset_truncated: Dict[str, int] = Field(default_factory=dict)

    # list of candidate_ids clipped
    max_weight_clipped: List[str] = Field(default_factory=list)
    min_weight_clipped: List[str] = Field(default_factory=list)

    renormalization_applied: bool = False
    renormalization_factor: Optional[float] = None


class PlanSummary(BaseModel):
    # ---- legacy fields (tests expect these) ----
    total_candidates: int
    total_weight: float

    # bucket_by is a list of field names used to bucket (e.g. ["dataset_id"])
    bucket_counts: Dict[str, int] = Field(default_factory=dict)
    bucket_weights: Dict[str, float] = Field(default_factory=dict)

    # concentration metric
    concentration_herfindahl: float

    # ---- new fields (optional, for forward compatibility) ----
    num_selected: Optional[int] = None
    num_buckets: Optional[int] = None
    bucket_by: Optional[List[str]] = None
    concentration_top1: Optional[float] = None
    concentration_top3: Optional[float] = None


from FishBroWFS_V2.contracts.portfolio.plan_payloads import PlanCreatePayload


class PortfolioPlan(BaseModel):
    plan_id: str
    generated_at_utc: str

    source: SourceRef
    config: Union[PlanCreatePayload, Dict[str, Any]]

    universe: List[PlannedCandidate]
    weights: List[PlannedWeight]

    summaries: PlanSummary
    constraints_report: ConstraintsReport

    @model_validator(mode="after")
    def _validate_weights_sum(self) -> "PortfolioPlan":
        total = sum(w.weight for w in self.weights)
        # Allow tiny floating tolerance
        if abs(total - 1.0) > 1e-9:
            raise ValueError(f"Total weight must be 1.0, got {total}")
        return self

    @field_validator("config", mode="before")
    @classmethod
    def _normalize_config(cls, v):
        # If v is a PlanCreatePayload, convert to dict
        if isinstance(v, PlanCreatePayload):
            return v.model_dump()
        # If v is already a dict, keep as is
        if isinstance(v, dict):
            return v
        raise ValueError(f"config must be PlanCreatePayload or dict, got {type(v)}")