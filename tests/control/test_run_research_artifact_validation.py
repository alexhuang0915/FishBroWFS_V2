"""
Test artifact validation for RUN_RESEARCH_V2 jobs.

Verify:
- manifest.json exists
- Schema valid
- job_id matches DB record
"""

import pytest
import json
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock
import hashlib

from control.supervisor.handlers.run_research import RunResearchHandler
from contracts.supervisor.run_research import RunResearchPayload


def test_manifest_schema():
    """Test manifest.json schema generation."""
    handler = RunResearchHandler()
    
    # Create test payload (profile_name is derived from instrument)
    payload = RunResearchPayload(
        strategy_id="S1",
        start_date="2025-01-01",
        end_date="2025-01-31",
        params_override={
            "instrument": "CME.MNQ",
            "test_param": "value"
        }
    )
    
    # Create temporary directory
    with tempfile.TemporaryDirectory() as tmpdir:
        run_dir = Path(tmpdir) / "test_run"
        run_dir.mkdir(parents=True, exist_ok=True)
        
        # Generate manifest
        handler._generate_manifest("test_job_123", payload, run_dir)
        
        # Verify manifest exists
        manifest_path = run_dir / "manifest.json"
        assert manifest_path.exists(), "manifest.json should be created"
        
        # Load and validate manifest
        with open(manifest_path, "r") as f:
            manifest = json.load(f)
        
        # Required fields
        assert manifest["job_id"] == "test_job_123"
        assert manifest["job_type"] == "run_research_v2"
        assert "created_at" in manifest
        assert "input_fingerprint" in manifest
        assert "code_fingerprint" in manifest
        
        # Input fingerprint structure
        input_fp = manifest["input_fingerprint"]
        assert input_fp["strategy_id"] == "S1"
        # profile_name should be derived from instrument (CME_MNQ_TPE_v1)
        assert input_fp["profile_name"] == "CME_MNQ_TPE_v1"
        assert input_fp["start_date"] == "2025-01-01"
        assert input_fp["end_date"] == "2025-01-31"
        assert "params_hash" in input_fp
        
        # Code fingerprint structure
        code_fp = manifest["code_fingerprint"]
        assert "git_commit" in code_fp
        
        # Version
        assert manifest.get("manifest_version") == "1.0"
        
        print("✓ Manifest schema validation passed")


def test_manifest_fingerprint_consistency():
    """Test that fingerprint is consistent for same inputs."""
    payload1 = RunResearchPayload(
        strategy_id="S1",
        start_date="2025-01-01",
        end_date="2025-01-31",
        params_override={"param1": "value1", "param2": "value2"}
    )
    
    payload2 = RunResearchPayload(
        strategy_id="S1",
        start_date="2025-01-01",
        end_date="2025-01-31",
        params_override={"param2": "value2", "param1": "value1"}  # Different order
    )
    
    # Same values, different order should produce same fingerprint
    # because JSON serialization sorts keys
    fp1 = payload1.compute_input_fingerprint()
    fp2 = payload2.compute_input_fingerprint()
    
    assert fp1 == fp2, "Fingerprint should be order-independent"
    
    # Different values should produce different fingerprint
    payload3 = RunResearchPayload(
        strategy_id="S1",
        start_date="2025-01-01",
        end_date="2025-01-31",
        params_override={"param1": "different"}
    )
    fp3 = payload3.compute_input_fingerprint()
    assert fp1 != fp3, "Different params should produce different fingerprint"
    
    print("✓ Fingerprint consistency test passed")


def test_manifest_missing_fields_failure():
    """Test that missing required fields cause validation failure."""
    handler = RunResearchHandler()
    
    # Test missing strategy_id
    with pytest.raises(ValueError, match="strategy_id"):
        handler.validate_params({
            "start_date": "2025-01-01",
            "end_date": "2025-01-31"
        })
    
    # Test missing start_date
    with pytest.raises(ValueError, match="start_date"):
        handler.validate_params({
            "strategy_id": "S1",
            "end_date": "2025-01-31"
        })
    
    # Test invalid date format
    with pytest.raises(ValueError, match="start_date"):
        handler.validate_params({
            "strategy_id": "S1",
            "start_date": "01-01-2025",  # Wrong format
            "end_date": "2025-01-31"
        })
    
    # Test profile field is forbidden
    with pytest.raises(ValueError, match="Profile selection via payload is FORBIDDEN"):
        handler.validate_params({
            "strategy_id": "S1",
            "profile_name": "CME_MNQ_v2",
            "start_date": "2025-01-01",
            "end_date": "2025-01-31"
        })
    
    print("✓ Missing field validation works")


def test_artifact_directory_structure():
    """Test that artifacts are written to correct directories."""
    handler = RunResearchHandler()
    
    # Mock execution
    with tempfile.TemporaryDirectory() as tmpdir:
        artifacts_dir = Path(tmpdir) / "artifacts"
        artifacts_dir.mkdir(parents=True, exist_ok=True)
        
        mock_context = MagicMock()
        mock_context.job_id = "test_job_456"
        mock_context.artifacts_dir = str(artifacts_dir)
        mock_context.is_abort_requested.return_value = False
        mock_context.heartbeat = MagicMock()
        
        # Mock _execute_research to avoid actual execution
        with patch.object(handler, '_execute_research') as mock_execute:
            mock_execute.return_value = {
                "ok": True,
                "returncode": 0,
                "stdout_path": str(artifacts_dir / "stdout.txt"),
                "stderr_path": str(artifacts_dir / "stderr.txt"),
                "result": {"output_files": []}
            }
            
            # Mock _generate_manifest to avoid git operations
            with patch.object(handler, '_generate_manifest'):
                params = {
                    "strategy_id": "S1",
                    "start_date": "2025-01-01",
                    "end_date": "2025-01-31",
                    "params_override": {
                        "instrument": "CME.MNQ",
                        "timeframe": "60m",
                        "season": "2025",
                        "run_mode": "research"
                    }
                }
                
                result = handler.execute(params, mock_context)
                
                # Verify result structure
                assert result["ok"] is True
                assert result["job_type"] == "RUN_RESEARCH_V2"
                assert "run_dir" in result
                assert "manifest_path" in result
                
                # Verify artifacts were written
                # (mock_execute should have been called)
                mock_execute.assert_called_once()
                
                print("✓ Artifact directory structure test passed")


def test_job_id_matching():
    """Test that job_id in manifest matches DB record."""
    # This test would require actual DB integration
    # For now, test the logic conceptually
    handler = RunResearchHandler()
    
    test_job_id = "test_job_789"
    
    with tempfile.TemporaryDirectory() as tmpdir:
        run_dir = Path(tmpdir) / "test_run"
        run_dir.mkdir(parents=True, exist_ok=True)
        
        payload = RunResearchPayload(
            strategy_id="S1",
            start_date="2025-01-01",
            end_date="2025-01-31",
            params_override={"instrument": "CME.MNQ"}
        )
        
        # Generate manifest
        handler._generate_manifest(test_job_id, payload, run_dir)
        
        # Load manifest
        manifest_path = run_dir / "manifest.json"
        with open(manifest_path, "r") as f:
            manifest = json.load(f)
        
        # Verify job_id matches
        assert manifest["job_id"] == test_job_id
        
        print("✓ Job ID matching test passed")


if __name__ == "__main__":
    # Run tests
    test_manifest_schema()
    test_manifest_fingerprint_consistency()
    test_manifest_missing_fields_failure()
    test_artifact_directory_structure()
    test_job_id_matching()
    print("\n✅ All artifact validation tests passed!")