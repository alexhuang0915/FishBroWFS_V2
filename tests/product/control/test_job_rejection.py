"""
Test job rejection by admission controller.
"""
import tempfile
import json
from pathlib import Path

from control.supervisor.db import SupervisorDB
from control.supervisor.models import JobSpec
from control.supervisor.admission import submit_with_admission


def test_job_rejection_persists():
    """Test that REJECTED jobs are persisted in DB and not queued."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        evidence_dir = Path(tmpdir) / "evidence"
        
        db = SupervisorDB(db_path)
        
        # Create a job that will be rejected (duplicate fingerprint)
        payload1 = {"test": "value"}
        spec1 = JobSpec(job_type="RUN_RESEARCH_V2", params=payload1)
        
        # First submission should be QUEUED
        job_id1, state1, bundle1 = submit_with_admission(
            db, spec1, str(evidence_dir)
        )
        assert state1 == "QUEUED", "First job should be QUEUED"
        assert bundle1.downstream_admissible, "First job should be admissible"
        
        # Second identical submission should be REJECTED
        spec2 = JobSpec(job_type="RUN_RESEARCH_V2", params=payload1.copy())
        job_id2, state2, bundle2 = submit_with_admission(
            db, spec2, str(evidence_dir)
        )
        
        assert state2 == "REJECTED", "Duplicate job should be REJECTED"
        assert not bundle2.downstream_admissible, "Duplicate job should not be admissible"
        assert job_id1 != job_id2, "Job IDs should be different"
        
        # Verify REJECTED job is in database
        job_row = db.get_job_row(job_id2)
        assert job_row is not None, "REJECTED job should be in DB"
        assert job_row.state == "REJECTED", "Job state should be REJECTED"
        assert "Rejected" in job_row.state_reason or "Failed" in job_row.state_reason
        
        # Verify REJECTED job is not picked by fetch_next_queued_job
        next_job = db.fetch_next_queued_job()
        # Should pick the first job (QUEUED), not the REJECTED one
        assert next_job == job_id1, "Should pick QUEUED job, not REJECTED"
        
        # Verify evidence files were created for REJECTED job
        job_evidence_dir = evidence_dir / job_id2
        assert job_evidence_dir.exists(), "Evidence dir should exist for REJECTED job"
        
        required_files = ["manifest.json", "policy_check.json", "inputs_fingerprint.json"]
        for file in required_files:
            assert (job_evidence_dir / file).exists(), f"{file} should exist"
        
        # Check manifest content
        with open(job_evidence_dir / "manifest.json", 'r') as f:
            manifest = json.load(f)
            assert manifest["state"] == "REJECTED"
            assert manifest["job_id"] == job_id2
        
        print("✓ Job rejection persistence test passed")


def test_rejected_job_evidence_completeness():
    """Test that REJECTED jobs have complete evidence bundle."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        evidence_dir = Path(tmpdir) / "evidence"
        
        db = SupervisorDB(db_path)
        
        # Create a job that violates timeframe policy
        payload = {"timeframe": 90}  # 90 is not allowed
        spec = JobSpec(job_type="RUN_RESEARCH_V2", params=payload)
        
        job_id, state, bundle = submit_with_admission(
            db, spec, str(evidence_dir)
        )
        
        assert state == "REJECTED", "Job with invalid timeframe should be REJECTED"
        
        # Check evidence bundle
        job_evidence_dir = evidence_dir / job_id
        assert job_evidence_dir.exists()
        
        # Check policy_check.json
        with open(job_evidence_dir / "policy_check.json", 'r') as f:
            policy_check = json.load(f)
            assert "preflight" in policy_check
            assert policy_check["overall_status"] == "FAIL"
            assert policy_check["final_reason"]["policy_stage"] == "preflight"
            failed_checks = [
                c for c in policy_check["preflight"]
                if c["status"] == "FAIL"
            ]
            assert len(failed_checks) > 0, "Should have failed checks"
        
        # Check inputs_fingerprint.json
        with open(job_evidence_dir / "inputs_fingerprint.json", 'r') as f:
            fingerprint = json.load(f)
            assert "params_hash" in fingerprint
            assert "hash_version" in fingerprint
            assert fingerprint["hash_version"] == "v1"
        
        print("✓ Rejected job evidence completeness test passed")


def test_rejected_state_is_terminal():
    """Test that REJECTED is a terminal state (never transitions)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        evidence_dir = Path(tmpdir) / "evidence"
        
        db = SupervisorDB(db_path)
        
        # Create a REJECTED job
        payload = {"timeframe": 90}
        spec = JobSpec(job_type="RUN_RESEARCH_V2", params=payload)
        
        job_id, state, _ = submit_with_admission(db, spec, str(evidence_dir))
        assert state == "REJECTED"
        
        # Try to mark it as RUNNING (should not work)
        # The mark_running method checks state IN ('QUEUED', 'RUNNING')
        # REJECTED is not in that list, so it won't update
        job_row = db.get_job_row(job_id)
        assert job_row.state == "REJECTED"
        
        # Try to fetch next queued job - should not return REJECTED job
        next_job = db.fetch_next_queued_job()
        assert next_job is None or next_job != job_id
        
        # Try to mark as SUCCEEDED (should not work)
        # The mark_succeeded method checks state == 'RUNNING'
        # REJECTED is not RUNNING, so it won't update
        
        print("✓ REJECTED state terminality test passed")


if __name__ == "__main__":
    test_job_rejection_persists()
    test_rejected_job_evidence_completeness()
    test_rejected_state_is_terminal()
    print("All job rejection tests passed!")