"""Dataset Registry Schema.

Phase 12: Dataset Registry for Research Job Wizard.
Describes "what datasets are available" without containing any price data.
Schema can only "add fields" in the future, cannot change semantics.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import List

from pydantic import BaseModel, ConfigDict, Field


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
    
    fingerprint_sha1: str = Field(
        ...,
        description="SHA1 hash of file content (binary), deterministic fingerprint"
    )
    
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
