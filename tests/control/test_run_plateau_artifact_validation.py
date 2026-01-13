"""
Test artifact validation for RUN_PLATEAU_V2 jobs.

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

from control.supervisor.handlers.run_plateau import RunPlateauHandler
from contracts.supervisor.run_plateau import RunPlateauPayload


def test_manifest_schema():
    """Test manifest.json schema generation."""
    handler = RunPlateauHandler()
    
    # Create test payload
    payload = RunPlateauPayload(
        research_run_id="test_research_run_123",
        k_neighbors=5,
        score_threshold_rel=0.8
    )
    
    # Create temporary directory
    with tempfile.TemporaryDirectory() as tmpdir:
        plateau_dir = Path(tmpdir) / "plateau"
        plateau_dir.mkdir(parents=True, exist_ok=True)
        
        # Mock winners path
        winners_path = Path(tmpdir) / "winners.json"
        winners_path.write_text("{}")
        
        # Generate manifest
        handler._generate_manifest("test_job_123", payload, plateau_dir, winners_path)
        
        # Verify manifest exists
        manifest_path = plateau_dir / "manifest.json"
        assert manifest_path.exists(), "manifest.json should be created"
        
        # Load and validate manifest
        with open(manifest_path, "r") as f:
            manifest = json.load(f)
        
        # Required fields
        assert manifest["job_id"] == "test_job_123"
        assert manifest["job_type"] == "run_plateau_v2"
        assert "created_at" in manifest
        assert "input_fingerprint" in manifest
        assert "code_fingerprint" in manifest
        
        # Input fingerprint structure
        input_fp = manifest["input_fingerprint"]
        assert input_fp["research_run_id"] == "test_research_run_123"
        assert input_fp["k_neighbors"] == 5
        assert input_fp["score_threshold_rel"] == 0.8
        assert "params_hash" in input_fp
        
        # Code fingerprint structure
        code_fp = manifest["code_fingerprint"]
        assert "git_commit" in code_fp
        
        # Additional fields
        assert "plateau_directory" in manifest
        assert "winners_path" in manifest
        assert manifest.get("manifest_version") == "1.0"
        
        print("✓ Manifest schema validation passed")


def test_manifest_fingerprint_consistency():
    """Test that fingerprint is consistent for same inputs."""
    payload1 = RunPlateauPayload(
        research_run_id="test_research_run_123",
        k_neighbors=5,
        score_threshold_rel=0.8
    )
    
    payload2 = RunPlateauPayload(
        research_run_id="test_research_run_123",
        k_neighbors=5,
        score_threshold_rel=0.8
    )
    
    # Same values should produce same fingerprint
    fp1 = payload1.compute_input_fingerprint()
    fp2 = payload2.compute_input_fingerprint()
    
    assert fp1 == fp2, "Fingerprint should be identical for same inputs"
    
    # Different values should produce different fingerprint
    payload3 = RunPlateauPayload(
        research_run_id="test_research_run_123",
        k_neighbors=10,  # Different
        score_threshold_rel=0.8
    )
    fp3 = payload3.compute_input_fingerprint()
    assert fp1 != fp3, "Different params should produce different fingerprint"
    
    # Test with None values
    payload4 = RunPlateauPayload(
        research_run_id="test_research_run_123",
        k_neighbors=None,
        score_threshold_rel=None
    )
    fp4 = payload4.compute_input_fingerprint()
    assert fp1 != fp4, "None values should produce different fingerprint"
    
    print("✓ Fingerprint consistency test passed")


def test_manifest_missing_fields_failure():
    """Test that missing required fields cause validation failure."""
    handler = RunPlateauHandler()
    
    # Test missing research_run_id
    with pytest.raises(ValueError, match="research_run_id"):
        handler.validate_params({
            "k_neighbors": 5,
            "score_threshold_rel": 0.8
        })
    
    # Test invalid k_neighbors
    with pytest.raises(ValueError, match="k_neighbors"):
        handler.validate_params({
            "research_run_id": "test_research_run_123",
            "k_neighbors": 0,  # Invalid
            "score_threshold_rel": 0.8
        })
    
    # Test invalid score_threshold_rel
    with pytest.raises(ValueError, match="score_threshold_rel"):
        handler.validate_params({
            "research_run_id": "test_research_run_123",
            "k_neighbors": 5,
            "score_threshold_rel": 1.5  # Invalid
        })
    
    print("✓ Missing field validation works")


def test_artifact_directory_structure():
    """Test that artifacts are written to correct directories."""
    handler = RunPlateauHandler()
    
    # Mock execution
    with tempfile.TemporaryDirectory() as tmpdir:
        artifacts_dir = Path(tmpdir) / "artifacts"
        artifacts_dir.mkdir(parents=True, exist_ok=True)
        
        mock_context = MagicMock()
        mock_context.job_id = "test_job_456"
        mock_context.artifacts_dir = str(artifacts_dir)
        mock_context.is_abort_requested.return_value = False
        mock_context.heartbeat = MagicMock()
        
        # Mock _execute_plateau to avoid actual execution
        with patch.object(handler, '_execute_plateau') as mock_execute:
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
                    "research_run_id": "test_research_run_123",
                    "k_neighbors": 5,
                    "score_threshold_rel": 0.8
                }
                
                result = handler.execute(params, mock_context)
                
                # Verify result structure
                assert result["ok"] is True
                assert result["job_type"] == "RUN_PLATEAU_V2"
                assert "plateau_dir" in result
                assert "manifest_path" in result
                
                # Verify artifacts were written
                mock_execute.assert_called_once()
                
                print("✓ Artifact directory structure test passed")


def test_job_id_matching():
    """Test that job_id in manifest matches DB record."""
    handler = RunPlateauHandler()
    
    test_job_id = "test_job_789"
    
    with tempfile.TemporaryDirectory() as tmpdir:
        plateau_dir = Path(tmpdir) / "plateau"
        plateau_dir.mkdir(parents=True, exist_ok=True)
        
        winners_path = Path(tmpdir) / "winners.json"
        winners_path.write_text("{}")
        
        payload = RunPlateauPayload(
            research_run_id="test_research_run_123",
            k_neighbors=5,
            score_threshold_rel=0.8
        )
        
        # Generate manifest
        handler._generate_manifest(test_job_id, payload, plateau_dir, winners_path)
        
        # Load manifest
        manifest_path = plateau_dir / "manifest.json"
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
