"""Test: Raw means RAW - regression prevention.

RED TEAM #1: Lock down three things:
1. Row order unchanged (no sort)
2. Duplicate ts_str not deduplicated (no drop_duplicates)
3. Empty values not dropped (no dropna) - test with volume=0
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from FishBroWFS_V2.data.raw_ingest import ingest_raw_txt


def test_row_order_preserved(temp_dir: Path) -> None:
    """Test that row order matches TXT file exactly (no sort)."""
    # Create TXT with intentionally unsorted timestamps
    txt_path = temp_dir / "test_order.txt"
    txt_content = """Date,Time,Open,High,Low,Close,TotalVolume
2013/1/3,09:30:00,110.0,115.0,109.0,114.0,2000
2013/1/1,09:30:00,100.0,105.0,99.0,104.0,1000
2013/1/2,09:30:00,105.0,107.0,104.0,106.0,1500
"""
    txt_path.write_text(txt_content, encoding="utf-8")
    
    result = ingest_raw_txt(txt_path)
    
    # Assert order matches TXT (first row should be 2013/1/3)
    assert result.df.iloc[0]["ts_str"] == "2013/1/3 09:30:00"
    assert result.df.iloc[1]["ts_str"] == "2013/1/1 09:30:00"
    assert result.df.iloc[2]["ts_str"] == "2013/1/2 09:30:00"
    
    # Verify no sort occurred (should be in TXT order)
    assert len(result.df) == 3


def test_duplicate_ts_str_not_deduped(temp_dir: Path) -> None:
    """Test that duplicate ts_str rows are preserved (no drop_duplicates)."""
    # Create TXT with duplicate Date/Time but different Close values
    txt_path = temp_dir / "test_duplicate.txt"
    txt_content = """Date,Time,Open,High,Low,Close,TotalVolume
2013/1/1,09:30:00,100.0,105.0,99.0,104.0,1000
2013/1/1,09:30:00,100.0,105.0,99.0,105.0,1200
2013/1/2,09:30:00,105.0,107.0,104.0,106.0,1500
"""
    txt_path.write_text(txt_content, encoding="utf-8")
    
    result = ingest_raw_txt(txt_path)
    
    # Assert both duplicate rows are present
    assert len(result.df) == 3
    
    # Assert order matches TXT
    assert result.df.iloc[0]["ts_str"] == "2013/1/1 09:30:00"
    assert result.df.iloc[0]["close"] == 104.0
    
    assert result.df.iloc[1]["ts_str"] == "2013/1/1 09:30:00"
    assert result.df.iloc[1]["close"] == 105.0  # Different close value
    
    assert result.df.iloc[2]["ts_str"] == "2013/1/2 09:30:00"
    
    # Verify duplicates exist (ts_str column should have duplicates)
    ts_str_counts = result.df["ts_str"].value_counts()
    assert ts_str_counts["2013/1/1 09:30:00"] == 2


def test_volume_zero_preserved(temp_dir: Path) -> None:
    """Test that volume=0 rows are preserved (no dropna)."""
    # Create TXT with volume=0
    txt_path = temp_dir / "test_volume_zero.txt"
    txt_content = """Date,Time,Open,High,Low,Close,TotalVolume
2013/1/1,09:30:00,100.0,105.0,99.0,104.0,0
2013/1/1,10:00:00,104.0,106.0,103.0,105.0,1200
2013/1/2,09:30:00,105.0,107.0,104.0,106.0,0
"""
    txt_path.write_text(txt_content, encoding="utf-8")
    
    result = ingest_raw_txt(txt_path)
    
    # Assert all rows are present (including volume=0)
    assert len(result.df) == 3
    
    # Assert volume=0 rows are preserved
    assert result.df.iloc[0]["volume"] == 0
    assert result.df.iloc[1]["volume"] == 1200
    assert result.df.iloc[2]["volume"] == 0
    
    # Verify volume column type is int64
    assert result.df["volume"].dtype == "int64"


def test_no_sort_values_called(temp_dir: Path) -> None:
    """Regression test: Ensure sort_values is never called internally."""
    # This is a contract test - if sort is called, order would change
    txt_path = temp_dir / "test_no_sort.txt"
    txt_content = """Date,Time,Open,High,Low,Close,TotalVolume
2013/1/3,09:30:00,110.0,115.0,109.0,114.0,2000
2013/1/1,09:30:00,100.0,105.0,99.0,104.0,1000
2013/1/2,09:30:00,105.0,107.0,104.0,106.0,1500
"""
    txt_path.write_text(txt_content, encoding="utf-8")
    
    result = ingest_raw_txt(txt_path)
    
    # If sort was called, first row would be 2013/1/1 (earliest)
    # But we expect 2013/1/3 (first in TXT)
    first_ts = result.df.iloc[0]["ts_str"]
    assert first_ts.startswith("2013/1/3"), f"Row order changed - first row is {first_ts}, expected 2013/1/3"


def test_no_drop_duplicates_called(temp_dir: Path) -> None:
    """Regression test: Ensure drop_duplicates is never called internally."""
    txt_path = temp_dir / "test_no_dedup.txt"
    txt_content = """Date,Time,Open,High,Low,Close,TotalVolume
2013/1/1,09:30:00,100.0,105.0,99.0,104.0,1000
2013/1/1,09:30:00,100.0,105.0,99.0,105.0,1200
2013/1/1,09:30:00,100.0,105.0,99.0,106.0,1300
"""
    txt_path.write_text(txt_content, encoding="utf-8")
    
    result = ingest_raw_txt(txt_path)
    
    # If drop_duplicates was called, we'd have only 1 row
    # But we expect 3 rows (all duplicates preserved)
    assert len(result.df) == 3
    
    # All should have same ts_str
    assert all(result.df["ts_str"] == "2013/1/1 09:30:00")
    
    # But different close values
    assert result.df.iloc[0]["close"] == 104.0
    assert result.df.iloc[1]["close"] == 105.0
    assert result.df.iloc[2]["close"] == 106.0


def test_no_dropna_called(temp_dir: Path) -> None:
    """Regression test: Ensure dropna is never called internally (volume=0 preserved)."""
    txt_path = temp_dir / "test_no_dropna.txt"
    txt_content = """Date,Time,Open,High,Low,Close,TotalVolume
2013/1/1,09:30:00,100.0,105.0,99.0,104.0,0
2013/1/1,10:00:00,104.0,106.0,103.0,105.0,0
2013/1/2,09:30:00,105.0,107.0,104.0,106.0,0
"""
    txt_path.write_text(txt_content, encoding="utf-8")
    
    result = ingest_raw_txt(txt_path)
    
    # If dropna was called on volume, rows with volume=0 might be dropped
    # But we expect all 3 rows preserved
    assert len(result.df) == 3
    
    # All should have volume=0
    assert all(result.df["volume"] == 0)
