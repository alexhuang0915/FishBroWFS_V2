"""Derived JSON schema (machine‑computed)."""
from typing import List, Dict, Any
from pydantic import BaseModel, Field


class DerivedDocument(BaseModel):
    """Root derived.json schema."""
    estimated_combinations: int = Field(..., description="Estimated number of combinations")
    risk_class: str = Field(..., description="Risk class (LOW, MEDIUM, HIGH)")
    execution_plan: Dict[str, Any] = Field(default_factory=dict, description="Detailed execution plan")
    # Additional machine‑computed fields
    warnings: List[str] = Field(default_factory=list)
    assumptions: Dict[str, Any] = Field(default_factory=dict)
    
    class Config:
        extra = "forbid"
        frozen = True