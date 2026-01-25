
import sys
import os
import shutil
from pathlib import Path
import json

# Setup paths
src_path = str(Path.cwd() / "src")
if src_path not in sys.path:
    sys.path.insert(0, src_path)

from gui.tui.services.bridge import Bridge
from core.paths import get_outputs_root

def test_deletion():
    outputs_root = get_outputs_root()
    job_id = "test-deletion-target-123"
    
    # 1. Setup Evidence Dir
    evidence_root = outputs_root / "artifacts" / "jobs"
    job_evidence_dir = evidence_root / job_id
    job_evidence_dir.mkdir(parents=True, exist_ok=True)
    
    (job_evidence_dir / "stdout.log").write_text("dummy log")
    (job_evidence_dir / "spec.json").write_text("{}")
    
    # 1.5 Setup DB entry (Simulate actual job)
    import sqlite3
    from core.paths import get_db_path
    db_path = get_db_path()
    if db_path.exists():
        with sqlite3.connect(db_path) as conn:
            # We need all NOT NULL columns
            now = "2026-01-24T00:00:00Z"
            conn.execute("""
                INSERT OR REPLACE INTO jobs 
                (job_id, job_type, state, spec_json, created_at, updated_at) 
                VALUES (?, ?, ?, ?, ?, ?)
            """, (job_id, "TEST", "SUCCEEDED", "{}", now, now))
            conn.commit()
    
    # 2. Setup Linked Artifact...
    # (previous code continues)
    season_dir = outputs_root / "artifacts" / "seasons" / "TEST_SEASON" / "wfs" / job_id
    season_dir.mkdir(parents=True, exist_ok=True)
    result_json = season_dir / "result.json"
    result_json.write_text("{}")
    
    # 3. Create the link file
    path_txt = job_evidence_dir / "wfs_result_path.txt"
    path_txt.write_text(str(result_json))
    
    print(f"--- PRE-DELETE ---")
    print(f"Evidence Dir exists: {job_evidence_dir.exists()}")
    print(f"Result Json exists: {result_json.exists()}")
    
    # Check DB
    db_exists_pre = False
    if db_path.exists():
        with sqlite3.connect(db_path) as conn:
            row = conn.execute("SELECT job_id FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
            db_exists_pre = row is not None
    print(f"DB Entry exists: {db_exists_pre}")

    # 4. Trigger Deletion
    bridge = Bridge()
    result = bridge.delete_job_data(job_id)
    
    print(f"--- DELETE RESULT ---")
    print(json.dumps(result, indent=2))
    
    # Check DB Post
    db_exists_post = False
    if db_path.exists():
        with sqlite3.connect(db_path) as conn:
            row = conn.execute("SELECT job_id FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
            db_exists_post = row is not None

    print(f"--- POST-DELETE ---")
    print(f"Evidence Dir exists: {job_evidence_dir.exists()} (Expected: False)")
    print(f"Result Json exists: {result_json.exists()} (Expected: False)")
    print(f"Season Job Dir exists: {season_dir.exists()} (Expected: False)")
    print(f"DB Entry exists: {db_exists_post} (Expected: False)")
    
    if job_evidence_dir.exists() or result_json.exists() or db_exists_post:
        print("FAILURE: Deletion did not work as expected.")
        return False
    else:
        print("SUCCESS: Deletion logic verified (Including DB).")
        return True

if __name__ == "__main__":
    if test_deletion():
        sys.exit(0)
    else:
        sys.exit(1)
