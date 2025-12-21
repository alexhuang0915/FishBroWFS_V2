"""Tests for Dataset Registry (Phase 12)."""

from __future__ import annotations

import tempfile
from datetime import date
from pathlib import Path

import pytest

from FishBroWFS_V2.data.dataset_registry import DatasetIndex, DatasetRecord
from scripts.build_dataset_registry import build_registry, parse_filename_to_dates


def test_dataset_record_schema() -> None:
    """Test DatasetRecord schema validation."""
    record = DatasetRecord(
        id="CME.MNQ.60m.2020-2024",
        symbol="CME.MNQ",
        exchange="CME",
        timeframe="60m",
        path="CME.MNQ/60m/2020-2024.parquet",
        start_date=date(2020, 1, 1),
        end_date=date(2024, 12, 31),
        fingerprint_sha1="a" * 40,  # SHA1 hex length
        tz_provider="IANA",
        tz_version="2024a"
    )
    
    assert record.id == "CME.MNQ.60m.2020-2024"
    assert record.symbol == "CME.MNQ"
    assert record.exchange == "CME"
    assert record.timeframe == "60m"
    assert record.start_date <= record.end_date
    assert len(record.fingerprint_sha1) == 40


def test_dataset_index_schema() -> None:
    """Test DatasetIndex schema validation."""
    from datetime import datetime
    
    record = DatasetRecord(
        id="TEST.SYM.15m.2020-2021",
        symbol="TEST.SYM",
        exchange="TEST",
        timeframe="15m",
        path="TEST.SYM/15m/2020-2021.parquet",
        start_date=date(2020, 1, 1),
        end_date=date(2021, 12, 31),
        fingerprint_sha1="b" * 40
    )
    
    index = DatasetIndex(
        generated_at=datetime.now(),
        datasets=[record]
    )
    
    assert len(index.datasets) == 1
    assert index.datasets[0].id == "TEST.SYM.15m.2020-2021"


def test_parse_filename_to_dates() -> None:
    """Test date range parsing from filenames."""
    # Test YYYY-YYYY pattern
    result = parse_filename_to_dates("2020-2024.parquet")
    assert result is not None
    start, end = result
    assert start == date(2020, 1, 1)
    assert end == date(2024, 12, 31)
    
    # Test YYYYMMDD-YYYYMMDD pattern
    result = parse_filename_to_dates("20200101-20241231.parquet")
    assert result is not None
    start, end = result
    assert start == date(2020, 1, 1)
    assert end == date(2024, 12, 31)
    
    # Test invalid patterns
    assert parse_filename_to_dates("invalid.parquet") is None
    assert parse_filename_to_dates("2020-2024-extra.parquet") is None
    assert parse_filename_to_dates("20200101-20241231-extra.parquet") is None


def test_build_registry_with_fake_data() -> None:
    """Test registry building with fake fixture data."""
    with tempfile.TemporaryDirectory() as tmpdir:
        derived_root = Path(tmpdir) / "derived"
        
        # Create fake directory structure
        # data/derived/CME.MNQ/60m/2020-2024.parquet
        dataset_dir = derived_root / "CME.MNQ" / "60m"
        dataset_dir.mkdir(parents=True)
        
        # Create a dummy parquet file with some content
        parquet_file = dataset_dir / "2020-2024.parquet"
        parquet_file.write_bytes(b"fake parquet content for testing")
        
        # Build registry
        index = build_registry(derived_root)
        
        # Verify results
        assert len(index.datasets) == 1
        
        record = index.datasets[0]
        assert record.id == "CME.MNQ.60m.2020-2024"
        assert record.symbol == "CME.MNQ"
        assert record.timeframe == "60m"
        assert record.path == "CME.MNQ/60m/2020-2024.parquet"
        assert record.start_date == date(2020, 1, 1)
        assert record.end_date == date(2024, 12, 31)
        assert record.fingerprint_sha1 != ""  # Should have computed fingerprint
        assert len(record.fingerprint_sha1) == 40  # SHA1 hex length


def test_build_registry_multiple_datasets() -> None:
    """Test registry building with multiple fake datasets."""
    with tempfile.TemporaryDirectory() as tmpdir:
        derived_root = Path(tmpdir) / "derived"
        
        # Create multiple fake datasets
        datasets = [
            ("CME.MNQ", "60m", "2020-2024"),
            ("TWF.MXF", "15m", "2018-2023"),
            ("CME.ES", "5m", "20210101-20231231"),
        ]
        
        for symbol, timeframe, date_range in datasets:
            dataset_dir = derived_root / symbol / timeframe
            dataset_dir.mkdir(parents=True)
            
            parquet_file = dataset_dir / f"{date_range}.parquet"
            # Different content for different fingerprints
            parquet_file.write_bytes(f"content for {symbol}.{timeframe}".encode())
        
        # Build registry
        index = build_registry(derived_root)
        
        # Verify we have 3 datasets
        assert len(index.datasets) == 3
        
        # Verify all have fingerprints
        for record in index.datasets:
            assert record.fingerprint_sha1 != ""
            assert len(record.fingerprint_sha1) == 40
            assert record.start_date <= record.end_date
        
        # Verify IDs are constructed correctly
        ids = {record.id for record in index.datasets}
        expected_ids = {
            "CME.MNQ.60m.2020-2024",
            "TWF.MXF.15m.2018-2023",
            "CME.ES.5m.2021-2023",  # Note: parsed from YYYYMMDD-YYYYMMDD
        }
        assert ids == expected_ids


def test_build_registry_skips_invalid_files() -> None:
    """Test that invalid files are skipped during registry building."""
    with tempfile.TemporaryDirectory() as tmpdir:
        derived_root = Path(tmpdir) / "derived"
        
        # Create valid dataset
        valid_dir = derived_root / "CME.MNQ" / "60m"
        valid_dir.mkdir(parents=True)
        valid_file = valid_dir / "2020-2024.parquet"
        valid_file.write_bytes(b"valid")
        
        # Create invalid file (wrong extension)
        invalid_ext = valid_dir / "2020-2024.txt"
        invalid_ext.write_bytes(b"text file")
        
        # Create invalid file (cannot parse date)
        invalid_date = valid_dir / "invalid.parquet"
        invalid_date.write_bytes(b"invalid date")
        
        # Build registry - should only register the valid one
        index = build_registry(derived_root)
        
        assert len(index.datasets) == 1
        assert index.datasets[0].id == "CME.MNQ.60m.2020-2024"


def test_fingerprint_deterministic() -> None:
    """Test that fingerprint is computed from content, not metadata."""
    with tempfile.TemporaryDirectory() as tmpdir:
        derived_root = Path(tmpdir) / "derived"
        
        # Create dataset
        dataset_dir = derived_root / "TEST" / "1m"
        dataset_dir.mkdir(parents=True)
        
        parquet_file = dataset_dir / "2020-2021.parquet"
        content = b"identical content for fingerprint test"
        parquet_file.write_bytes(content)
        
        # Get first fingerprint
        index1 = build_registry(derived_root)
        fingerprint1 = index1.datasets[0].fingerprint_sha1
        
        # Touch file (change mtime) without changing content
        import time
        time.sleep(0.1)  # Ensure different mtime
        parquet_file.touch()
        
        # Get second fingerprint - should be identical
        index2 = build_registry(derived_root)
        fingerprint2 = index2.datasets[0].fingerprint_sha1
        
        assert fingerprint1 == fingerprint2, "Fingerprint should be content-based, not mtime-based"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
