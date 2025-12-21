"""Parameter Grid Expansion for Phase 13.

Pure functions for turning ParamSpec + user grid config into value lists.
Deterministic ordering, no floating drift surprises.
"""

from __future__ import annotations

import math
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from FishBroWFS_V2.strategy.param_schema import ParamSpec


class GridMode(str, Enum):
    """Grid expansion mode."""
    SINGLE = "single"
    RANGE = "range"
    MULTI = "multi"


class ParamGridSpec(BaseModel):
    """User-defined grid specification for a single parameter.
    
    Exactly one of the three modes must be active.
    """
    
    model_config = ConfigDict(frozen=True, extra="forbid")
    
    mode: GridMode = Field(
        ...,
        description="Grid expansion mode"
    )
    
    single_value: Any | None = Field(
        default=None,
        description="Single value for mode='single'"
    )
    
    range_start: float | int | None = Field(
        default=None,
        description="Start of range (inclusive) for mode='range'"
    )
    
    range_end: float | int | None = Field(
        default=None,
        description="End of range (inclusive) for mode='range'"
    )
    
    range_step: float | int | None = Field(
        default=None,
        description="Step size for mode='range'"
    )
    
    multi_values: list[Any] | None = Field(
        default=None,
        description="List of values for mode='multi'"
    )
    
    @field_validator("mode", mode="before")
    @classmethod
    def validate_mode(cls, v: Any) -> GridMode:
        if isinstance(v, str):
            v = v.lower()
        return GridMode(v)
    
    @field_validator("single_value", "range_start", "range_end", "range_step", "multi_values", mode="after")
    @classmethod
    def validate_mode_consistency(cls, v: Any, info) -> Any:
        """Ensure only fields relevant to the active mode are set."""
        mode = info.data.get("mode")
        if mode is None:
            return v
        
        field_name = info.field_name
        
        # Map fields to allowed modes
        allowed_for = {
            "single_value": [GridMode.SINGLE],
            "range_start": [GridMode.RANGE],
            "range_end": [GridMode.RANGE],
            "range_step": [GridMode.RANGE],
            "multi_values": [GridMode.MULTI],
        }
        
        if field_name in allowed_for:
            if mode not in allowed_for[field_name]:
                if v is not None:
                    raise ValueError(
                        f"Field '{field_name}' must be None when mode='{mode.value}'"
                    )
            else:
                if v is None:
                    raise ValueError(
                        f"Field '{field_name}' must be set when mode='{mode.value}'"
                    )
        return v
    
    @field_validator("range_step")
    @classmethod
    def validate_range_step(cls, v: float | int | None) -> float | int | None:
        # Allow zero step; validation will be done in validate_grid_for_param
        return v
    
    @field_validator("range_start", "range_end")
    @classmethod
    def validate_range_order(cls, v: float | int | None, info) -> float | int | None:
        # Allow start > end; validation will be done in validate_grid_for_param
        return v
    
    @field_validator("multi_values")
    @classmethod
    def validate_multi_values(cls, v: list[Any] | None) -> list[Any] | None:
        # Allow empty list; validation will be done in validate_grid_for_param
        return v


def values_for_param(grid: ParamGridSpec) -> list[Any]:
    """Compute deterministic list of values for a parameter.
    
    Args:
        grid: User-defined grid configuration
    
    Returns:
        Sorted unique list of values in deterministic order.
    
    Raises:
        ValueError: if grid is invalid.
    """
    if grid.mode == GridMode.SINGLE:
        return [grid.single_value]
    
    elif grid.mode == GridMode.RANGE:
        start = grid.range_start
        end = grid.range_end
        step = grid.range_step
        
        if start is None or end is None or step is None:
            raise ValueError("range mode requires start, end, and step")
        
        if start > end:
            raise ValueError("start <= end")
        
        # Determine if values are integer-like
        if isinstance(start, int) and isinstance(end, int) and isinstance(step, int):
            # Integer range inclusive
            values = []
            i = 0
            while True:
                val = start + i * step
                if val > end:
                    break
                values.append(val)
                i += 1
            return values
        else:
            # Float range inclusive with drift-safe rounding
            if step <= 0:
                raise ValueError("step must be positive")
            # Add small epsilon to avoid missing the last due to floating error
            num_steps = math.floor((end - start) / step + 1e-12)
            values = []
            for i in range(num_steps + 1):
                val = start + i * step
                # Round to 12 decimal places to avoid floating noise
                val = round(val, 12)
                if val <= end + 1e-12:
                    values.append(val)
            return values
    
    elif grid.mode == GridMode.MULTI:
        values = grid.multi_values
        if values is None:
            raise ValueError("multi_values must be set for multi mode")
        
        # Ensure uniqueness and deterministic order
        seen = set()
        unique = []
        for v in values:
            if v not in seen:
                seen.add(v)
                unique.append(v)
        return unique
    
    else:
        raise ValueError(f"Unknown grid mode: {grid.mode}")


def count_for_param(grid: ParamGridSpec) -> int:
    """Return number of distinct values for this parameter."""
    return len(values_for_param(grid))


