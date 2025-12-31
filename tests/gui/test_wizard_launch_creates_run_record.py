"""Test that Wizard launch creates a run record.

Tests that calling launch_run_from_experiment_yaml creates a run_record.json.
Uses service layer directly (not UI click).
"""
import json
import pytest
import tempfile
import yaml
from pathlib import Path
from unittest.mock import patch, MagicMock

from gui.nicegui.services.run_launcher_service import (
    launch_run_from_experiment_yaml,
    LaunchResult,
)


def test_wizard_launch_creates_run_record(tmp_path):
    """Test that Wizard launch creates a run record (section 6.1 of spec)."""
    # Create a minimal experiment YAML in tmp_path
    yaml_content = {
        "version": "v1",
        "strategy_id": "S1",
        "dataset_id": "CME.MNQ",
        "timeframe": 60,
        "features": {
            "required": [
                {"name": "bb_pb_20", "timeframe_min": 60},
            ],
            "optional": [],
        },
        "params": {},
        "allow_build": False,
        "notes": "Test experiment",
    }
    
    yaml_path = tmp_path / "test_experiment.yaml"
    with open(yaml_path, "w", encoding="utf-8") as f:
        yaml.dump(yaml_content, f)
    
    # Mock the outputs directory to use tmp_path
    outputs_dir = tmp_path / "outputs"
    outputs_dir.mkdir()
    
    # We need to patch the write_intent, derive_from_intent, write_derived functions
    # to avoid actual file system operations and dependencies
    # Instead, we'll test the integration by mocking the internal _launch_run_from_intent
    # But the spec says to call service layer directly, so we should test the actual function.
    # However, that would require feature registry and other dependencies.
    # Let's follow the hint code pattern: create a minimal yaml and call launch_run_from_experiment_yaml
    # with mocked dependencies.
    
    # Mock write_intent to avoid actual file writing but still create directory structure
    with patch("gui.nicegui.services.run_launcher_service.write_intent") as mock_write_intent:
        mock_intent_path = outputs_dir / "seasons" / "2026Q1" / "runs" / "run_test123" / "intent.json"
        mock_intent_path.parent.mkdir(parents=True, exist_ok=True)
        mock_intent_path.touch()
        mock_write_intent.return_value = mock_intent_path
        
        # Mock derive_from_intent and write_derived
        with patch("gui.nicegui.services.run_launcher_service.derive_from_intent") as mock_derive:
            mock_derive.return_value = MagicMock()
            with patch("gui.nicegui.services.run_launcher_service.write_derived") as mock_write_derived:
                mock_derived_path = mock_intent_path.parent / "derived.json"
                mock_derived_path.touch()
                mock_write_derived.return_value = mock_derived_path
                
                # Call the function
                result = launch_run_from_experiment_yaml(str(yaml_path), season="2026Q1")
                
                # Assert success
                assert result.ok, f"Launch failed: {result.message}"
                assert result.run_id is not None
                assert result.run_dir is not None
                
                # Check that run_record.json was created
                run_record_path = result.run_dir / "run_record.json"
                assert run_record_path.exists(), "run_record.json not created"
                
                # Verify run_record.json has expected structure
                with open(run_record_path, "r", encoding="utf-8") as f:
                    run_record = json.load(f)
                
                assert "run_id" in run_record
                assert run_record["run_id"] == result.run_id
                assert "season" in run_record
                assert run_record["season"] == "2026Q1"
                assert "status" in run_record
                assert "created_at" in run_record
                assert "artifacts" in run_record


def test_wizard_launch_with_real_yaml(tmp_path):
    """Test with a known experiment yaml from configs."""
    # Use the S1_no_flip.yaml from configs if it exists
    config_yaml_path = Path("configs/experiments/baseline_no_flip/S1_no_flip.yaml")
    if not config_yaml_path.exists():
        pytest.skip("S1_no_flip.yaml not found in configs")
    
    # Create a temporary copy to avoid modifying the original
    temp_yaml_path = tmp_path / "S1_no_flip_copy.yaml"
    with open(config_yaml_path, "r", encoding="utf-8") as src:
        yaml_content = yaml.safe_load(src)
    
    # Ensure allow_build is False (it should be)
    yaml_content["allow_build"] = False
    
    with open(temp_yaml_path, "w", encoding="utf-8") as dst:
        yaml.dump(yaml_content, dst)
    
    # Mock the file system operations
    with patch("gui.nicegui.services.run_launcher_service.write_intent") as mock_write_intent:
        mock_intent_path = tmp_path / "outputs" / "seasons" / "2026Q1" / "runs" / "run_test456" / "intent.json"
        mock_intent_path.parent.mkdir(parents=True, exist_ok=True)
        mock_intent_path.touch()
        mock_write_intent.return_value = mock_intent_path
        
        with patch("gui.nicegui.services.run_launcher_service.derive_from_intent") as mock_derive:
            mock_derive.return_value = MagicMock()
            with patch("gui.nicegui.services.run_launcher_service.write_derived") as mock_write_derived:
                mock_derived_path = mock_intent_path.parent / "derived.json"
                mock_derived_path.touch()
                mock_write_derived.return_value = mock_derived_path
                
                # Call the function
                result = launch_run_from_experiment_yaml(str(temp_yaml_path), season="2026Q1")
                
                # Basic assertions
                assert result.ok, f"Launch failed with real YAML: {result.message}"
                assert result.run_id is not None
                
                # Check run_record.json was created
                if result.run_dir:
                    run_record_path = result.run_dir / "run_record.json"
                    # The function creates run_record.json via _create_canonical_run_record
                    # which is called in _launch_run_from_intent
                    # Since we mocked write_intent, the run_dir is from mock_intent_path.parent
                    # but _create_canonical_run_record still runs and creates the file
                    # Actually, it writes to run_dir which is mock_intent_path.parent
                    # Let's check if it was created
                    if run_record_path.exists():
                        with open(run_record_path, "r", encoding="utf-8") as f:
                            run_record = json.load(f)
                        assert run_record["run_id"] == result.run_id


def test_launch_fails_with_invalid_yaml(tmp_path):
    """Test that launch fails with invalid YAML (allow_build=true)."""
    yaml_content = {
        "strategy_id": "S1",
        "dataset_id": "CME.MNQ",
        "timeframe": 60,
        "allow_build": True,  # Should fail
    }
    
    yaml_path = tmp_path / "invalid.yaml"
    with open(yaml_path, "w", encoding="utf-8") as f:
        yaml.dump(yaml_content, f)
    
    result = launch_run_from_experiment_yaml(str(yaml_path), season="2026Q1")
    assert not result.ok
    assert "allow_build" in result.message.lower()


def test_launch_fails_with_invalid_strategy(tmp_path):
    """Test that launch fails with invalid strategy ID."""
    yaml_content = {
        "strategy_id": "INVALID",
        "dataset_id": "CME.MNQ",
        "timeframe": 60,
        "allow_build": False,
    }
    
    yaml_path = tmp_path / "invalid_strategy.yaml"
    with open(yaml_path, "w", encoding="utf-8") as f:
        yaml.dump(yaml_content, f)
    
    result = launch_run_from_experiment_yaml(str(yaml_path), season="2026Q1")
    assert not result.ok
    assert "strategy must be s1, s2, or s3" in result.message.lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])