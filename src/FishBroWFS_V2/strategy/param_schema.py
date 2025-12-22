
"""Strategy Parameter Schema for GUI introspection.

Phase 12: Strategy parameter schema definition for automatic UI generation.
GUI must NOT hardcode any strategy parameters.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ParamSpec(BaseModel):
    """Specification for a single strategy parameter.
    
    Used by GUI to generate appropriate input widgets.
    """
    
    model_config = ConfigDict(frozen=True)
    
    name: str = Field(
        ...,
        description="Parameter name (must match strategy implementation)",
        examples=["window", "threshold", "enabled"]
    )
    
    type: Literal["int", "float", "enum", "bool"] = Field(
        ...,
        description="Parameter data type"
    )
    
    min: int | float | None = Field(
        default=None,
        description="Minimum value (for int/float types)"
    )
    
    max: int | float | None = Field(
        default=None,
        description="Maximum value (for int/float types)"
    )
    
    step: int | float | None = Field(
        default=None,
        description="Step size (for int/float sliders)"
    )
    
    choices: list[str] | None = Field(
        default=None,
        description="Allowed choices (for enum type)"
    )
    
    default: Any = Field(
        ...,
        description="Default value"
    )
    
    help: str = Field(
        ...,
        description="Human-readable description/help text"
    )


