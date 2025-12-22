
"""Monkeypatch trap test: Ensure forbidden pandas methods are never called during raw ingest.

This test uses monkeypatch to trap any calls to forbidden methods.
If any forbidden method is called, the test immediately fails with a clear error.

Binding: Raw means RAW (Phase 6.5) - no sort, no dedup, no dropna, no datetime parse.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from FishBroWFS_V2.data.raw_ingest import ingest_raw_txt


def test_raw_ingest_forbidden_methods_trap(monkeypatch: pytest.MonkeyPatch, sample_raw_txt: Path) -> None:
    """Trap test: Any forbidden pandas method call during ingest will immediately fail.
    
    This test uses monkeypatch to replace forbidden methods with functions that
    raise AssertionError. If ingest_raw_txt() calls any forbidden method, the
    test will fail immediately with a clear error message.
    
    Forbidden methods:
    - pd.DataFrame.sort_values() - violates row order preservation
    - pd.DataFrame.dropna() - violates empty value preservation
    - pd.DataFrame.drop_duplicates() - violates duplicate preservation
    - pd.to_datetime() - violates naive ts_str contract (Phase 6.5)
    
    ⚠️ This is a constitutional test, not a debug log.
    The error messages are legal requirements, not debugging hints.
    """
    # Arrange: Patch forbidden methods to raise AssertionError if called
    
    def _boom_sort_values(*args, **kwargs):
        """Trap function for sort_values() - violates Raw means RAW."""
        raise AssertionError(
            "FORBIDDEN: sort_values() violates Raw means RAW (Phase 6.5). "
            "Row order must be preserved exactly as in TXT file."
        )
    
    def _boom_dropna(*args, **kwargs):
        """Trap function for dropna() - violates Raw means RAW."""
        raise AssertionError(
            "FORBIDDEN: dropna() violates Raw means RAW (Phase 6.5). "
            "Empty values must be preserved (e.g., volume=0)."
        )
    
    def _boom_drop_duplicates(*args, **kwargs):
        """Trap function for drop_duplicates() - violates Raw means RAW."""
        raise AssertionError(
            "FORBIDDEN: drop_duplicates() violates Raw means RAW (Phase 6.5). "
            "Duplicate rows must be preserved exactly as in TXT file."
        )
    
    def _boom_to_datetime(*args, **kwargs):
        """Trap function for pd.to_datetime() - violates naive ts_str contract."""
        raise AssertionError(
            "FORBIDDEN: pd.to_datetime() violates Naive ts_str Contract (Phase 6.5). "
            "Timestamp must remain as string literal, no datetime parsing allowed."
        )
    
    # Apply monkeypatches (scope limited to this test function)
    # Note: pd.to_datetime() is only used in _normalize_24h() for date parsing.
    # Since sample_raw_txt doesn't contain 24:00:00, _normalize_24h won't be called,
    # so we can safely trap all pd.to_datetime calls
    monkeypatch.setattr(pd.DataFrame, "sort_values", _boom_sort_values)
    monkeypatch.setattr(pd.DataFrame, "dropna", _boom_dropna)
    monkeypatch.setattr(pd.DataFrame, "drop_duplicates", _boom_drop_duplicates)
    monkeypatch.setattr(pd, "to_datetime", _boom_to_datetime)
    
    # Act: Call ingest_raw_txt() with patched pandas
    # If any forbidden method is called, AssertionError will be raised immediately
    result = ingest_raw_txt(sample_raw_txt)
    
    # Assert: Ingest completed successfully without triggering any traps
    # If we reach here, no forbidden methods were called
    assert result is not None
    assert len(result.df) > 0
    assert "ts_str" in result.df.columns
    assert result.df["ts_str"].dtype == "object"  # Must be string, not datetime


def test_raw_ingest_forbidden_methods_trap_with_24h_normalization(
    monkeypatch: pytest.MonkeyPatch, temp_dir: Path
) -> None:
    """Trap test with 24:00 normalization - ensure no forbidden DataFrame methods called.
    
    Tests the same traps but with a TXT file containing 24:00:00 time.
    Note: pd.to_datetime() is allowed in _normalize_24h() for date parsing only,
    so we only trap DataFrame methods, not pd.to_datetime().
    """
    # Create TXT with 24:00:00 (requires normalization)
    txt_path = temp_dir / "test_24h.txt"
    txt_content = """Date,Time,Open,High,Low,Close,TotalVolume
2013/1/1,09:30:00,100.0,105.0,99.0,104.0,1000
2013/1/1,24:00:00,104.0,106.0,103.0,105.0,1200
2013/1/2,09:30:00,105.0,107.0,104.0,106.0,1500
"""
    txt_path.write_text(txt_content, encoding="utf-8")
    
    # Arrange: Patch forbidden DataFrame methods only
    # Note: pd.to_datetime() is allowed for date parsing in _normalize_24h()
    def _boom_sort_values(*args, **kwargs):
        raise AssertionError(
            "FORBIDDEN: sort_values() violates Raw means RAW (Phase 6.5). "
            "Row order must be preserved exactly as in TXT file."
        )
    
    def _boom_dropna(*args, **kwargs):
        raise AssertionError(
            "FORBIDDEN: dropna() violates Raw means RAW (Phase 6.5). "
            "Empty values must be preserved (e.g., volume=0)."
        )
    
    def _boom_drop_duplicates(*args, **kwargs):
        raise AssertionError(
            "FORBIDDEN: drop_duplicates() violates Raw means RAW (Phase 6.5). "
            "Duplicate rows must be preserved exactly as in TXT file."
        )
    
    monkeypatch.setattr(pd.DataFrame, "sort_values", _boom_sort_values)
    monkeypatch.setattr(pd.DataFrame, "dropna", _boom_dropna)
    monkeypatch.setattr(pd.DataFrame, "drop_duplicates", _boom_drop_duplicates)
    
    # Act: Call ingest_raw_txt() - should succeed with 24h normalization
    result = ingest_raw_txt(txt_path)
    
    # Assert: Ingest completed successfully
    assert result is not None
    assert len(result.df) == 3
    assert result.policy.normalized_24h == True  # Should have normalized 24:00:00
    # Verify 24:00:00 was normalized to next day 00:00:00
    assert "2013/1/2 00:00:00" in result.df["ts_str"].values


