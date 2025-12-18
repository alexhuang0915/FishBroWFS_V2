"""Seed demo run for Viewer validation.

Creates a DONE job with minimal artifacts for Viewer testing.
Does NOT run engine - only writes files.
"""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from FishBroWFS_V2.control.jobs_db import init_db
from FishBroWFS_V2.control.report_links import build_report_link
from FishBroWFS_V2.control.types import JobStatus
from FishBroWFS_V2.core.paths import ensure_run_dir

# Default DB path (same as api.py)
DEFAULT_DB_PATH = Path("outputs/jobs.db")


def get_db_path() -> Path:
    """Get database path from environment or default."""
    db_path_str = os.getenv("JOBS_DB_PATH")
    if db_path_str:
        return Path(db_path_str)
    return DEFAULT_DB_PATH


def main() -> str:
    """
    Create demo job with minimal artifacts.
    
    Returns:
        run_id of created demo job
        
    Contract:
        - Never raises exceptions
        - Does NOT import engine
        - Does NOT run backtest
        - Does NOT touch worker
        - Does NOT need dataset
    """
    try:
        # Generate run_id
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        run_id = f"demo_{timestamp}"
        
        # Initialize DB if needed
        db_path = get_db_path()
        init_db(db_path)
        
        # Create outputs directory (use standard path structure: outputs/<season>/runs/<run_id>/)
        outputs_root = Path("outputs")
        season = "2026Q1"  # Default season for demo
        run_dir = ensure_run_dir(outputs_root, season, run_id)
        
        # Write minimal artifacts
        _write_manifest(run_dir, run_id, season)
        _write_winners_v2(run_dir)
        _write_governance(run_dir)
        _write_kpi(run_dir)
        
        # Create job record (status = DONE)
        _create_demo_job(db_path, run_id, season)
        
        return run_id
    
    except Exception as e:
        print(f"ERROR: Failed to create demo job: {e}")
        raise


def _write_manifest(run_dir: Path, run_id: str, season: str) -> None:
    """Write minimal manifest.json."""
    manifest = {
        "run_id": run_id,
        "season": season,
        "config_hash": "demo-config-hash",
        "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "stages": [],
        "meta": {},
    }
    
    manifest_path = run_dir / "manifest.json"
    with manifest_path.open("w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, sort_keys=True)


def _write_winners_v2(run_dir: Path) -> None:
    """Write minimal winners_v2.json."""
    winners_v2 = {
        "config_hash": "demo-config-hash",
        "schema_version": "v2",
        "run_id": "demo",
        "rows": [],
        "meta": {},
    }
    
    winners_path = run_dir / "winners_v2.json"
    with winners_path.open("w", encoding="utf-8") as f:
        json.dump(winners_v2, f, indent=2, sort_keys=True)


def _write_governance(run_dir: Path) -> None:
    """Write minimal governance.json."""
    governance = {
        "config_hash": "demo-config-hash",
        "schema_version": "v1",
        "run_id": "demo",
        "rows": [],
        "meta": {},
    }
    
    governance_path = run_dir / "governance.json"
    with governance_path.open("w", encoding="utf-8") as f:
        json.dump(governance, f, indent=2, sort_keys=True)


def _write_kpi(run_dir: Path) -> None:
    """Write kpi.json with KPI values aligned with Phase 6.1 registry."""
    kpi = {
        "net_profit": 123456,
        "max_drawdown": -0.18,
        "num_trades": 42,
        "final_score": 1.23,
    }
    
    kpi_path = run_dir / "kpi.json"
    with kpi_path.open("w", encoding="utf-8") as f:
        json.dump(kpi, f, indent=2, sort_keys=True)


def _create_demo_job(db_path: Path, run_id: str, season: str) -> None:
    """
    Create demo job record in database.
    
    Uses direct SQL to create job with DONE status and report_link.
    """
    job_id = str(uuid4())
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    
    # Generate report link
    report_link = build_report_link(season, run_id)
    
    conn = sqlite3.connect(str(db_path))
    try:
        # Ensure schema
        from FishBroWFS_V2.control.jobs_db import ensure_schema
        ensure_schema(conn)
        
        # Insert job with DONE status
        # Note: requested_pause is required (defaults to 0)
        conn.execute("""
            INSERT INTO jobs (
                job_id, status, created_at, updated_at,
                season, dataset_id, outputs_root, config_hash,
                config_snapshot_json, requested_pause, run_id, report_link
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            job_id,
            JobStatus.DONE.value,
            now,
            now,
            season,
            "demo_dataset",
            "outputs",
            "demo-config-hash",
            json.dumps({}),
            0,  # requested_pause
            run_id,
            report_link,
        ))
        
        conn.commit()
    finally:
        conn.close()


if __name__ == "__main__":
    run_id = main()
    print(f"Demo job created: {run_id}")
    print(f"Outputs: outputs/seasons/2026Q1/runs/{run_id}/")
    print(f"Report link: /b5?season=2026Q1&run_id={run_id}")
