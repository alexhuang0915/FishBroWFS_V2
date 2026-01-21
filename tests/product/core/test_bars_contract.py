"""Bars Contract SSOT Tests.

Test the three gates (A/B/C) for bars contract validation.
"""

import tempfile
from pathlib import Path
import numpy as np
import pandas as pd
import pytest

from core.bars_contract import (
    validate_gate_a,
    validate_gate_b_npz,
    validate_gate_b_parquet,
    validate_gate_b,
    validate_gate_c,
    validate_bars,
    validate_bars_with_raise,
    BarsValidationResult,
    BarsManifestEntry,
    create_bars_manifest_entry,
    GateAError,
    GateBError,
    GateCError,
    REQUIRED_COLUMNS,
    TS_DTYPE,
)


def create_valid_npz_bars(file_path: Path, n_bars: int = 100) -> dict:
    """Create a valid NPZ bars file for testing."""
    # Create synthetic bars data
    # Create timestamps with 1-minute intervals
    start_ts = np.datetime64("2023-01-01T00:00:00")
    ts = np.array([start_ts + np.timedelta64(i, 'm') for i in range(n_bars)], dtype="datetime64[s]")
    
    base_price = 100.0
    o = base_price + np.random.randn(n_bars) * 0.1
    h = o + np.abs(np.random.randn(n_bars)) * 0.2
    l = o - np.abs(np.random.randn(n_bars)) * 0.2
    c = (h + l) / 2 + np.random.randn(n_bars) * 0.05
    v = np.random.uniform(1000, 10000, n_bars)
    
    # Ensure price sanity
    h = np.maximum(h, np.maximum(o, c) + 0.01)
    l = np.minimum(l, np.minimum(o, c) - 0.01)
    
    data = {
        "ts": ts,
        "open": o.astype(np.float64),
        "high": h.astype(np.float64),
        "low": l.astype(np.float64),
        "close": c.astype(np.float64),
        "volume": v.astype(np.float64),
    }
    
    # Save as NPZ
    np.savez(file_path, **data)
    return data


def create_valid_parquet_bars(file_path: Path, n_bars: int = 100) -> pd.DataFrame:
    """Create a valid Parquet bars file for testing."""
    # Create synthetic bars data
    ts = pd.date_range(
        "2023-01-01 00:00:00",
        periods=n_bars,
        freq="1min",
        tz="UTC"
    )
    
    base_price = 100.0
    o = base_price + np.random.randn(n_bars) * 0.1
    h = o + np.abs(np.random.randn(n_bars)) * 0.2
    l = o - np.abs(np.random.randn(n_bars)) * 0.2
    c = (h + l) / 2 + np.random.randn(n_bars) * 0.05
    v = np.random.uniform(1000, 10000, n_bars)
    
    # Ensure price sanity
    h = np.maximum(h, np.maximum(o, c) + 0.01)
    l = np.minimum(l, np.minimum(o, c) - 0.01)
    
    df = pd.DataFrame({
        "timestamp": ts,
        "open": o,
        "high": h,
        "low": l,
        "close": c,
        "volume": v,
    })
    
    df.to_parquet(file_path)
    return df


class TestGateA:
    """Test Gate A: Existence/Openability."""
    
    def test_gate_a_passes_for_valid_npz(self, tmp_path):
        """Gate A should pass for a valid NPZ file."""
        file_path = tmp_path / "test_bars.npz"
        create_valid_npz_bars(file_path)
        
        passed, error = validate_gate_a(file_path)
        assert passed is True
        assert error is None
    
    def test_gate_a_fails_for_nonexistent_file(self, tmp_path):
        """Gate A should fail for non-existent file."""
        file_path = tmp_path / "nonexistent.npz"
        
        passed, error = validate_gate_a(file_path)
        assert passed is False
        assert "not found" in error.lower() or "file not found" in error.lower()
    
    def test_gate_a_fails_for_empty_file(self, tmp_path):
        """Gate A should fail for empty file."""
        file_path = tmp_path / "empty.npz"
        file_path.write_bytes(b"")
        
        passed, error = validate_gate_a(file_path)
        assert passed is False
        assert "empty" in error.lower()
    
    def test_gate_a_passes_for_valid_parquet(self, tmp_path):
        """Gate A should pass for a valid Parquet file."""
        file_path = tmp_path / "test_bars.parquet"
        create_valid_parquet_bars(file_path)
        
        passed, error = validate_gate_a(file_path)
        assert passed is True
        assert error is None


