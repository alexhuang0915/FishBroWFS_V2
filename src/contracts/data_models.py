"""
Data Contracts (Layer 0).

Defines the immutable structures for raw market data.
Strict typing is enforced.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path

from pydantic import BaseModel, Field, field_validator, model_validator


class TimeFrame(str, Enum):
    """Supported timeframes."""
    TICK = "tick"
    MINUTE_1 = "1m"
    MINUTE_5 = "5m"
    MINUTE_15 = "15m"
    MINUTE_30 = "30m"
    HOUR_1 = "1h"
    DAILY = "1d"


class Bar(BaseModel):
    """
    Standard OHLCV Bar.
    
    Invariants:
    - High >= Low
    - High >= Open
    - High >= Close
    - Low <= Open
    - Low <= Close
    - Volume >= 0
    """
    timestamp: datetime = Field(..., description="UTC timestamp of the bar open time")
    open: float
    high: float
    low: float
    close: float
    volume: float

    @field_validator("timestamp")
    @classmethod
    def validate_utc(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("Timestamp must be timezone-aware (UTC)")
        if v.tzinfo != timezone.utc:
            # Coerce to UTC if aware but not UTC
            return v.astimezone(timezone.utc)
        return v

    @model_validator(mode="after")
    def check_invariants(self) -> Bar:
        if not (self.high >= self.low):
            raise ValueError(f"High ({self.high}) < Low ({self.low})")
        if not (self.high >= self.open):
            raise ValueError(f"High ({self.high}) < Open ({self.open})")
        if not (self.high >= self.close):
            raise ValueError(f"High ({self.high}) < Close ({self.close})")
        if not (self.low <= self.open):
            raise ValueError(f"Low ({self.low}) > Open ({self.open})")
        if not (self.low <= self.close):
            raise ValueError(f"Low ({self.low}) > Close ({self.close})")
        if self.volume < 0:
            raise ValueError(f"Volume ({self.volume}) < 0")
        return self


class DataSnapshot(BaseModel):
    """
    Represents a verified snapshot of raw data.
    
    This is the handle we use to refer to data, not a bare filename.
    """
    snapshot_id: str = Field(..., description="Unique ID of this snapshot (usually hash of metadata)")
    source_uri: str = Field(..., description="URI of the source data (e.g., file:///path/to/raw.csv)")
    symbol: str
    timeframe: TimeFrame
    start_time: datetime
    end_time: datetime
    row_count: int
    sha256_checksum: str = Field(..., description="SHA256 of the raw file content")
    created_at_utc: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @staticmethod
    def compute_file_checksum(path: Path) -> str:
        """Compute SHA256 of a file."""
        sha256_hash = hashlib.sha256()
        with open(path, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()
