
"""
Freeze season payload contract for GUI.

Contract:
- Freeze season metadata cannot be changed after freeze
- Duplicate freeze → 409 Conflict
"""

from __future__ import annotations

from typing import Optional
from pydantic import BaseModel, Field


class FreezeSeasonPayload(BaseModel):
    """Payload for freezing a season from GUI."""
    season: str
    note: Optional[str] = Field(default=None, max_length=1000)
    tags: list[str] = Field(default_factory=list)

    @classmethod
    def example(cls) -> "FreezeSeasonPayload":
        return cls(
            season="2026Q1",
            note="Initial research season",
            tags=["research", "baseline"],
        )


