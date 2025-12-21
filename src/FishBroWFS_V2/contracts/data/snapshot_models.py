"""
Snapshot metadata models (Phase 16.5).
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class SnapshotStats(BaseModel):
    """Basic statistics of a snapshot."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    count: int = Field(..., description="Number of bars", ge=0)
    min_timestamp: str = Field(..., description="Earliest bar timestamp (ISO 8601 UTC)")
    max_timestamp: str = Field(..., description="Latest bar timestamp (ISO 8601 UTC)")
    min_price: float = Field(..., description="Lowest low price across bars", ge=0.0)
    max_price: float = Field(..., description="Highest high price across bars", ge=0.0)
    total_volume: float = Field(..., description="Sum of volume across bars", ge=0.0)


class SnapshotMetadata(BaseModel):
    """Immutable metadata of a data snapshot."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    snapshot_id: str = Field(
        ...,
        description="Deterministic snapshot identifier",
        min_length=1,
    )
    symbol: str = Field(
        ...,
        description="Trading symbol",
        min_length=1,
    )
    timeframe: str = Field(
        ...,
        description="Bar timeframe",
        min_length=1,
    )
    transform_version: str = Field(
        ...,
        description="Version of the normalization algorithm (e.g., 'v1')",
        min_length=1,
    )
    created_at: str = Field(
        ...,
        description="ISO 8601 UTC timestamp when snapshot was created (may include fractional seconds)",
        pattern=r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$",
    )
    raw_sha256: str = Field(
        ...,
        description="SHA256 of the raw bars JSON",
        pattern=r"^[a-f0-9]{64}$",
    )
    normalized_sha256: str = Field(
        ...,
        description="SHA256 of the normalized bars JSON",
        pattern=r"^[a-f0-9]{64}$",
    )
    manifest_sha256: str = Field(
        ...,
        description="SHA256 of the manifest JSON (excluding this field)",
        pattern=r"^[a-f0-9]{64}$",
    )
    stats: SnapshotStats = Field(
        ...,
        description="Basic statistics of the snapshot",
    )