class TestGateB:
    """Test Gate B: Schema Contract."""
    
    def test_gate_b_npz_passes_for_valid_bars(self, tmp_path):
        """Gate B NPZ should pass for valid bars."""
        file_path = tmp_path / "test_bars.npz"
        create_valid_npz_bars(file_path)
        
        passed, error, data = validate_gate_b_npz(file_path)
        assert passed is True
        assert error is None
        assert data is not None
        assert set(data.keys()) >= REQUIRED_COLUMNS
        assert len(data["ts"]) > 0
    
    def test_gate_b_npz_fails_for_missing_columns(self, tmp_path):
        """Gate B NPZ should fail for missing required columns."""
        file_path = tmp_path / "test_bars.npz"
        
        # Create NPZ with missing columns
        data = {
            "ts": np.array([np.datetime64("2023-01-01T00:00:00")]),
            "open": np.array([100.0]),
            "high": np.array([101.0]),
            "low": np.array([99.0]),
            # Missing "close" and "volume"
        }
        np.savez(file_path, **data)
        
        passed, error, data = validate_gate_b_npz(file_path)
        assert passed is False
        assert "missing required columns" in error.lower()
        assert "close" in error.lower() or "volume" in error.lower()
    
    def test_gate_b_npz_fails_for_non_datetime_ts(self, tmp_path):
        """Gate B NPZ should fail for non-datetime timestamp column."""
        file_path = tmp_path / "test_bars.npz"
        
        # Create NPZ with wrong ts dtype
        data = {
            "ts": np.array([1, 2, 3]),  # Not datetime64
            "open": np.array([100.0, 101.0, 102.0]),
            "high": np.array([101.0, 102.0, 103.0]),
            "low": np.array([99.0, 100.0, 101.0]),
            "close": np.array([100.5, 101.5, 102.5]),
            "volume": np.array([1000.0, 1100.0, 1200.0]),
        }
        np.savez(file_path, **data)
        
        passed, error, data = validate_gate_b_npz(file_path)
        assert passed is False
        assert "datetime64" in error.lower()
    
    def test_gate_b_npz_fails_for_length_mismatch(self, tmp_path):
        """Gate B NPZ should fail for column length mismatch."""
        file_path = tmp_path / "test_bars.npz"
        
        # Create NPZ with mismatched lengths
        data = {
            "ts": np.array([np.datetime64("2023-01-01T00:00:00")]),
            "open": np.array([100.0, 101.0]),  # Different length
            "high": np.array([101.0]),
            "low": np.array([99.0]),
            "close": np.array([100.5]),
            "volume": np.array([1000.0]),
        }
        np.savez(file_path, **data)
        
        passed, error, data = validate_gate_b_npz(file_path)
        assert passed is False
        assert "length mismatch" in error.lower()
    
    def test_gate_b_npz_fails_for_non_increasing_ts(self, tmp_path):
        """Gate B NPZ should fail for non-increasing timestamps."""
        file_path = tmp_path / "test_bars.npz"
        
        # Create NPZ with non-increasing timestamps
        data = {
            "ts": np.array([
                np.datetime64("2023-01-01T00:02:00"),
                np.datetime64("2023-01-01T00:01:00"),  # Earlier than previous
                np.datetime64("2023-01-01T00:03:00"),
            ]),
            "open": np.array([100.0, 101.0, 102.0]),
            "high": np.array([101.0, 102.0, 103.0]),
            "low": np.array([99.0, 100.0, 101.0]),
            "close": np.array([100.5, 101.5, 102.5]),
            "volume": np.array([1000.0, 1100.0, 1200.0]),
        }
        np.savez(file_path, **data)
        
        passed, error, data = validate_gate_b_npz(file_path)
        assert passed is False
        assert "increasing" in error.lower()
    
    def test_gate_b_npz_fails_for_price_sanity_violation(self, tmp_path):
        """Gate B NPZ should fail for price sanity violations."""
        file_path = tmp_path / "test_bars.npz"
        
        # Create NPZ with low > open
        data = {
            "ts": np.array([np.datetime64("2023-01-01T00:00:00")]),
            "open": np.array([100.0]),
            "high": np.array([101.0]),
            "low": np.array([101.0]),  # low == high, but should be <= open
            "close": np.array([100.5]),
            "volume": np.array([1000.0]),
        }
        np.savez(file_path, **data)
        
        passed, error, data = validate_gate_b_npz(file_path)
        assert passed is False
        assert "low > open" in error.lower() or "low > close" in error.lower()
    
    def test_gate_b_parquet_passes_for_valid_bars(self, tmp_path):
        """Gate B Parquet should pass for valid bars."""
        file_path = tmp_path / "test_bars.parquet"
        create_valid_parquet_bars(file_path)
        
        passed, error, df = validate_gate_b_parquet(file_path)
        assert passed is True
        assert error is None
        assert df is not None
        assert len(df) > 0
    
    def test_gate_b_auto_detects_format(self, tmp_path):
        """Gate B should auto-detect file format."""
        # Test NPZ
        npz_path = tmp_path / "test_bars.npz"
        create_valid_npz_bars(npz_path)
        
        passed, error, data = validate_gate_b(npz_path)
        assert passed is True
        assert error is None
        assert data is not None
        
        # Test Parquet
        parquet_path = tmp_path / "test_bars.parquet"
        create_valid_parquet_bars(parquet_path)
        
        passed, error, data = validate_gate_b(parquet_path)
        assert passed is True
        assert error is None
        assert data is not None


