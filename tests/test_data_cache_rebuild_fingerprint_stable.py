"""Test: Delete parquet cache and rebuild - fingerprint must remain stable.

Binding #4: Parquet is Cache, Not Truth.
Fingerprint is computed from raw TXT + ingest_policy, not from parquet.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from FishBroWFS_V2.data.cache import CachePaths, cache_paths, read_parquet_cache, write_parquet_cache
from FishBroWFS_V2.data.fingerprint import compute_txt_fingerprint
from FishBroWFS_V2.data.raw_ingest import ingest_raw_txt


def test_cache_rebuild_fingerprint_stable(temp_dir: Path, sample_raw_txt: Path) -> None:
    """Test that deleting parquet and rebuilding produces same fingerprint.
    
    Flow:
    1. Use sample_raw_txt fixture
    2. Compute fingerprint sha1 A
    3. Ingest → write parquet cache
    4. Delete parquet + meta
    5. Ingest → write parquet cache (same policy)
    6. Compute fingerprint sha1 B
    7. Assert A == B
    8. Assert meta.data_fingerprint_sha1 == A
    """
    # Use sample_raw_txt fixture
    txt_path = sample_raw_txt
    
    # Ingest policy
    ingest_policy = {
        "normalized_24h": False,
        "column_map": None,
    }
    
    # Step 1: Compute fingerprint sha1 A
    fingerprint_a = compute_txt_fingerprint(txt_path, ingest_policy=ingest_policy)
    sha1_a = fingerprint_a.sha1
    
    # Step 2: Ingest → write parquet cache
    result = ingest_raw_txt(txt_path)
    cache_root = temp_dir / "cache"
    cache_paths_obj = cache_paths(cache_root, "TEST_SYMBOL")
    
    meta = {
        "data_fingerprint_sha1": sha1_a,
        "source_path": str(txt_path),
        "ingest_policy": ingest_policy,
        "rows": result.rows,
        "first_ts_str": result.df.iloc[0]["ts_str"],
        "last_ts_str": result.df.iloc[-1]["ts_str"],
    }
    
    write_parquet_cache(cache_paths_obj, result.df, meta)
    
    # Verify cache exists
    assert cache_paths_obj.parquet_path.exists()
    assert cache_paths_obj.meta_path.exists()
    
    # Step 3: Delete parquet + meta
    cache_paths_obj.parquet_path.unlink()
    cache_paths_obj.meta_path.unlink()
    
    assert not cache_paths_obj.parquet_path.exists()
    assert not cache_paths_obj.meta_path.exists()
    
    # Step 4: Ingest → write parquet cache (same policy)
    result2 = ingest_raw_txt(txt_path)
    write_parquet_cache(cache_paths_obj, result2.df, meta)
    
    # Step 5: Compute fingerprint sha1 B
    fingerprint_b = compute_txt_fingerprint(txt_path, ingest_policy=ingest_policy)
    sha1_b = fingerprint_b.sha1
    
    # Step 6: Assert A == B
    assert sha1_a == sha1_b, f"Fingerprint changed after cache rebuild: {sha1_a} != {sha1_b}"
    
    # Step 7: Assert meta.data_fingerprint_sha1 == A
    df_read, meta_read = read_parquet_cache(cache_paths_obj)
    assert meta_read["data_fingerprint_sha1"] == sha1_a
    assert meta_read["data_fingerprint_sha1"] == sha1_b


def test_cache_rebuild_with_24h_normalization(temp_dir: Path) -> None:
    """Test fingerprint stability with 24:00 normalization."""
    # Create temp raw TXT with 24:00:00 (specific test case, not using fixture)
    txt_path = temp_dir / "test_data_24h.txt"
    txt_content = """Date,Time,Open,High,Low,Close,TotalVolume
2013/1/1,09:30:00,100.0,105.0,99.0,104.0,1000
2013/1/1,24:00:00,104.0,106.0,103.0,105.0,1200
2013/1/2,09:30:00,105.0,107.0,104.0,106.0,1500
"""
    txt_path.write_text(txt_content, encoding="utf-8")
    
    # Ingest policy (will normalize 24:00:00)
    ingest_policy = {
        "normalized_24h": True,  # Will be set to True after ingest
        "column_map": None,
    }
    
    # Ingest first time
    result1 = ingest_raw_txt(txt_path)
    # Update policy to reflect normalization
    ingest_policy["normalized_24h"] = result1.policy.normalized_24h
    
    # Compute fingerprint
    fingerprint_a = compute_txt_fingerprint(txt_path, ingest_policy=ingest_policy)
    sha1_a = fingerprint_a.sha1
    
    # Write cache
    cache_root = temp_dir / "cache2"
    cache_paths_obj = cache_paths(cache_root, "TEST_SYMBOL_24H")
    
    meta = {
        "data_fingerprint_sha1": sha1_a,
        "source_path": str(txt_path),
        "ingest_policy": ingest_policy,
        "rows": result1.rows,
        "first_ts_str": result1.df.iloc[0]["ts_str"],
        "last_ts_str": result1.df.iloc[-1]["ts_str"],
    }
    
    write_parquet_cache(cache_paths_obj, result1.df, meta)
    
    # Delete cache
    cache_paths_obj.parquet_path.unlink()
    cache_paths_obj.meta_path.unlink()
    
    # Rebuild
    result2 = ingest_raw_txt(txt_path)
    write_parquet_cache(cache_paths_obj, result2.df, meta)
    
    # Compute fingerprint again
    fingerprint_b = compute_txt_fingerprint(txt_path, ingest_policy=ingest_policy)
    sha1_b = fingerprint_b.sha1
    
    # Assert stability
    assert sha1_a == sha1_b, f"Fingerprint changed: {sha1_a} != {sha1_b}"
    assert result1.policy.normalized_24h == True  # Should have normalized 24:00:00
    assert result2.policy.normalized_24h == True
