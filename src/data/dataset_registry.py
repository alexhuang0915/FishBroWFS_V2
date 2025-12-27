"""Dataset Registry Schema.

Phase 12: Dataset Registry for Research Job Wizard.
Describes "what datasets are available" without containing any price data.
Schema can only "add fields" in the future, cannot change semantics.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


class DatasetRecord(BaseModel):
    """Metadata for a single derived dataset."""
    
    model_config = ConfigDict(frozen=True)
    
    id: str = Field(
        ...,
        description="Unique identifier, e.g. 'CME.MNQ.60m.2020-2024'",
        examples=["CME.MNQ.60m.2020-2024", "TWF.MXF.15m.2018-2023"]
    )
    
    symbol: str = Field(
        ...,
        description="Symbol identifier, e.g. 'CME.MNQ'",
        examples=["CME.MNQ", "TWF.MXF"]
    )
    
    exchange: str = Field(
        ...,
        description="Exchange identifier, e.g. 'CME'",
        examples=["CME", "TWF"]
    )
    
    timeframe: str = Field(
        ...,
        description="Timeframe string, e.g. '60m'",
        examples=["60m", "15m", "5m", "1D"]
    )
    
    path: str = Field(
        ...,
        description="Relative path to derived file from data/derived/",
        examples=["CME.MNQ/60m/2020-2024.parquet"]
    )
    
    start_date: date = Field(
        ...,
        description="First date with data (inclusive)"
    )
    
    end_date: date = Field(
        ...,
        description="Last date with data (inclusive)"
    )
    
    fingerprint_sha1: Optional[str] = Field(
        default=None,
        description="SHA1 hash of file content (binary), deterministic fingerprint (deprecated, use fingerprint_sha256_40)"
    )
    
    fingerprint_sha256_40: str = Field(
        ...,
        description="SHA256 hash of file content (binary), first 40 hex chars, deterministic fingerprint"
    )
    
    @model_validator(mode="before")
    @classmethod
    def ensure_fingerprint_sha256_40(cls, data: dict) -> dict:
        """Backward compatibility: if fingerprint_sha256_40 missing but fingerprint_sha1 present, copy it."""
        if isinstance(data, dict):
            if "fingerprint_sha256_40" not in data or not data["fingerprint_sha256_40"]:
                if "fingerprint_sha1" in data and data["fingerprint_sha1"]:
                    # Copy sha1 to sha256 field (note: this is semantically wrong but maintains compatibility)
                    data["fingerprint_sha256_40"] = data["fingerprint_sha1"]
        return data
    
    tz_provider: str = Field(
        default="IANA",
        description="Timezone provider identifier"
    )
    
    tz_version: str = Field(
        default="unknown",
        description="Timezone database version"
    )


class DatasetIndex(BaseModel):
    """Complete registry of all available datasets."""
    
    model_config = ConfigDict(frozen=True)
    
    generated_at: datetime = Field(
        ...,
        description="Timestamp when this index was generated"
    )
    
    datasets: List[DatasetRecord] = Field(
        default_factory=list,
        description="List of all available dataset records"
    )
    
    def model_post_init(self, __context: object) -> None:
        """Post-initialization hook to sort datasets by id."""
        super().model_post_init(__context)
        # Sort datasets by id to ensure deterministic order
        if self.datasets:
            self.datasets.sort(key=lambda d: d.id)
