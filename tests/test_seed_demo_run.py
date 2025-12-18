"""Tests for seed_demo_run.

Tests that seed_demo_run creates demo job and artifacts correctly.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from FishBroWFS_V2.control.seed_demo_run import main, get_db_path


def test_seed_demo_run_no_raise(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that seed_demo_run does not raise exceptions."""
    # Set outputs root to tmp_path
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("JOBS_DB_PATH", str(tmp_path / "jobs.db"))
    
    # Should not raise
    run_id = main()
    
    assert run_id.startswith("demo_")
    assert len(run_id) > 5


def test_outputs_directory_created(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that outputs/<season>/runs/<run_id>/ directory is created."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("JOBS_DB_PATH", str(tmp_path / "jobs.db"))
    
    run_id = main()
    
    # Standard path structure: outputs/<season>/runs/<run_id>/
    run_dir = tmp_path / "outputs" / "seasons" / "2026Q1" / "runs" / run_id
    assert run_dir.exists()
    assert run_dir.is_dir()


def test_artifacts_exist(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that all required artifacts are created."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("JOBS_DB_PATH", str(tmp_path / "jobs.db"))
    
    run_id = main()
    # Standard path structure: outputs/<season>/runs/<run_id>/
    run_dir = tmp_path / "outputs" / "seasons" / "2026Q1" / "runs" / run_id
    
    # Check manifest.json
    manifest_path = run_dir / "manifest.json"
    assert manifest_path.exists()
    with manifest_path.open("r", encoding="utf-8") as f:
        manifest = json.load(f)
    assert manifest["run_id"] == run_id
    assert "created_at" in manifest
    
    # Check winners_v2.json
    winners_path = run_dir / "winners_v2.json"
    assert winners_path.exists()
    
    # Check governance.json
    governance_path = run_dir / "governance.json"
    assert governance_path.exists()
    
    # Check kpi.json (KPI唯一來源)
    kpi_path = run_dir / "kpi.json"
    assert kpi_path.exists()
    with kpi_path.open("r", encoding="utf-8") as f:
        kpi = json.load(f)
    assert "net_profit" in kpi
    assert "max_drawdown" in kpi
    assert "num_trades" in kpi
    assert "final_score" in kpi


def test_job_in_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that job is created in database with DONE status."""
    monkeypatch.chdir(tmp_path)
    db_path = tmp_path / "jobs.db"
    monkeypatch.setenv("JOBS_DB_PATH", str(db_path))
    
    run_id = main()
    
    # Check database
    conn = sqlite3.connect(str(db_path))
    try:
        cursor = conn.execute("SELECT status, run_id, report_link FROM jobs WHERE run_id = ?", (run_id,))
        row = cursor.fetchone()
        assert row is not None
        
        status, db_run_id, report_link = row
        assert status == "DONE"
        assert db_run_id == run_id
        assert report_link is not None
        assert report_link.startswith("/b5?")
        assert run_id in report_link
        assert "season=2026Q1" in report_link
    finally:
        conn.close()


def test_report_link_not_none(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that report_link is not None."""
    monkeypatch.chdir(tmp_path)
    db_path = tmp_path / "jobs.db"
    monkeypatch.setenv("JOBS_DB_PATH", str(db_path))
    
    run_id = main()
    
    conn = sqlite3.connect(str(db_path))
    try:
        cursor = conn.execute("SELECT report_link FROM jobs WHERE run_id = ?", (run_id,))
        row = cursor.fetchone()
        assert row is not None
        
        report_link = row[0]
        assert report_link is not None
        assert len(report_link) > 0
    finally:
        conn.close()


def test_kpi_values_aligned(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that KPI values align with Phase 6.1 registry."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("JOBS_DB_PATH", str(tmp_path / "jobs.db"))
    
    run_id = main()
    # Standard path structure: outputs/<season>/runs/<run_id>/
    run_dir = tmp_path / "outputs" / "seasons" / "2026Q1" / "runs" / run_id
    
    # Check kpi.json exists and has required KPIs (KPI唯一來源)
    kpi_path = run_dir / "kpi.json"
    assert kpi_path.exists()
    with kpi_path.open("r", encoding="utf-8") as f:
        kpi = json.load(f)
    
    assert "net_profit" in kpi
    assert "max_drawdown" in kpi
    assert "num_trades" in kpi
    assert "final_score" in kpi
    
    # Verify KPI values match expected
    assert kpi["net_profit"] == 123456
    assert kpi["max_drawdown"] == -0.18
    assert kpi["num_trades"] == 42
    assert kpi["final_score"] == 1.23
