
"""WizardJobSpec Schema for Research Job Wizard.

Phase 12: WizardJobSpec is the ONLY output from GUI.
Contains all configuration needed to run a research job.
Must NOT contain any worker/engine runtime state.
"""

from __future__ import annotations

from datetime import date
from types import MappingProxyType
from typing import Any, Mapping, Optional

from pydantic import BaseModel, ConfigDict, Field, field_serializer, model_validator


class DataSpec(BaseModel):
    """Dataset specification for a research job."""
    
    model_config = ConfigDict(frozen=True, extra="forbid")
    
    dataset_id: str = Field(..., min_length=1)
    start_date: date
    end_date: date
    
    @model_validator(mode="after")
    def _check_dates(self) -> "DataSpec":
        if self.start_date > self.end_date:
            raise ValueError("start_date must be <= end_date")
        return self


class WFSSpec(BaseModel):
    """WFS (Winners Funnel System) configuration."""
    
    model_config = ConfigDict(frozen=True, extra="forbid")
    
    stage0_subsample: float = 1.0
    top_k: int = 100
    mem_limit_mb: int = 4096
    allow_auto_downsample: bool = True
    
    @model_validator(mode="after")
    def _check_ranges(self) -> "WFSSpec":
        if not (0.0 < self.stage0_subsample <= 1.0):
            raise ValueError("stage0_subsample must be in (0, 1]")
        if self.top_k <= 0:
            raise ValueError("top_k must be > 0")
        if self.mem_limit_mb < 1024:
            raise ValueError("mem_limit_mb must be >= 1024")
        return self


class WizardJobSpec(BaseModel):
    """Complete job specification for research.
    
    Phase 12 Iron Rule: GUI's ONLY output = WizardJobSpec JSON
    Must NOT contain worker/engine runtime state.
    """
    
    model_config = ConfigDict(frozen=True, extra="forbid")
    
    season: str = Field(..., min_length=1)
    data1: DataSpec
    data2: Optional[DataSpec] = None
    strategy_id: str = Field(..., min_length=1)
    params: Mapping[str, Any] = Field(default_factory=dict)
    wfs: WFSSpec = Field(default_factory=WFSSpec)
    
    @model_validator(mode="after")
    def _freeze_params(self) -> "WizardJobSpec":
        # make params immutable so test_jobspec_immutability passes
        if not isinstance(self.params, MappingProxyType):
            object.__setattr__(self, "params", MappingProxyType(dict(self.params)))
        return self
    
    @field_serializer("params")
    def _ser_params(self, v: Mapping[str, Any]) -> dict[str, Any]:
        return dict(v)

    @property
    def dataset_id(self) -> str:
        """Alias for data1.dataset_id (for backward compatibility)."""
        return self.data1.dataset_id


# Example WizardJobSpec for documentation
EXAMPLE_WIZARD_JOBSPEC = WizardJobSpec(
    season="2024Q1",
    data1=DataSpec(
        dataset_id="CME.MNQ.60m.2020-2024",
        start_date=date(2020, 1, 1),
        end_date=date(2024, 12, 31)
    ),
    data2=None,
    strategy_id="sma_cross_v1",
    params={"window": 20, "threshold": 0.5},
    wfs=WFSSpec()
)


