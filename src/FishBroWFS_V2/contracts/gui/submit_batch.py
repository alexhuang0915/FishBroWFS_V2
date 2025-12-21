"""
Submit batch payload contract for GUI.

Contract:
- Must not contain execution / engine flags
- Job count ≤ 1000
- Ordering does not affect batch_id (handled by API)
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional
from pydantic import BaseModel, Field, field_validator


class JobTemplateRef(BaseModel):
    """Reference to a job template (GUI-side)."""
    dataset_id: str
    strategy_id: str
    param_grid_id: str
    # Additional GUI-specific fields may be added here, but must not affect execution


class SubmitBatchPayload(BaseModel):
    """Payload for submitting a batch of jobs from GUI."""
    dataset_id: str
    strategy_id: str
    param_grid_id: str
    jobs: list[JobTemplateRef]
    outputs_root: Path = Field(default=Path("outputs"))

    @field_validator("jobs")
    @classmethod
    def validate_job_count(cls, v: list[JobTemplateRef]) -> list[JobTemplateRef]:
        if len(v) > 1000:
            raise ValueError("Job count must be ≤ 1000")
        if len(v) == 0:
            raise ValueError("Job list cannot be empty")
        return v

    @field_validator("outputs_root")
    @classmethod
    def ensure_path(cls, v: Path) -> Path:
        # Ensure it's a Path object (already is)
        return v