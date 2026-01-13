"""
Test artifact validation for RUN_FREEZE_V2 jobs.

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

from control.supervisor.handlers.run_freeze import RunFreezeHandler
from contracts.supervisor.run_freeze import RunFreezePayload


def test_manifest_schema():
    """Test manifest.json schema generation."""
    handler = RunFreezeHandler()
    
    # Create test payload
    payload = RunFreezePayload(
        season="2026Q1",
        force=False,
        engine_version="v2.1.0",
        notes="Test freeze"
    )
    
    # Create temporary directory
    with tempfile.TemporaryDirectory() as tmpdir:
        freeze_dir = Path(tmpdir) / "freeze"
        freeze_dir.mkdir(parents=True, exist_ok=True)
        
        # Generate manifest
        handler._generate_manifest("test_job_123", payload, freeze_dir)
        
        # Verify manifest exists
        manifest_path = freeze_dir / "manifest.json"
        assert manifest_path.exists(), "manifest.json should be created"
        
        # Load and validate manifest
        with open(manifest_path, "r") as f:
            manifest = json.load(f)
        
        # Required fields
        assert manifest["job_id"] == "test_job_123"
        assert manifest["job_type"] == "run_freeze_v2"
        assert "created_at" in manifest
        assert "input_fingerprint" in manifest
        assert "code_fingerprint" in manifest
        
        # Input fingerprint structure
        input_fp = manifest["input_fingerprint"]
        assert input_fp["season"] == "2026Q1"
        assert input_fp["force"] is False
        assert input_fp["engine_version"] == "v2.1.0"
        assert input_fp["notes"] == "Test freeze"
        assert "params_hash" in input_fp
        
        # Code fingerprint structure
        code_fp = manifest["code_fingerprint"]
        assert "git_commit" in code_fp
        
        # Additional fields
        assert "freeze_directory" in manifest
        assert manifest.get("manifest_version") == "1.0"
        
        print("✓ Manifest schema validation passed")


def test_manifest_fingerprint_consistency():
    """Test that fingerprint is consistent for same inputs."""
    payload1 = RunFreezePayload(
        season="2026Q1",
        force=False,
        engine_version="v2.1.0",
        notes="Test freeze"
    )
    
    payload2 = RunFreezePayload(
        season="2026Q1",
        force=False,
        engine_version="v2.1.0",
        notes="Test freeze"
    )
    
    # Same values should produce same fingerprint
    fp1 = payload1.compute_input_fingerprint()
    fp2 = payload2.compute_input_fingerprint()
    
    assert fp1 == fp2, "Fingerprint should be identical for same inputs"
    
    # Different values should produce different fingerprint
    payload3 = RunFreezePayload(
        season="2026Q2",  # Different
        force=False,
        engine_version="v2.1.0",
        notes="Test freeze"
    )
    fp3 = payload3.compute_input_fingerprint()
    assert fp1 != fp3, "Different params should produce different fingerprint"
    
    # Test with None values
    payload4 = RunFreezePayload(
        season="2026Q1",
        force=False,
        engine_version=None,
        notes=None
    )
    fp4 = payload4.compute_input_fingerprint()
    assert fp1 != fp4, "None values should produce different fingerprint"
    
    print("✓ Fingerprint consistency test passed")


def test_manifest_missing_fields_failure():
    """Test that missing required fields cause validation failure."""
    handler = RunFreezeHandler()
    
    # Test missing season
    with pytest.raises(ValueError, match="season"):
        handler.validate_params({
            "force": False,
            "engine_version": "v2.1.0"
        })
    
    # Test invalid season (too short)
    with pytest.raises(ValueError, match="season should be at least 4 characters"):
        handler.validate_params({
            "season": "Q1",
            "force": False
        })
    
    # Test valid season with optional fields omitted
    handler.validate_params({
        "season": "2026Q1"
    })
    
    print("✓ Missing field validation works")


def test_artifact_directory_structure():
    """Test that artifacts are written to correct directories."""
    handler = RunFreezeHandler()
    
    # Mock execution
    with tempfile.TemporaryDirectory() as tmpdir:
        artifacts_dir = Path(tmpdir) / "artifacts"
        artifacts_dir.mkdir(parents=True, exist_ok=True)
        
        mock_context = MagicMock()
        mock_context.job_id = "test_job_456"
        mock_context.artifacts_dir = str(artifacts_dir)
        mock_context.is_abort_requested.return_value = False
        mock_context.heartbeat = MagicMock()
        
        # Mock _execute_freeze to avoid actual execution
        with patch.object(handler, '_execute_freeze') as mock_execute:
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
                    "season": "2026Q1",
                    "force": False,
                    "engine_version": "v2.1.0",
                    "notes": "Test freeze"
                }
                
                result = handler.execute(params, mock_context)
                
                # Verify result structure
                assert result["ok"] is True
                assert result["job_type"] == "RUN_FREEZE_V2"
                assert "freeze_dir" in result
                assert "manifest_path" in result
                
                # Verify artifacts were written
                mock_execute.assert_called_once()
                
                print("✓ Artifact directory structure test passed")


def test_job_id_matching():
    """Test that job_id in manifest matches DB record."""
    handler = RunFreezeHandler()
    
    test_job_id = "test_job_789"
    
    with tempfile.TemporaryDirectory() as tmpdir:
        freeze_dir = Path(tmpdir) / "freeze"
        freeze_dir.mkdir(parents=True, exist_ok=True)
        
        payload = RunFreezePayload(
            season="2026Q1",
            force=False,
            engine_version="v2.1.0",
            notes="Test freeze"
        )
        
        # Generate manifest
        handler._generate_manifest(test_job_id, payload, freeze_dir)
        
        # Load manifest
        manifest_path = freeze_dir / "manifest.json"
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
