"""
Data Reader (Layer 0).

Strict ingestor for FishBroData/raw.
Verifies checksums and produces DataSnapshot objects.
"""

from __future__ import annotations

import csv
import logging
from datetime import datetime
from pathlib import Path
from typing import Iterator, Optional

from contracts.data_models import Bar, DataSnapshot, TimeFrame

logger = logging.getLogger(__name__)


class DataReader:
    """Strict reader for raw market data."""

    def __init__(self, raw_root: Path):
        self.raw_root = raw_root
        if not self.raw_root.exists():
            raise FileNotFoundError(f"Raw root not found: {self.raw_root}")

    def read_dataset(
        self,
        symbol: str,
        timeframe: TimeFrame,
        verify_checksum: bool = True
    ) -> DataSnapshot:
        """
        Read and verify a raw dataset.
        
        This implementation assumes 'FishBroData/raw' structure:
        {root}/{timeframe}/{symbol}.csv (or similar convention).
        """
        file_path = self.raw_root / timeframe.value / f"{symbol}.csv"
        
        if not file_path.exists():
            raise FileNotFoundError(f"Data file not found: {file_path}")

        # Compute Checksum
        checksum = "skipped"
        if verify_checksum:
            checksum = DataSnapshot.compute_file_checksum(file_path)

        # Scan file to get metadata (rows, start, end)
        row_count = 0
        start_time: Optional[datetime] = None
        end_time: Optional[datetime] = None
        
        with open(file_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                row_count += 1
                try:
                    ts_str = row.get("Date") or row.get("datetime") or row.get("timestamp")
                    if not ts_str:
                         continue
                         
                    ts = datetime.fromisoformat(str(ts_str).replace("Z", "+00:00"))
                    
                    if start_time is None:
                        start_time = ts
                    end_time = ts
                except Exception:
                    pass

        if row_count == 0 or not start_time or not end_time:
            raise ValueError(f"File {file_path} is empty or invalid")

        import hashlib
        snapshot_id = hashlib.sha256(f"{symbol}:{timeframe}:{checksum}".encode()).hexdigest()

        return DataSnapshot(
            snapshot_id=snapshot_id,
            source_uri=f"file://{file_path.absolute()}",
            symbol=symbol,
            timeframe=timeframe,
            start_time=start_time,
            end_time=end_time,
            row_count=row_count,
            sha256_checksum=checksum
        )

    def stream_bars(self, snapshot: DataSnapshot) -> Iterator[Bar]:
        """
        Yield verified Bar objects from a snapshot.
        """
        path = Path(snapshot.source_uri.replace("file://", ""))
        
        with open(path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    ts_str = row.get("Date") or row.get("datetime")
                    
                    yield Bar(
                        timestamp=datetime.fromisoformat(str(ts_str).replace("Z", "+00:00")),
                        open=float(row["Open"]),
                        high=float(row["High"]),
                        low=float(row["Low"]),
                        close=float(row["Close"]),
                        volume=float(row["Volume"])
                    )
                except Exception as e:
                    logger.error(f"Bad row in {path}: {row} - {e}")
                    raise ValueError(f"Data corruption in {path}: {e}")
