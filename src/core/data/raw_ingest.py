
from __future__ import annotations
from typing import Dict, List, Any
from pathlib import Path
import pandas as pd
from pydantic import BaseModel
import logging

logger = logging.getLogger(__name__)

class RawIngestResult(BaseModel):
    """
    Result of ingesting a raw TXT file.
    """
    filename: str
    row_count: int
    columns: List[str]
    content_hash: str
    preview_rows: List[Dict[str, Any]]
    # We might not want to store the full dataframe in Pydantic, 
    # but for local passing it helps.
    # Actually, shared_build passes this to normalize_raw_bars.
    # Let's keep it simple: just metadata, and maybe a path or a way to get df.
    # Legacy likely had df inside or separate.
    # Let's check shared_build usage.
    # It passes raw_ingest_result to normalize_raw_bars(raw_ingest_result).
    # so we'll store the dataframe in a private attribute or strict check.
    
    class Config:
        arbitrary_types_allowed = True
        
    # Hack: Allow attaching df outside schema (or use PrivateAttr)
    _df: pd.DataFrame = None 
    
    def get_df(self) -> pd.DataFrame:
        if self._df is None:
            raise ValueError("Dataframe not attached")
        return self._df


def ingest_raw_txt(file_path: Path) -> RawIngestResult:
    """
    Ingest a raw K-Bar TXT file (TS, O, H, L, C, V).
    """
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")
        
    # Calculate hash (SHA256)
    import hashlib
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            sha256.update(chunk)
    file_hash = sha256.hexdigest()
    
    # Read CSV
    # Assuming standard format: Date, Time, Open, High, Low, Close, TotalVolume
    # Or similar. We will try to parse standard formats.
    
    try:
        df = pd.read_csv(file_path)
        # Normalize columns
        df.columns = [c.strip().lower() for c in df.columns]
        
        # Expectation: date, time, open, high, low, close, volume
        # Combine Date+Time -> ts
        if "date" in df.columns and "time" in df.columns:
            # Check format
            # Example: 2020/01/02, 17:00:00
            # or 2020-01-02
            df["ts"] = pd.to_datetime(df["date"].astype(str) + " " + df["time"].astype(str))
            # Drop date/time
            # df = df.drop(columns=["date", "time"])
            
        elif "datetime" in df.columns:
            df["ts"] = pd.to_datetime(df["datetime"])
            
        elif "ts" in df.columns:
             df["ts"] = pd.to_datetime(df["ts"])

        # Ensure numeric
        for col in ["open", "high", "low", "close", "volume"]:
            # Volume might be "totalvolume"
            if col not in df.columns:
                 # Try mappings
                 mappings = {"volume": ["vol", "totalvolume"], "open": ["op"], "high": ["hi"], "low": ["lo"], "close": ["cl"]}
                 for alias in mappings.get(col, []):
                     if alias in df.columns:
                         df = df.rename(columns={alias: col})
                         break
            
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        
        rows = len(df)
        cols = list(df.columns)
        preview = df.head(5).to_dict(orient="records")
        for p in preview:
             if "ts" in p: p["ts"] = str(p["ts"]) # serialize for preview
        
        result = RawIngestResult(
            filename=file_path.name,
            row_count=rows,
            columns=cols,
            content_hash=file_hash,
            preview_rows=preview
        )
        result._df = df
        return result
        
    except Exception as e:
        logger.error(f"Failed to ingest raw txt: {e}")
        raise