class TestGateC:
    """Test Gate C: Manifest SSOT Integrity."""
    
    def test_gate_c_passes_for_matching_hash(self, tmp_path):
        """Gate C should pass when hash matches."""
        file_path = tmp_path / "test_bars.npz"
        create_valid_npz_bars(file_path)
        
        # Create manifest entry with correct hash
        from core.bars_contract import compute_file_hash
        expected_hash = compute_file_hash(file_path)
        manifest_entry = BarsManifestEntry(
            file_path=str(file_path),
            file_hash=expected_hash,
            bars_count=100,
            season="2026Q1",
            dataset_id="TEST",
        )
        
        passed, error, computed_hash = validate_gate_c(file_path, manifest_entry)
        assert passed is True
        assert error is None
        assert computed_hash == expected_hash
    
    def test_gate_c_fails_for_mismatched_hash(self, tmp_path):
        """Gate C should fail when hash doesn't match."""
        file_path = tmp_path / "test_bars.npz"
        create_valid_npz_bars(file_path)
        
        # Create manifest entry with wrong hash
        manifest_entry = BarsManifestEntry(
            file_path=str(file_path),
            file_hash="wrong_hash_1234567890abcdef",
            bars_count=100,
            season="2026Q1",
            dataset_id="TEST",
        )
        
        passed, error, computed_hash = validate_gate_c(file_path, manifest_entry)
        assert passed is False
        assert "hash mismatch" in error.lower()
        assert computed_hash is not None
    
    def test_gate_c_passes_without_manifest(self, tmp_path):
        """Gate C should pass when no manifest entry provided."""
        file_path = tmp_path / "test_bars.npz"
        create_valid_npz_bars(file_path)
        
        passed, error, computed_hash = validate_gate_c(file_path)
        assert passed is True
        assert error is None
        assert computed_hash is not None


class TestComprehensiveValidation:
    """Test comprehensive validation with all three gates."""
    
    def test_validate_bars_passes_for_valid_file(self, tmp_path):
        """validate_bars should pass for valid bars file."""
        file_path = tmp_path / "test_bars.npz"
        create_valid_npz_bars(file_path)
        
        result = validate_bars(file_path)
        assert isinstance(result, BarsValidationResult)
        assert result.all_passed is True
        assert result.gate_a_passed is True
        assert result.gate_b_passed is True
        assert result.gate_c_passed is True
        assert result.bars_count == 100
        assert result.file_size_bytes > 0
        assert result.computed_hash is not None
    
    def test_validate_bars_with_raise_passes(self, tmp_path):
        """validate_bars_with_raise should return result for valid file."""
        file_path = tmp_path / "test_bars.npz"
        create_valid_npz_bars(file_path)
        
        result = validate_bars_with_raise(file_path)
        assert isinstance(result, BarsValidationResult)
        assert result.all_passed is True
    
    def test_validate_bars_with_raise_raises_gate_a_error(self, tmp_path):
        """validate_bars_with_raise should raise GateAError for missing file."""
        file_path = tmp_path / "nonexistent.npz"
        
        with pytest.raises(GateAError) as exc_info:
            validate_bars_with_raise(file_path)
        
        assert "Gate A failed" in str(exc_info.value)
    
    def test_validate_bars_with_raise_raises_gate_b_error(self, tmp_path):
        """validate_bars_with_raise should raise GateBError for invalid schema."""
        file_path = tmp_path / "test_bars.npz"
        
        # Create invalid NPZ (missing columns)
        data = {"ts": np.array([np.datetime64("2023-01-01T00:00:00")])}
        np.savez(file_path, **data)
        
        with pytest.raises(GateBError) as exc_info:
            validate_bars_with_raise(file_path)
        
        assert "Gate B failed" in str(exc_info.value)


class TestBarsManifestEntry:
    """Test BarsManifestEntry creation and validation."""
    
    def test_create_bars_manifest_entry(self, tmp_path):
        """create_bars_manifest_entry should create valid entry."""
        file_path = tmp_path / "test_bars.npz"
        create_valid_npz_bars(file_path)
        
        entry = create_bars_manifest_entry(
            file_path=file_path,
            season="2026Q1",
            dataset_id="TEST",
            timeframe_min=15,
        )
        
        assert isinstance(entry, BarsManifestEntry)
        assert entry.file_path == str(file_path)
        assert entry.file_hash is not None
        assert entry.bars_count == 100
        assert entry.season == "2026Q1"
        assert entry.dataset_id == "TEST"
        assert entry.timeframe_min == 15
        assert entry.generated_at_utc is not None
    
    def test_create_bars_manifest_entry_fails_for_invalid_bars(self, tmp_path):
        """create_bars_manifest_entry should fail for invalid bars."""
        file_path = tmp_path / "test_bars.npz"
        
        # Create invalid NPZ
        data = {"invalid": np.array([1, 2, 3])}
        np.savez(file_path, **data)
        
        with pytest.raises(ValueError) as exc_info:
            create_bars_manifest_entry(
                file_path=file_path,
                season="2026Q1",
                dataset_id="TEST",
            )
        
        assert "invalid bars" in str(exc_info.value)