def validate_grid_for_param(
    grid: ParamGridSpec,
    param_type: str,
    min: int | float | None = None,
    max: int | float | None = None,
    choices: list[Any] | None = None,
) -> None:
    """Validate that grid is compatible with param spec.
    
    Args:
        grid: Parameter grid specification
        param_type: Parameter type ("int", "float", "bool", "enum")
        min: Minimum allowed value (optional)
        max: Maximum allowed value (optional)
        choices: List of allowed values for enum type (optional)
    
    Raises ValueError with descriptive message if invalid.
    """
    # Check duplicates for MULTI mode
    if grid.mode == GridMode.MULTI and grid.multi_values:
        if len(grid.multi_values) != len(set(grid.multi_values)):
            raise ValueError("multi_values contains duplicate values")
    
    # Check empty multi_values
    if grid.mode == GridMode.MULTI and grid.multi_values is not None and len(grid.multi_values) == 0:
        raise ValueError("multi_values must contain at least one value")
    
    # Range-specific validation
    if grid.mode == GridMode.RANGE:
        if grid.range_step is not None and grid.range_step <= 0:
            raise ValueError("range_step must be positive")
        if grid.range_start is not None and grid.range_end is not None and grid.range_start > grid.range_end:
            raise ValueError("start <= end")
    
    # Type-specific validation
    if param_type == "enum":
        if choices is None:
            raise ValueError("enum parameter must have choices defined")
        if grid.mode == GridMode.RANGE:
            raise ValueError("enum parameters cannot use range mode")
        if grid.mode == GridMode.SINGLE:
            if grid.single_value not in choices:
                raise ValueError(f"value '{grid.single_value}' not in choices {choices}")
        elif grid.mode == GridMode.MULTI:
            if grid.multi_values is None:
                raise ValueError("multi_values must be set for multi mode")
            for val in grid.multi_values:
                if val not in choices:
                    raise ValueError(f"value '{val}' not in choices {choices}")
    
    elif param_type == "bool":
        if grid.mode == GridMode.RANGE:
            raise ValueError("bool parameters cannot use range mode")
        if grid.mode == GridMode.SINGLE:
            if not isinstance(grid.single_value, bool):
                raise ValueError(f"bool parameter expects bool value, got {type(grid.single_value)}")
        elif grid.mode == GridMode.MULTI:
            if grid.multi_values is None:
                raise ValueError("multi_values must be set for multi mode")
            for val in grid.multi_values:
                if not isinstance(val, bool):
                    raise ValueError(f"bool parameter expects bool values, got {type(val)}")
    
    elif param_type == "int":
        # Ensure values are integers
        if grid.mode == GridMode.SINGLE:
            if not isinstance(grid.single_value, int):
                raise ValueError("int parameter expects integer value")
        elif grid.mode == GridMode.RANGE:
            if not (isinstance(grid.range_start, (int, float)) and
                    isinstance(grid.range_end, (int, float)) and
                    isinstance(grid.range_step, (int, float))):
                raise ValueError("int range requires numeric start/end/step")
            # Values will be integer due to integer step
        elif grid.mode == GridMode.MULTI:
            if grid.multi_values is None:
                raise ValueError("multi_values must be set for multi mode")
            for val in grid.multi_values:
                if not isinstance(val, int):
                    raise ValueError("int parameter expects integer values")
    
    elif param_type == "float":
        # Ensure values are numeric
        if grid.mode == GridMode.SINGLE:
            if not isinstance(grid.single_value, (int, float)):
                raise ValueError("float parameter expects numeric value")
        elif grid.mode == GridMode.RANGE:
            if not (isinstance(grid.range_start, (int, float)) and
                    isinstance(grid.range_end, (int, float)) and
                    isinstance(grid.range_step, (int, float))):
                raise ValueError("float range requires numeric start/end/step")
        elif grid.mode == GridMode.MULTI:
            if grid.multi_values is None:
                raise ValueError("multi_values must be set for multi mode")
            for val in grid.multi_values:
                if not isinstance(val, (int, float)):
                    raise ValueError("float parameter expects numeric values")
    
    # Check bounds
    if min is not None:
        if grid.mode == GridMode.SINGLE:
            val = grid.single_value
            if val is not None and val < min:
                raise ValueError(f"value {val} out of range (min {min})")
        elif grid.mode == GridMode.RANGE:
            if grid.range_start is not None and grid.range_start < min:
                raise ValueError(f"range_start {grid.range_start} out of range (min {min})")
        elif grid.mode == GridMode.MULTI:
            if grid.multi_values is None:
                raise ValueError("multi_values must be set for multi mode")
            for val in grid.multi_values:
                if val < min:
                    raise ValueError(f"value {val} out of range (min {min})")
    
    if max is not None:
        if grid.mode == GridMode.SINGLE:
            val = grid.single_value
            if val is not None and val > max:
                raise ValueError(f"value {val} out of range (max {max})")
        elif grid.mode == GridMode.RANGE:
            if grid.range_end is not None and grid.range_end > max:
                raise ValueError(f"range_end {grid.range_end} out of range (max {max})")
        elif grid.mode == GridMode.MULTI:
            if grid.multi_values is None:
                raise ValueError("multi_values must be set for multi mode")
            for val in grid.multi_values:
                if val > max:
                    raise ValueError(f"value {val} out of range (max {max})")
    
    # Compute values to ensure no errors
    values_for_param(grid)