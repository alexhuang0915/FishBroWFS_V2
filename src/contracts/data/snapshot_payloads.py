"""
Snapshot creation payloads (Phase 16.5).
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class SnapshotCreatePayload(BaseModel):
    """Payload for creating a data snapshot from raw bars."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    raw_bars: list[dict[str, Any]] = Field(
        ...,
        description="List of raw bar dictionaries with timestamp, open, high, low, close, volume",
        min_length=1,
    )
    symbol: str = Field(
        ...,
        description="Trading symbol (e.g., 'MNQ')",
        min_length=1,
    )
    timeframe: str = Field(
        ...,
        description="Bar timeframe (e.g., '1m', '5m', '1h')",
        min_length=1,
    )
    transform_version: str = Field(
        default="v1",
        description="Version of the normalization algorithm (e.g., 'v1')",
        min_length=1,
    )