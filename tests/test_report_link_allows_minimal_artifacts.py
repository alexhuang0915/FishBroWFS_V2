"""Tests for report link allowing minimal artifacts.

Tests that report readiness only checks file existence,
and build_report_link always returns Viewer URL.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from FishBroWFS_V2.control.report_links import (
    build_report_link,
    get_outputs_root,
    is_report_ready,
)


def test_is_report_ready_with_minimal_artifacts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that is_report_ready returns True with only three files."""
    monkeypatch.setenv("FISHBRO_OUTPUTS_ROOT", str(tmp_path))
    
    run_id = "test_run_123"
    run_dir = tmp_path / run_id
    run_dir.mkdir(parents=True)
    
    # Create only the three required files
    (run_dir / "manifest.json").write_text(json.dumps({"run_id": run_id}))
    # Use winners_v2.json (preferred) or winners.json (fallback)
    (run_dir / "winners_v2.json").write_text(json.dumps({"summary": {}}))
    (run_dir / "governance.json").write_text(json.dumps({"scoring": {}}))
    
    # Should return True
    assert is_report_ready(run_id) is True


def test_is_report_ready_missing_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that is_report_ready returns False if any file is missing."""
    monkeypatch.setenv("FISHBRO_OUTPUTS_ROOT", str(tmp_path))
    
    run_id = "test_run_123"
    run_dir = tmp_path / run_id
    run_dir.mkdir(parents=True)
    
    # Create only two files (missing governance.json)
    (run_dir / "manifest.json").write_text(json.dumps({"run_id": run_id}))
    (run_dir / "winners.json").write_text(json.dumps({"summary": {}}))
    
    # Should return False
    assert is_report_ready(run_id) is False


def test_build_report_link_always_returns_url(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that build_report_link always returns Viewer URL."""
    monkeypatch.setenv("FISHBRO_OUTPUTS_ROOT", str(tmp_path))
    
    run_id = "test_run_123"
    
    # Should return URL even if artifacts don't exist
    report_link = build_report_link(run_id)
    
    assert report_link is not None
    assert report_link.startswith("/?")
    assert run_id in report_link
    assert "season" in report_link


def test_build_report_link_no_error_string(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that build_report_link never returns error string."""
    monkeypatch.setenv("FISHBRO_OUTPUTS_ROOT", str(tmp_path))
    
    run_id = "test_run_123"
    
    # Should never return error string
    report_link = build_report_link(run_id)
    
    assert report_link is not None
    assert isinstance(report_link, str)
    assert "error" not in report_link.lower()
    assert "not ready" not in report_link.lower()
    assert "missing" not in report_link.lower()


def test_is_report_ready_never_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that is_report_ready never raises exceptions."""
    monkeypatch.setenv("FISHBRO_OUTPUTS_ROOT", str(tmp_path))
    
    # Should not raise even with invalid run_id
    result = is_report_ready("nonexistent_run")
    assert isinstance(result, bool)
    
    # Should not raise even with None
    result = is_report_ready(None)  # type: ignore
    assert isinstance(result, bool)


def test_build_report_link_never_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that build_report_link never raises exceptions."""
    monkeypatch.setenv("FISHBRO_OUTPUTS_ROOT", str(tmp_path))
    
    # Should not raise even with invalid run_id
    report_link = build_report_link("nonexistent_run")
    assert report_link is not None
    assert isinstance(report_link, str)
    
    # Should not raise even with empty string
    report_link = build_report_link("")
    assert report_link is not None
    assert isinstance(report_link, str)


def test_minimal_artifacts_content_not_checked(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that is_report_ready does not check content validity."""
    monkeypatch.setenv("FISHBRO_OUTPUTS_ROOT", str(tmp_path))
    
    run_id = "test_run_123"
    run_dir = tmp_path / run_id
    run_dir.mkdir(parents=True)
    
    # Create files with invalid JSON content
    (run_dir / "manifest.json").write_text("invalid json")
    (run_dir / "winners_v2.json").write_text("not json")
    (run_dir / "governance.json").write_text("{}")
    
    # Should still return True (only checks existence)
    assert is_report_ready(run_id) is True


def test_is_report_ready_accepts_winners_json_fallback(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that is_report_ready accepts winners.json as fallback."""
    monkeypatch.setenv("FISHBRO_OUTPUTS_ROOT", str(tmp_path))
    
    run_id = "test_run_123"
    run_dir = tmp_path / run_id
    run_dir.mkdir(parents=True)
    
    # Create files with winners.json (not winners_v2.json)
    (run_dir / "manifest.json").write_text(json.dumps({"run_id": run_id}))
    (run_dir / "winners.json").write_text(json.dumps({"summary": {}}))
    (run_dir / "governance.json").write_text(json.dumps({"scoring": {}}))
    
    # Should still return True (only checks existence)
    assert is_report_ready(run_id) is True


def test_ui_does_not_block_with_minimal_artifacts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that UI flow does not block with minimal artifacts."""
    monkeypatch.setenv("FISHBRO_OUTPUTS_ROOT", str(tmp_path))
    
    run_id = "test_run_123"
    run_dir = tmp_path / run_id
    run_dir.mkdir(parents=True)
    
    # Create minimal artifacts
    (run_dir / "manifest.json").write_text(json.dumps({"run_id": run_id}))
    (run_dir / "winners_v2.json").write_text(json.dumps({"summary": {}}))
    (run_dir / "governance.json").write_text(json.dumps({"scoring": {}}))
    
    # build_report_link should work
    report_link = build_report_link(run_id)
    assert report_link is not None
    assert "error" not in report_link.lower()
    
    # is_report_ready should return True
    assert is_report_ready(run_id) is True
