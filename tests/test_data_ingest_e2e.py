"""End-to-end test: Ingest → Cache → Rebuild.

Tests the complete data ingest pipeline:
1. Ingest raw TXT → DataFrame
2. Compute fingerprint
3. Write parquet cache + meta.json
4. Clean cache
5. Rebuild cache
6. Verify fingerprint stability
"""

from __future__ import annotations

from pathlib import Path

import pytest

from FishBroWFS_V2.data.cache import cache_paths, read_parquet_cache, write_parquet_cache
from FishBroWFS_V2.data.fingerprint import compute_txt_fingerprint
from FishBroWFS_V2.data.raw_ingest import ingest_raw_txt

# Note: sample_raw_txt fixture is defined in conftest.py for all tests


def test_ingest_cache_e2e(tmp_path: Path, sample_raw_txt: Path) -> None:
    """End-to-end test: Ingest → Compute fingerprint → Write cache.
    
    Tests:
    1. ingest_raw_txt() produces DataFrame with correct columns
    2. compute_txt_fingerprint() produces SHA1 hash
    3. write_parquet_cache() creates parquet and meta.json files
    4. meta.json contains data_fingerprint_sha1
    """
    # Step 1: Ingest raw TXT
    result = ingest_raw_txt(sample_raw_txt)
    
    # Verify DataFrame structure
    assert len(result.df) == 3
    assert list(result.df.columns) == ["ts_str", "open", "high", "low", "close", "volume"]
    assert result.df["ts_str"].dtype == "object"  # str
    assert result.df["open"].dtype == "float64"
    assert result.df["volume"].dtype == "int64"
    
    # Step 2: Compute fingerprint
    ingest_policy = {
        "normalized_24h": result.policy.normalized_24h,
        "column_map": result.policy.column_map,
    }
    fingerprint = compute_txt_fingerprint(sample_raw_txt, ingest_policy=ingest_policy)
    
    # Verify fingerprint
    assert len(fingerprint.sha1) == 40  # SHA1 hex length
    assert fingerprint.source_path == str(sample_raw_txt)
    assert fingerprint.rows == 3
    
    # Step 3: Write cache
    cache_root = tmp_path / "cache"
    symbol = "TEST_SYMBOL"
    paths = cache_paths(cache_root, symbol)
    
    meta = {
        "data_fingerprint_sha1": fingerprint.sha1,
        "source_path": str(sample_raw_txt),
        "ingest_policy": ingest_policy,
        "rows": result.rows,
        "first_ts_str": result.df.iloc[0]["ts_str"],
        "last_ts_str": result.df.iloc[-1]["ts_str"],
    }
    
    write_parquet_cache(paths, result.df, meta)
    
    # Step 4: Verify cache files exist
    assert paths.parquet_path.exists(), f"Parquet file not created: {paths.parquet_path}"
    assert paths.meta_path.exists(), f"Meta file not created: {paths.meta_path}"
    
    # Step 5: Verify meta.json contains fingerprint
    df_read, meta_read = read_parquet_cache(paths)
    
    assert "data_fingerprint_sha1" in meta_read
    assert meta_read["data_fingerprint_sha1"] == fingerprint.sha1
    assert meta_read["data_fingerprint_sha1"] == meta["data_fingerprint_sha1"]
    
    # Verify parquet data matches original
    assert len(df_read) == 3
    assert list(df_read.columns) == ["ts_str", "open", "high", "low", "close", "volume"]
    assert df_read.iloc[0]["ts_str"] == "2013/1/1 09:30:00"


def test_clean_rebuild_fingerprint_stable(tmp_path: Path, sample_raw_txt: Path) -> None:
    """Test: Clean cache → Rebuild → Fingerprint remains stable.
    
    Flow:
    1. Ingest → Write cache → Get sha1_before
    2. Clean cache (delete parquet + meta)
    3. Re-ingest → Write cache → Get sha1_after
    4. Assert sha1_before == sha1_after
    
    ⚠️ No mocks, no hardcoding - real file operations only.
    """
    # Step 1: Initial ingest and cache
    result1 = ingest_raw_txt(sample_raw_txt)
    ingest_policy = {
        "normalized_24h": result1.policy.normalized_24h,
        "column_map": result1.policy.column_map,
    }
    fingerprint1 = compute_txt_fingerprint(sample_raw_txt, ingest_policy=ingest_policy)
    
    cache_root = tmp_path / "cache_rebuild"
    symbol = "TEST_SYMBOL_REBUILD"
    paths = cache_paths(cache_root, symbol)
    
    meta1 = {
        "data_fingerprint_sha1": fingerprint1.sha1,
        "source_path": str(sample_raw_txt),
        "ingest_policy": ingest_policy,
        "rows": result1.rows,
        "first_ts_str": result1.df.iloc[0]["ts_str"],
        "last_ts_str": result1.df.iloc[-1]["ts_str"],
    }
    
    write_parquet_cache(paths, result1.df, meta1)
    
    # Verify cache exists
    assert paths.parquet_path.exists()
    assert paths.meta_path.exists()
    
    # Read meta to get sha1_before
    _, meta_read_before = read_parquet_cache(paths)
    sha1_before = meta_read_before["data_fingerprint_sha1"]
    assert sha1_before == fingerprint1.sha1
    
    # Step 2: Clean cache (delete parquet + meta)
    # Directly delete files (real cleanup, no mocks)
    paths.parquet_path.unlink()
    paths.meta_path.unlink()
    
    # Verify files are deleted
    assert not paths.parquet_path.exists()
    assert not paths.meta_path.exists()
    
    # Step 3: Re-ingest and rebuild cache
    result2 = ingest_raw_txt(sample_raw_txt)
    fingerprint2 = compute_txt_fingerprint(sample_raw_txt, ingest_policy=ingest_policy)
    
    meta2 = {
        "data_fingerprint_sha1": fingerprint2.sha1,
        "source_path": str(sample_raw_txt),
        "ingest_policy": ingest_policy,
        "rows": result2.rows,
        "first_ts_str": result2.df.iloc[0]["ts_str"],
        "last_ts_str": result2.df.iloc[-1]["ts_str"],
    }
    
    write_parquet_cache(paths, result2.df, meta2)
    
    # Step 4: Verify fingerprint stability
    _, meta_read_after = read_parquet_cache(paths)
    sha1_after = meta_read_after["data_fingerprint_sha1"]
    
    assert sha1_before == sha1_after, (
        f"Fingerprint changed after cache rebuild: "
        f"before={sha1_before}, after={sha1_after}"
    )
    assert sha1_after == fingerprint2.sha1
    assert fingerprint1.sha1 == fingerprint2.sha1, (
        f"Fingerprint computation changed: "
        f"first={fingerprint1.sha1}, second={fingerprint2.sha1}"
    )
