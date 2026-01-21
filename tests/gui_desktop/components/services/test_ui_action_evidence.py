"""
Unit tests for ui_action_evidence module.
"""

import json
import tempfile
import shutil
from pathlib import Path
from unittest.mock import patch, mock_open

import pytest

from gui.services.ui_action_evidence import (
    write_abort_request_evidence,
    EvidenceWriteError,
    verify_evidence_write_possible,
    AbortRequestEvidence,
)


class TestUIActionEvidence:
    """Test suite for UI action evidence functions."""
    
    def setup_method(self):
        """Create a temporary directory for test outputs."""
        self.temp_dir = tempfile.mkdtemp(prefix="test_ui_action_evidence_")
        self.original_cwd = Path.cwd()
        # Change to temp directory for tests
        import os
        os.chdir(self.temp_dir)
    
    def teardown_method(self):
        """Clean up temporary directory."""
        import os
        os.chdir(self.original_cwd)
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_abort_request_evidence_dataclass(self):
        """Test AbortRequestEvidence dataclass and serialization."""
        evidence = AbortRequestEvidence(
            job_id="test_job_123",
            requested_at_utc="2026-01-13T01:30:00.000Z",
            reason="user_requested",
            ui_build="test_build_1.0",
            gate_enabled=True,
        )
        
        # Check default values
        assert evidence.schema_version == "1.0"
        assert evidence.action == "abort_request"
        assert evidence.requested_by == "desktop_ui"
        
        # Convert to dict
        evidence_dict = evidence.to_dict()
        
        # Check all fields are present
        expected_keys = {
            "schema_version", "action", "job_id", "requested_at_utc",
            "requested_by", "reason", "ui_build", "gate_enabled"
        }
        assert set(evidence_dict.keys()) == expected_keys
        
        # Check values
        assert evidence_dict["job_id"] == "test_job_123"
        assert evidence_dict["reason"] == "user_requested"
        assert evidence_dict["gate_enabled"] is True
        
        # Test JSON serialization
        json_str = json.dumps(evidence_dict, indent=2)
        parsed = json.loads(json_str)
        assert parsed["schema_version"] == "1.0"
    
    def test_write_abort_request_evidence_basic(self):
        """Test basic evidence writing."""
        job_id = "test_job_abc123"
        
        # Create outputs directory structure
        outputs_dir = Path("outputs")
        outputs_dir.mkdir(exist_ok=True)
        
        # Write evidence
        evidence_path = write_abort_request_evidence(job_id, reason="test_reason")
        
        # Check path
        assert evidence_path.exists()
        assert evidence_path.name == "abort_request.json"
        assert evidence_path.parent.name == "ui_actions"
        assert evidence_path.parent.parent.name == job_id
        assert evidence_path.parent.parent.parent.name == "jobs"
        assert evidence_path.parent.parent.parent.parent.name == "outputs"
        
        # Read and verify content
        with open(evidence_path, "r", encoding="utf-8") as f:
            evidence_data = json.load(f)
        
        assert evidence_data["schema_version"] == "1.0"
        assert evidence_data["action"] == "abort_request"
        assert evidence_data["job_id"] == job_id
        assert evidence_data["reason"] == "test_reason"
        assert evidence_data["gate_enabled"] is True
        assert evidence_data["requested_by"] == "desktop_ui"
        assert "requested_at_utc" in evidence_data  # Should be auto-generated
    
    def test_write_abort_request_evidence_no_overwrite(self):
        """Test that evidence writing doesn't overwrite existing files."""
        job_id = "test_job_no_overwrite"
        
        # Create outputs directory
        outputs_dir = Path("outputs")
        outputs_dir.mkdir(exist_ok=True)
        
        # Write first evidence
        path1 = write_abort_request_evidence(job_id)
        assert path1.name == "abort_request.json"
        
        # Write second evidence (should not overwrite)
        path2 = write_abort_request_evidence(job_id)
        assert path2.name == "abort_request_2.json"
        assert path2 != path1
        
        # Write third evidence
        path3 = write_abort_request_evidence(job_id)
        assert path3.name == "abort_request_3.json"
        
        # All files should exist
        assert path1.exists()
        assert path2.exists()
        assert path3.exists()
        
        # Verify all have unique content (different timestamps)
        with open(path1, "r") as f1, open(path2, "r") as f2:
            data1 = json.load(f1)
            data2 = json.load(f2)
            assert data1["requested_at_utc"] != data2["requested_at_utc"]
    
    def test_write_abort_request_evidence_invalid_job_id(self):
        """Test validation of job_id parameter."""
        with pytest.raises(ValueError, match="Invalid job_id"):
            write_abort_request_evidence("")
        
        with pytest.raises(ValueError, match="Invalid job_id"):
            write_abort_request_evidence(None)  # type: ignore
        
        with pytest.raises(ValueError, match="Invalid job_id"):
            write_abort_request_evidence(123)  # type: ignore
    
    def test_write_abort_request_evidence_directory_creation(self):
        """Test that directories are created if missing."""
        job_id = "test_job_new_dirs"
        
        # outputs directory doesn't exist yet
        assert not Path("outputs").exists()
        
        # Write evidence - should create all directories
        evidence_path = write_abort_request_evidence(job_id)
        
        # Check all directories were created
        assert evidence_path.exists()
        assert evidence_path.parent.exists()  # ui_actions
        assert evidence_path.parent.parent.exists()  # job_id
        assert evidence_path.parent.parent.parent.exists()  # jobs
        assert evidence_path.parent.parent.parent.parent.exists()  # outputs
    
    def test_write_abort_request_evidence_permission_error(self):
        """Test handling of permission errors."""
        job_id = "test_job_permission"
        
        # Mock Path.mkdir to raise PermissionError
        with patch.object(Path, "mkdir", side_effect=PermissionError("No permission")):
            with pytest.raises(EvidenceWriteError, match="Cannot create outputs directory"):
                write_abort_request_evidence(job_id)
    
    def test_write_abort_request_evidence_io_error(self):
        """Test handling of IO errors during file write."""
        job_id = "test_job_io_error"
        
        # Create outputs directory
        Path("outputs").mkdir(exist_ok=True)
        
        # Mock open to raise IOError
        with patch("builtins.open", side_effect=IOError("Disk full")):
            with pytest.raises(EvidenceWriteError, match="Cannot write evidence"):
                write_abort_request_evidence(job_id)
    
    def test_verify_evidence_write_possible_writable(self):
        """Test verify_evidence_write_possible when directory is writable."""
        # Create outputs directory
        outputs_dir = Path("outputs")
        outputs_dir.mkdir(exist_ok=True)
        
        # Should return True
        assert verify_evidence_write_possible() is True
    
    def test_verify_evidence_write_possible_not_writable(self):
        """Test verify_evidence_write_possible when directory is not writable."""
        # Create outputs directory first
        Path("outputs").mkdir(exist_ok=True)
        # Mock Path.touch to raise PermissionError
        with patch.object(Path, "touch", side_effect=PermissionError("No write permission")):
            assert verify_evidence_write_possible() is False
    
    def test_verify_evidence_write_possible_directory_creation(self):
        """Test verify_evidence_write_possible when outputs doesn't exist but can be created."""
        # outputs doesn't exist
        assert not Path("outputs").exists()
        
        # Should return True (directory can be created)
        assert verify_evidence_write_possible() is True
        
        # Directory should now exist
        assert Path("outputs").exists()
    
    def test_verify_evidence_write_possible_directory_creation_fails(self):
        """Test verify_evidence_write_possible when outputs can't be created."""
        # Mock Path.mkdir to raise PermissionError
        with patch.object(Path, "mkdir", side_effect=PermissionError("No permission")):
            assert verify_evidence_write_possible() is False
    
    def test_iso8601_utc_format(self):
        """Test that UTC timestamps are in ISO 8601 format."""
        from gui.services.ui_action_evidence import _get_iso8601_utc
        import re
        
        timestamp = _get_iso8601_utc()
        
        # ISO 8601 pattern: YYYY-MM-DDTHH:MM:SS.sssZ or with timezone offset
        iso_pattern = r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})$'
        assert re.match(iso_pattern, timestamp) is not None, f"Invalid ISO 8601 format: {timestamp}"
        
        # Should contain 'Z' or timezone offset (our implementation should produce Z)
        assert 'Z' in timestamp or '+' in timestamp or '-' in timestamp


if __name__ == "__main__":
    pytest.main([__file__, "-v"])