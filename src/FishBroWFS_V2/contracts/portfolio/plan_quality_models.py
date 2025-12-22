
"""Quality models for portfolio plan grading (GREEN/YELLOW/RED)."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field, ConfigDict

Grade = Literal["GREEN", "YELLOW", "RED"]


class QualitySourceRef(BaseModel):
    """Reference to the source of the plan."""
    plan_id: str
    season: Optional[str] = None
    export_name: Optional[str] = None
    export_manifest_sha256: Optional[str] = None
    candidates_sha256: Optional[str] = None


class QualityThresholds(BaseModel):
    """Thresholds for grading."""
    min_total_candidates: int = 10
    # top1_score thresholds (higher is better)
    green_top1: float = 0.90
    yellow_top1: float = 0.80
    red_top1: float = 0.75
    # top3_score thresholds (higher is better) - kept for compatibility
    green_top3: float = 0.85
    yellow_top3: float = 0.75
    red_top3: float = 0.70
    # effective_n thresholds (higher is better) - test expects 7.0 for GREEN, 5.0 for YELLOW
    green_effective_n: float = 7.0
    yellow_effective_n: float = 5.0
    red_effective_n: float = 4.0
    # bucket_coverage thresholds (higher is better) - test expects 0.90 for GREEN, 0.70 for YELLOW
    green_bucket_coverage: float = 0.90
    yellow_bucket_coverage: float = 0.70
    red_bucket_coverage: float = 0.60
    # constraints_pressure thresholds (lower is better)
    green_constraints_pressure: int = 0
    yellow_constraints_pressure: int = 1
    red_constraints_pressure: int = 2


class QualityMetrics(BaseModel):
    """
    Contract goals:
    - Internal grading code historically uses: top1/top3/top5/bucket_coverage_ratio
    - Hardening tests expect: top1_score/effective_n/bucket_coverage
    We support BOTH via real fields + deterministic properties.
    """
    model_config = ConfigDict(populate_by_name=True, extra="allow")

    total_candidates: int

    # Canonical stored fields (keep legacy names used by grading)
    top1: float = 0.0
    top3: float = 0.0
    top5: float = 0.0

    herfindahl: float
    effective_n: float

    bucket_by: List[str] = Field(default_factory=list)
    bucket_count: int

    bucket_coverage_ratio: float = 0.0
    constraints_pressure: int = 0

    # ---- Compatibility properties expected by tests ----
    @property
    def top1_score(self) -> float:
        return float(self.top1)

    @property
    def top3_score(self) -> float:
        return float(self.top3)

    @property
    def top5_score(self) -> float:
        return float(self.top5)

    @property
    def bucket_coverage(self) -> float:
        return float(self.bucket_coverage_ratio)

    @property
    def concentration_herfindahl(self) -> float:
        return float(self.herfindahl)


class PlanQualityReport(BaseModel):
    """Complete quality report for a portfolio plan."""
    plan_id: str
    generated_at_utc: str
    source: QualitySourceRef
    grade: Grade
    metrics: QualityMetrics
    reasons: List[str]
    thresholds: QualityThresholds
    inputs: Dict[str, str] = Field(default_factory=dict)  # file->sha256

    @classmethod
    def create_now(cls) -> str:
        """Return current UTC timestamp in ISO format with Z suffix."""
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


