
"""
Compare request payload contract for GUI.

Contract:
- Top K must be positive and ≤ 100
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class CompareRequestPayload(BaseModel):
    """Payload for comparing season results from GUI."""
    season: str
    top_k: int = Field(default=20, gt=0, le=100)

    @classmethod
    def example(cls) -> "CompareRequestPayload":
        return cls(
            season="2026Q1",
            top_k=20,
        )


