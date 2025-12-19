"""Data fingerprint - Truth fingerprint based on Raw TXT.

Binding #3: Mandatory Fingerprint in Governance + JobRecord.
Fingerprint must depend only on raw TXT content + ingest_policy.
Parquet is cache, not truth.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DataFingerprint:
    """Data fingerprint - immutable truth identifier.
    
    Attributes:
        sha1: SHA1 hash of raw TXT content + ingest_policy
        source_path: Path to source TXT file
        rows: Number of rows (metadata)
        first_ts_str: First timestamp string (metadata)
        last_ts_str: Last timestamp string (metadata)
        ingest_policy: Ingest policy dict (for hash computation)
    """
    sha1: str
    source_path: str
    rows: int
    first_ts_str: str
    last_ts_str: str
    ingest_policy: dict


def compute_txt_fingerprint(path: Path, *, ingest_policy: dict) -> DataFingerprint:
    """Compute fingerprint from raw TXT file + ingest_policy.
    
    Fingerprint is computed from:
    1. Raw TXT file content (bytes)
    2. Ingest policy (JSON with stable sort)
    
    This ensures the fingerprint represents the "truth" - raw data + normalization policy.
    Parquet cache can be deleted and rebuilt, fingerprint remains stable.
    
    Args:
        path: Path to raw TXT file
        ingest_policy: Ingest policy dict (will be JSON-serialized with stable sort)
        
    Returns:
        DataFingerprint with SHA1 hash and metadata
        
    Raises:
        FileNotFoundError: If path does not exist
    """
    if not path.exists():
        raise FileNotFoundError(f"TXT file not found: {path}")
    
    # Compute SHA1: policy first, then file content
    h = hashlib.sha1()
    
    # Add ingest_policy (stable JSON sort)
    policy_json = json.dumps(ingest_policy, sort_keys=True, ensure_ascii=False)
    h.update(policy_json.encode("utf-8"))
    
    # Add file content (chunked for large files)
    with path.open("rb") as f:
        while True:
            chunk = f.read(1024 * 1024)  # 1MB chunks
            if not chunk:
                break
            h.update(chunk)
    
    sha1 = h.hexdigest()
    
    # Read metadata (rows, first_ts_str, last_ts_str)
    # We need to parse the file to get these, but they're just metadata
    # The hash is the truth, metadata is for convenience
    import pandas as pd
    
    df = pd.read_csv(path, encoding="utf-8")
    rows = len(df)
    
    # Try to extract first/last timestamps
    # This is best-effort metadata, not part of hash
    first_ts_str = ""
    last_ts_str = ""
    
    if "Date" in df.columns and "Time" in df.columns:
        if rows > 0:
            first_date = str(df.iloc[0]["Date"])
            first_time = str(df.iloc[0]["Time"])
            last_date = str(df.iloc[-1]["Date"])
            last_time = str(df.iloc[-1]["Time"])
            
            # Apply same normalization as ingest (duplicate logic to avoid circular import)
            def _normalize_24h_local(date_s: str, time_s: str) -> tuple[str, bool]:
                """Local copy of _normalize_24h to avoid circular import."""
                t = time_s.strip()
                if t.startswith("24:"):
                    if t != "24:00:00":
                        raise ValueError(f"Invalid 24h time: {time_s}")
                    d = pd.to_datetime(date_s.strip(), format="%Y/%m/%d", errors="raise")
                    d2 = (d + pd.Timedelta(days=1)).to_pydatetime().date()
                    return f"{d2.year}/{d2.month}/{d2.day} 00:00:00", True
                return f"{date_s.strip()} {t}", False
            
            try:
                first_ts_str, _ = _normalize_24h_local(first_date, first_time)
            except Exception:
                first_ts_str = f"{first_date} {first_time}"
            
            try:
                last_ts_str, _ = _normalize_24h_local(last_date, last_time)
            except Exception:
                last_ts_str = f"{last_date} {last_time}"
    
    return DataFingerprint(
        sha1=sha1,
        source_path=str(path),
        rows=rows,
        first_ts_str=first_ts_str,
        last_ts_str=last_ts_str,
        ingest_policy=ingest_policy,
    )
