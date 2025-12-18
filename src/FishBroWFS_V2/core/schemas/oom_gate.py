"""Pydantic schemas for OOM gate input and output.

Locked schemas for PASS/BLOCK/AUTO_DOWNSAMPLE decisions.
"""

from __future__ import annotations

from pydantic import BaseModel, Field
from typing import Literal


class OomGateInput(BaseModel):
    """
    Input for OOM gate decision.
    
    All fields are required for memory estimation.
    """
    bars: int = Field(gt=0, description="Number of bars")
    params: int = Field(gt=0, description="Total number of parameters")
    param_subsample_rate: float = Field(gt=0.0, le=1.0, description="Subsample rate in [0.0, 1.0]")
    intents_per_bar: float = Field(default=2.0, ge=0.0, description="Estimated intents per bar")
    bytes_per_intent_est: int = Field(default=64, gt=0, description="Estimated bytes per intent")
    ram_budget_bytes: int = Field(default=6_000_000_000, gt=0, description="RAM budget in bytes (default: 6GB)")


class OomGateDecision(BaseModel):
    """
    OOM gate decision output.
    
    Contains decision (PASS/BLOCK/AUTO_DOWNSAMPLE) and recommendations.
    """
    decision: Literal["PASS", "BLOCK", "AUTO_DOWNSAMPLE"]
    estimated_bytes: int = Field(ge=0, description="Estimated memory usage in bytes")
    ram_budget_bytes: int = Field(gt=0, description="RAM budget in bytes")
    recommended_subsample_rate: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Recommended subsample rate (only for AUTO_DOWNSAMPLE)"
    )
    notes: str = Field(default="", description="Human-readable notes about the decision")
