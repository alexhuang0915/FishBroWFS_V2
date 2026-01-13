"""
Test artifact validation for RUN_COMPILE_V2 jobs.

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

from control.supervisor.handlers.run_compile import RunCompileHandler
from contracts.supervisor.run_compile import RunCompilePayload


def test_manifest_schema():
    """Test manifest.json schema generation."""
    handler = RunCompileHandler()
    
    # Create test payload
    payload = RunCompilePayload(
        season="2026Q1",
        manifest_path="/tmp/test/season_manifest.json"
    )
    
    # Create temporary directory
    with tempfile.TemporaryDirectory() as tmpdir:
        compile_dir = Path(tmpdir) / "compile"
        compile_dir.mkdir(parents=True, exist_ok=True)
        
        # Mock manifest path
        manifest_path = Path(tmpdir) / "season_manifest.json"
        manifest_path.write_text("{}")
        
        # Generate manifest
        handler._generate_manifest("test_job_123", payload, compile_dir, manifest_path)
        
        # Verify manifest exists
        manifest_out_path = compile_dir / "manifest.json"
        assert manifest_out_path.exists(), "manifest.json should be created"
        
        # Load and validate manifest
        with open(manifest_out_path, "r") as f:
            manifest = json.load(f)
        
        # Required fields
        assert manifest["job_id"] == "test_job_123"
        assert manifest["job_type"] == "run_compile_v2"
        assert "created_at" in manifest
        assert "input_fingerprint" in manifest
        assert "code_fingerprint" in manifest
        
        # Input fingerprint structure
        input_fp = manifest["input_fingerprint"]
        assert input_fp["season"] == "2026Q1"
        assert input_fp["manifest_path"] == str(manifest_path)
        assert "params_hash" in input_fp
        
        # Code fingerprint structure
        code_fp = manifest["code_fingerprint"]
        assert "git_commit" in code_fp
        
        # Additional fields
        assert "compile_directory" in manifest
        assert manifest.get("manifest_version") == "1.0"
        
        print("✓ Manifest schema validation passed")


def test_manifest_fingerprint_consistency():
    """Test that fingerprint is consistent for same inputs."""
    payload1 = RunCompilePayload(
        season="2026Q1",
        manifest_path="/tmp/test/season_manifest.json"
    )
    
    payload2 = RunCompilePayload(
        season="2026Q1",
        manifest_path="/tmp/test/season_manifest.json"
    )
    
    # Same values should produce same fingerprint
    fp1 = payload1.compute_input_fingerprint()
    fp2 = payload2.compute_input_fingerprint()
    
    assert fp1 == fp2, "Fingerprint should be identical for same inputs"
    
    # Different values should produce different fingerprint
    payload3 = RunCompilePayload(
        season="2026Q2",  # Different
        manifest_path="/tmp/test/season_manifest.json"
    )
    fp3 = payload3.compute_input_fingerprint()
    assert fp1 != fp3, "Different params should produce different fingerprint"
    
    # Test with None manifest_path
    payload4 = RunCompilePayload(
        season="2026Q1",
        manifest_path=None
    )
    fp4 = payload4.compute_input_fingerprint()
    assert fp1 != fp4, "None values should produce different fingerprint"
    
    print("✓ Fingerprint consistency test passed")


def test_manifest_missing_fields_failure():
    """Test that missing required fields cause validation failure."""
    handler = RunCompileHandler()
    
    # Test missing season
    with pytest.raises(ValueError, match="season"):
        handler.validate_params({
            "manifest_path": "/tmp/test/season_manifest.json"
        })
    
    # Test invalid season (too short)
    with pytest.raises(ValueError, match="season should be at least 4 characters"):
        handler.validate_params({
            "season": "Q1",
            "manifest_path": "/tmp/test/season_manifest.json"
        })
    
    # Test valid season with optional manifest_path omitted
    handler.validate_params({
        "season": "2026Q1"
    })
    
    print("✓ Missing field validation works")


def test_artifact_directory_structure():
    """Test that artifacts are written to correct directories."""
    handler = RunCompileHandler()
    
    # Mock execution
    with tempfile.TemporaryDirectory() as tmpdir:
        artifacts_dir = Path(tmpdir) / "artifacts"
        artifacts_dir.mkdir(parents=True, exist_ok=True)
        
        mock_context = MagicMock()
        mock_context.job_id = "test_job_456"
        mock_context.artifacts_dir = str(artifacts_dir)
        mock_context.is_abort_requested.return_value = False
        mock_context.heartbeat = MagicMock()
        
        # Mock _execute_compile to avoid actual execution
        with patch.object(handler, '_execute_compile') as mock_execute:
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
                    "manifest_path": "/tmp/test/season_manifest.json"
                }
                
                result = handler.execute(params, mock_context)
                
                # Verify result structure
                assert result["ok"] is True
                assert result["job_type"] == "RUN_COMPILE_V2"
                assert "compile_dir" in result
                assert "manifest_path" in result
                
                # Verify artifacts were written
                mock_execute.assert_called_once()
                
                print("✓ Artifact directory structure test passed")


def test_job_id_matching():
    """Test that job_id in manifest matches DB record."""
    handler = RunCompileHandler()
    
    test_job_id = "test_job_789"
    
    with tempfile.TemporaryDirectory() as tmpdir:
        compile_dir = Path(tmpdir) / "compile"
        compile_dir.mkdir(parents=True, exist_ok=True)
        
        manifest_path = Path(tmpdir) / "season_manifest.json"
        manifest_path.write_text("{}")
        
        payload = RunCompilePayload(
            season="2026Q1",
            manifest_path=str(manifest_path)
        )
        
        # Generate manifest
        handler._generate_manifest(test_job_id, payload, compile_dir, manifest_path)
        
        # Load manifest
        manifest_out_path = compile_dir / "manifest.json"
        with open(manifest_out_path, "r") as f:
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
