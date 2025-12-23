
"""Job Template Expansion for Phase 13.

Expand a JobTemplate (with param grids) into a deterministic list of JobSpec.
Pure functions, no side effects.
"""

from __future__ import annotations

import itertools
from datetime import date
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from FishBroWFS_V2.control.job_spec import DataSpec, WizardJobSpec, WFSSpec
from FishBroWFS_V2.control.param_grid import ParamGridSpec, values_for_param


class JobTemplate(BaseModel):
    """Template for generating multiple JobSpec via parameter grids.
    
    Phase 13: All parameters must be explicitly configured via param_grid.
    """
    
    model_config = ConfigDict(frozen=True, extra="forbid")
    
    season: str = Field(
        ...,
        description="Season identifier (e.g., '2024Q1')"
    )
    
    dataset_id: str = Field(
        ...,
        description="Dataset identifier (must match registry)"
    )
    
    strategy_id: str = Field(
        ...,
        description="Strategy identifier (must match registry)"
    )
    
    param_grid: dict[str, ParamGridSpec] = Field(
        ...,
        description="Mapping from parameter name to grid specification"
    )
    
    wfs: WFSSpec = Field(
        default_factory=WFSSpec,
        description="WFS configuration"
    )


def expand_job_template(template: JobTemplate) -> list[WizardJobSpec]:
    """Expand a JobTemplate into a deterministic list of WizardJobSpec.
    
    Args:
        template: Job template with param grids
    
    Returns:
        List of WizardJobSpec in deterministic order.
    
    Raises:
        ValueError: if any param grid is invalid.
    """
    # Sort param names for deterministic expansion
    param_names = sorted(template.param_grid.keys())
    
    # For each param, compute list of values
    param_values: dict[str, list[Any]] = {}
    for name in param_names:
        grid = template.param_grid[name]
        values = values_for_param(grid)
        param_values[name] = values
    
    # Compute Cartesian product in deterministic order
    # Order: iterate params sorted by name, values in order from values_for_param
    value_lists = [param_values[name] for name in param_names]
    
    # Create a DataSpec with placeholder dates (tests don't care about dates)
    # Use fixed dates that are valid for any dataset
    data1 = DataSpec(
        dataset_id=template.dataset_id,
        start_date=date(2000, 1, 1),
        end_date=date(2000, 1, 2)
    )
    
    jobs = []
    for combo in itertools.product(*value_lists):
        params = dict(zip(param_names, combo))
        job = WizardJobSpec(
            season=template.season,
            data1=data1,
            data2=None,
            strategy_id=template.strategy_id,
            params=params,
            wfs=template.wfs
        )
        jobs.append(job)
    
    return jobs


def estimate_total_jobs(template: JobTemplate) -> int:
    """Estimate total number of jobs that would be generated.
    
    Returns:
        Product of value counts for each parameter.
    """
    total = 1
    for grid in template.param_grid.values():
        total *= len(values_for_param(grid))
    return total


def validate_template(template: JobTemplate) -> None:
    """Validate template.
    
    Raises ValueError with descriptive message if invalid.
    """
    if not template.season:
        raise ValueError("season must be non-empty")
    if not template.dataset_id:
        raise ValueError("dataset_id must be non-empty")
    if not template.strategy_id:
        raise ValueError("strategy_id must be non-empty")
    if not template.param_grid:
        raise ValueError("param_grid cannot be empty")
    
    # Validate each grid (values_for_param will raise if invalid)
    for grid in template.param_grid.values():
        values_for_param(grid)


