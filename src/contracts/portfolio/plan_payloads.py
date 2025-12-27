
from __future__ import annotations

from typing import List, Literal, Optional
from pydantic import BaseModel, Field, model_validator


EnrichField = Literal["batch_state", "batch_counts", "batch_metrics"]
BucketKey = Literal["dataset_id", "strategy_id"]
WeightingPolicy = Literal["equal", "score_weighted", "bucket_equal"]


class PlanCreatePayload(BaseModel):
    season: str
    export_name: str

    top_n: int = Field(gt=0, le=500, default=50)
    max_per_strategy: int = Field(gt=0, le=500, default=100)
    max_per_dataset: int = Field(gt=0, le=500, default=100)

    weighting: WeightingPolicy = "bucket_equal"
    bucket_by: List[BucketKey] = Field(default_factory=lambda: ["dataset_id"])

    max_weight: float = Field(gt=0.0, le=1.0, default=0.2)
    min_weight: float = Field(ge=0.0, le=1.0, default=0.0)

    enrich_with_batch_api: bool = True
    enrich_fields: List[EnrichField] = Field(
        default_factory=lambda: ["batch_state", "batch_counts", "batch_metrics"]
    )

    note: Optional[str] = None

    @model_validator(mode="after")
    def _validate_ranges(self) -> "PlanCreatePayload":
        if not self.bucket_by:
            raise ValueError("bucket_by must be non-empty")
        if self.min_weight > self.max_weight:
            raise ValueError("min_weight must be <= max_weight")
        return self


