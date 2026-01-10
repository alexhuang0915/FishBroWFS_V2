"""
Test evidence bundle completeness for SUCCEEDED and FAILED jobs.
"""
import tempfile
import json
from pathlib import Path
from unittest.mock import Mock, patch

from src.control.supervisor.handlers.base_governed import BaseGovernedHandler
from src.control.supervisor.job_handler import JobContext


class TestGovernedHandler(BaseGovernedHandler):
    """Test handler for evidence bundle tests."""
    __test__ = False  # Tell pytest not to collect this class as a test
    
    def __init__(self, evidence_base_dir: Path):
        super().__init__(evidence_base_dir)
        self.core_logic_called = False
        self.should_fail = False
    
    def get_job_type(self) -> str:
        return "PING"
    
    def core_logic(self, params: dict, context: JobContext) -> dict:
        self.core_logic_called = True
        
        if self.should_fail:
            raise RuntimeError("Simulated failure")
        
        # Write a test artifact
        artifact_path = Path(context.artifacts_dir) / "test_output.txt"
        artifact_path.write_text("test content")
        
        return {"status": "success", "value": 42}


def test_succeeded_job_evidence_completeness():
    """Test that SUCCEEDED jobs write complete evidence bundle."""
    with tempfile.TemporaryDirectory() as tmpdir:
        evidence_base_dir = Path(tmpdir) / "evidence"
        evidence_base_dir.mkdir()
        
        handler = TestGovernedHandler(evidence_base_dir)
        
        # Mock DB
        mock_db = Mock()
        mock_db.update_heartbeat = Mock()
        mock_db.is_abort_requested = Mock(return_value=False)
        
        # Create job context
        job_id = "test_job_123"
        artifacts_dir = evidence_base_dir / job_id
        artifacts_dir.mkdir()
        context = JobContext(job_id, mock_db, str(artifacts_dir))
        
        # Execute handler
        params = {"test": "value"}
        result = handler.execute(params, context)
        
        assert handler.core_logic_called
        assert result["status"] == "success"
        
        # Check evidence files
        required_files = [
            "manifest.json",
            "policy_check.json", 
            "inputs_fingerprint.json",
            "outputs_fingerprint.json",
            "runtime_metrics.json",
            "stdout_tail.log"
        ]
        
        for file in required_files:
            file_path = artifacts_dir / file
            assert file_path.exists(), f"Missing evidence file: {file}"
        
        # Check manifest content
        with open(artifacts_dir / "manifest.json", 'r') as f:
            manifest = json.load(f)
            assert manifest["job_id"] == job_id
            assert manifest["job_type"] == "PING"
            assert manifest["state"] == "SUCCEEDED"
            assert "start_time" in manifest
            assert "end_time" in manifest
        
        # Check outputs fingerprint includes our test artifact
        with open(artifacts_dir / "outputs_fingerprint.json", 'r') as f:
            outputs = json.load(f)
            assert "outputs" in outputs
            assert "test_output.txt" in outputs["outputs"]
            assert len(outputs["outputs"]["test_output.txt"]) == 64  # SHA256 hex length
        
        # Check runtime metrics
        with open(artifacts_dir / "runtime_metrics.json", 'r') as f:
            metrics = json.load(f)
            assert metrics["job_id"] == job_id
            assert metrics["handler_name"] == "TestGovernedHandler"
            assert metrics["execution_time_sec"] > 0
        
        print("✓ SUCCEEDED job evidence completeness test passed")


def test_failed_job_evidence_completeness():
    """Test that FAILED jobs still write evidence bundle."""
    with tempfile.TemporaryDirectory() as tmpdir:
        evidence_base_dir = Path(tmpdir) / "evidence"
        evidence_base_dir.mkdir()
        
        handler = TestGovernedHandler(evidence_base_dir)
        handler.should_fail = True
        
        # Mock DB
        mock_db = Mock()
        mock_db.update_heartbeat = Mock()
        mock_db.is_abort_requested = Mock(return_value=False)
        
        # Create job context
        job_id = "test_job_fail_123"
        artifacts_dir = evidence_base_dir / job_id
        artifacts_dir.mkdir()
        context = JobContext(job_id, mock_db, str(artifacts_dir))
        
        # Execute handler - should raise exception
        params = {"test": "value"}
        try:
            handler.execute(params, context)
            assert False, "Should have raised exception"
        except RuntimeError as e:
            assert str(e) == "Simulated failure"
        
        # Check evidence files were still written
        required_files = [
            "manifest.json",
            "policy_check.json",
            "inputs_fingerprint.json",
            "outputs_fingerprint.json",
            "runtime_metrics.json",
            "stdout_tail.log"
        ]
        
        for file in required_files:
            file_path = artifacts_dir / file
            assert file_path.exists(), f"Missing evidence file for failed job: {file}"
        
        # Check manifest indicates FAILED state
        with open(artifacts_dir / "manifest.json", 'r') as f:
            manifest = json.load(f)
            assert manifest["state"] == "FAILED"
            assert "error" in manifest
        
        # Check outputs fingerprint is empty for failed job
        with open(artifacts_dir / "outputs_fingerprint.json", 'r') as f:
            outputs = json.load(f)
            assert outputs["outputs"] == {}
        
        # Check runtime metrics includes error info
        with open(artifacts_dir / "runtime_metrics.json", 'r') as f:
            metrics = json.load(f)
            assert "custom_metrics" in metrics
            assert "error" in metrics["custom_metrics"]
        
        print("✓ FAILED job evidence completeness test passed")


def test_evidence_files_are_valid_json():
    """Test that all evidence files are valid JSON (except stdout_tail.log)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        evidence_base_dir = Path(tmpdir) / "evidence"
        evidence_base_dir.mkdir()
        
        handler = TestGovernedHandler(evidence_base_dir)
        
        # Mock DB
        mock_db = Mock()
        mock_db.update_heartbeat = Mock()
        mock_db.is_abort_requested = Mock(return_value=False)
        
        # Create job context
        job_id = "test_job_json_123"
        artifacts_dir = evidence_base_dir / job_id
        artifacts_dir.mkdir()
        context = JobContext(job_id, mock_db, str(artifacts_dir))
        
        # Execute handler
        params = {"test": "value"}
        handler.execute(params, context)
        
        # Check JSON files
        json_files = [
            "manifest.json",
            "policy_check.json",
            "inputs_fingerprint.json",
            "outputs_fingerprint.json",
            "runtime_metrics.json"
        ]
        
        for file in json_files:
            file_path = artifacts_dir / file
            with open(file_path, 'r') as f:
                try:
                    data = json.load(f)
                    assert isinstance(data, dict), f"{file} should be a dict"
                except json.JSONDecodeError as e:
                    assert False, f"{file} is not valid JSON: {e}"
        
        # Check stdout_tail.log is plain text
        stdout_path = artifacts_dir / "stdout_tail.log"
        assert stdout_path.exists()
        content = stdout_path.read_text()
        assert isinstance(content, str)
        
        print("✓ Evidence files valid JSON test passed")


if __name__ == "__main__":
    test_succeeded_job_evidence_completeness()
    test_failed_job_evidence_completeness()
    test_evidence_files_are_valid_json()
    print("All evidence bundle completeness tests passed!")