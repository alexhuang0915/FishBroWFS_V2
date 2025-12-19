"""Parquet cache - Cache, Not Truth.

Binding #4: Parquet is Cache, Not Truth.
Cache can be deleted and rebuilt. Fingerprint is the truth.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd


@dataclass(frozen=True)
class CachePaths:
    """Cache file paths for a symbol.
    
    Attributes:
        parquet_path: Path to parquet cache file
        meta_path: Path to meta.json file
    """
    parquet_path: Path
    meta_path: Path


def cache_paths(cache_root: Path, symbol: str) -> CachePaths:
    """Get cache paths for a symbol.
    
    Args:
        cache_root: Root directory for cache files
        symbol: Symbol identifier (e.g., "CME.MNQ")
        
    Returns:
        CachePaths with parquet_path and meta_path
    """
    cache_root.mkdir(parents=True, exist_ok=True)
    
    # Sanitize symbol for filename
    safe_symbol = symbol.replace("/", "_").replace("\\", "_").replace(":", "_")
    
    return CachePaths(
        parquet_path=cache_root / f"{safe_symbol}.parquet",
        meta_path=cache_root / f"{safe_symbol}.meta.json",
    )


def write_parquet_cache(paths: CachePaths, df: pd.DataFrame, meta: dict[str, Any]) -> None:
    """Write parquet cache + meta.json.
    
    Parquet stores raw df (with ts_str), no sort, no dedup.
    meta.json must contain:
    - data_fingerprint_sha1
    - source_path
    - ingest_policy
    - rows, first_ts_str, last_ts_str
    
    Args:
        paths: CachePaths for this symbol
        df: DataFrame to cache (must have columns: ts_str, open, high, low, close, volume)
        meta: Metadata dict (must include data_fingerprint_sha1, source_path, ingest_policy, etc.)
        
    Raises:
        ValueError: If required meta fields are missing
    """
    required_meta_fields = ["data_fingerprint_sha1", "source_path", "ingest_policy"]
    missing_fields = [field for field in required_meta_fields if field not in meta]
    if missing_fields:
        raise ValueError(f"Missing required meta fields: {missing_fields}")
    
    # Write parquet (preserve order, no sort)
    paths.parquet_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(paths.parquet_path, index=False, engine="pyarrow")
    
    # Write meta.json
    with paths.meta_path.open("w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, sort_keys=True, indent=2)
        f.write("\n")


def read_parquet_cache(paths: CachePaths) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Read parquet cache + meta.json.
    
    Args:
        paths: CachePaths for this symbol
        
    Returns:
        Tuple of (DataFrame, meta_dict)
        
    Raises:
        FileNotFoundError: If parquet or meta.json does not exist
        json.JSONDecodeError: If meta.json is invalid JSON
    """
    if not paths.parquet_path.exists():
        raise FileNotFoundError(f"Parquet cache not found: {paths.parquet_path}")
    if not paths.meta_path.exists():
        raise FileNotFoundError(f"Meta file not found: {paths.meta_path}")
    
    # Read parquet
    df = pd.read_parquet(paths.parquet_path, engine="pyarrow")
    
    # Read meta.json
    with paths.meta_path.open("r", encoding="utf-8") as f:
        meta = json.load(f)
    
    return df, meta
