"""
Test post-flight quality gate policies.
"""
import tempfile
import json
from pathlib import Path

from src.control.supervisor.policies.post_flight import QualityGate


def test_manifest_present_check():
    """Test check_manifest_present policy."""
    with tempfile.TemporaryDirectory() as tmpdir:
        evidence_dir = Path(tmpdir)
        
        quality_gate = QualityGate()
        
        # Test missing manifest
        checks = quality_gate.check(
            job_id="test_job",
            handler_name="TestHandler",
            result={},
            evidence_dir=evidence_dir
        )
        
        manifest_check = next(
            c for c in checks 
            if c.policy_name == "check_manifest_present"
        )
        assert not manifest_check.passed, "Missing manifest should fail"
        assert "does not exist" in manifest_check.message
        
        # Test invalid JSON manifest
        manifest_path = evidence_dir / "manifest.json"
        manifest_path.write_text("{invalid json")
        
        checks = quality_gate.check(
            job_id="test_job",
            handler_name="TestHandler",
            result={},
            evidence_dir=evidence_dir
        )
        
        manifest_check = next(
            c for c in checks 
            if c.policy_name == "check_manifest_present"
        )
        assert not manifest_check.passed, "Invalid JSON should fail"
        assert "invalid JSON" in manifest_check.message
        
        # Test manifest missing required fields
        manifest = {"job_id": "test_job"}  # Missing other fields
        manifest_path.write_text(json.dumps(manifest))
        
        checks = quality_gate.check(
            job_id="test_job",
            handler_name="TestHandler",
            result={},
            evidence_dir=evidence_dir
        )
        
        manifest_check = next(
            c for c in checks 
            if c.policy_name == "check_manifest_present"
        )
        assert not manifest_check.passed, "Incomplete manifest should fail"
        assert "missing fields" in manifest_check.message
        
        # Test valid manifest
        manifest = {
            "job_id": "test_job",
            "job_type": "PING",
            "state": "SUCCEEDED",
            "start_time": "2024-01-01T00:00:00Z",
            "end_time": "2024-01-01T01:00:00Z"
        }
        manifest_path.write_text(json.dumps(manifest))
        
        checks = quality_gate.check(
            job_id="test_job",
            handler_name="TestHandler",
            result={},
            evidence_dir=evidence_dir
        )
        
        manifest_check = next(
            c for c in checks 
            if c.policy_name == "check_manifest_present"
        )
        assert manifest_check.passed, "Valid manifest should pass"
        
        print("✓ Manifest present check test passed")


def test_required_outputs_exist_check():
    """Test check_required_outputs_exist policy."""
    with tempfile.TemporaryDirectory() as tmpdir:
        evidence_dir = Path(tmpdir)
        
        quality_gate = QualityGate()
        
        # Create minimal required files for RUN_RESEARCH_V2
        (evidence_dir / "manifest.json").write_text("{}")
        (evidence_dir / "policy_check.json").write_text("{}")
        (evidence_dir / "inputs_fingerprint.json").write_text("{}")
        
        # Test RUN_RESEARCH_V2 handler
        checks = quality_gate.check(
            job_id="test_job",
            handler_name="RunResearchV2Handler",
            result={},
            evidence_dir=evidence_dir
        )
        
        outputs_check = next(
            c for c in checks 
            if c.policy_name == "check_required_outputs_exist"
        )
        assert outputs_check.passed, "All required outputs exist"
        
        # Remove a required file
        (evidence_dir / "policy_check.json").unlink()
        
        checks = quality_gate.check(
            job_id="test_job",
            handler_name="RunResearchV2Handler",
            result={},
            evidence_dir=evidence_dir
        )
        
        outputs_check = next(
            c for c in checks 
            if c.policy_name == "check_required_outputs_exist"
        )
        assert not outputs_check.passed, "Missing required output should fail"
        assert "Missing" in outputs_check.message
        
        print("✓ Required outputs exist check test passed")


def test_quality_gate_downstream_admissible():
    """Test that downstream_admissible reflects all checks."""
    with tempfile.TemporaryDirectory() as tmpdir:
        evidence_dir = Path(tmpdir)
        
        quality_gate = QualityGate()
        
        # Create all required files
        (evidence_dir / "manifest.json").write_text(json.dumps({
            "job_id": "test_job",
            "job_type": "RUN_RESEARCH_V2",
            "state": "SUCCEEDED",
            "start_time": "2024-01-01T00:00:00Z",
            "end_time": "2024-01-01T01:00:00Z"
        }))
        (evidence_dir / "policy_check.json").write_text("{}")
        (evidence_dir / "inputs_fingerprint.json").write_text("{}")
        
        # All checks should pass
        checks = quality_gate.check(
            job_id="test_job",
            handler_name="RunResearchV2Handler",
            result={},
            evidence_dir=evidence_dir
        )
        
        all_passed = all(check.passed for check in checks)
        assert all_passed, "All checks should pass with complete evidence"
        
        # Remove manifest to cause failure
        (evidence_dir / "manifest.json").unlink()
        
        checks = quality_gate.check(
            job_id="test_job",
            handler_name="RunResearchV2Handler",
            result={},
            evidence_dir=evidence_dir
        )
        
        all_passed = all(check.passed for check in checks)
        assert not all_passed, "Missing manifest should cause failure"
        
        print("✓ Quality gate downstream admissible test passed")


if __name__ == "__main__":
    test_manifest_present_check()
    test_required_outputs_exist_check()
    test_quality_gate_downstream_admissible()
    print("All post-flight policy tests passed!")