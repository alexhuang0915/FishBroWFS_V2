"""
Export season payload contract for GUI.

Contract:
- Season must be frozen
- Export name immutable once created
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class ExportSeasonPayload(BaseModel):
    """Payload for exporting a season from GUI."""
    season: str
    export_name: str = Field(..., min_length=1, max_length=100, pattern=r"^[a-zA-Z0-9_-]+$")

    @classmethod
    def example(cls) -> "ExportSeasonPayload":
        return cls(
            season="2026Q1",
            export_name="export_v1",
        )