"""
Test Data2 Prepare Enforcement (Phase 18.7).

Tests that Data2 feeds are auto-prepared when selected and missing artifacts.
"""
import pytest
from pathlib import Path
import tempfile
import shutil
from unittest.mock import Mock, patch, MagicMock
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

from gui.desktop.tabs.op_tab import OpTab
from control.prepare_orchestration import prepare_with_data2_enforcement


@pytest.fixture
def app():
    """Create QApplication instance for GUI tests."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture
def op_tab(app):
    """Create OpTab instance for testing."""
    tab = OpTab()
    yield tab
    tab.deleteLater()


@pytest.fixture
def temp_outputs_dir():
    """Create temporary outputs directory for testing."""
    temp_dir = tempfile.mkdtemp(prefix="test_data2_prepare_")
    outputs_dir = Path(temp_dir) / "outputs"
    outputs_dir.mkdir(parents=True)
    
    # Create minimal directory structure
    season_dir = outputs_dir / "seasons" / "2026Q1" / "shared"
    season_dir.mkdir(parents=True)
    
    yield outputs_dir
    
    # Cleanup
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.mark.skip(reason="UI feature 'data2 prepared feeds' not yet implemented")
def test_data2_prepare_enforcement_basic(op_tab):
    """Test that Data2 preparation tracking works correctly."""
    # Clear any existing prepared feeds
    op_tab.data2_prepared_feeds.clear()
    op_tab.selected_context_feeds.clear()
    
    # Add some test feeds
    test_feeds = ["VX.FUT", "DX.FUT", "ZN.FUT"]
    for feed in test_feeds:
        op_tab.selected_context_feeds.add(feed)
    
    # Initially, no feeds should be marked as prepared
    assert len(op_tab.data2_prepared_feeds) == 0
    
    # Simulate prepare completion with these feeds
    payload = {
        "context_feeds": test_feeds,
        "result": {
            "no_change": False,  # Data2 was newly prepared
            "data2_reports": {
                "VX.FUT": {"success": True},
                "DX.FUT": {"success": True},
                "ZN.FUT": {"success": True},
            }
        }
    }
    
    op_tab.on_prepare_finished(payload)
    
    # All feeds should now be marked as prepared
    assert len(op_tab.data2_prepared_feeds) == 3
    for feed in test_feeds:
        assert feed in op_tab.data2_prepared_feeds
    
    # Run Analysis button should be enabled (if other conditions met)
    # We'll test the gating logic separately


@pytest.mark.skip(reason="UI feature 'data2 prepared feeds' not yet implemented")
def test_data2_gating_logic(op_tab):
    """Test that Run Research button is disabled when Data2 selected but not prepared."""
    # Clear state
    op_tab.selected_context_feeds.clear()
    op_tab.data2_prepared_feeds.clear()
    
    # Set basic requirements to be met
    op_tab.primary_market_cb.addItems(["MNQ.FUT"])  # Add a market
    op_tab.primary_market_cb.setCurrentText("MNQ.FUT")
    
    # Select a timeframe
    for cb in op_tab.timeframe_checkboxes.values():
        cb.setChecked(False)
    op_tab.timeframe_checkboxes["60m"].setChecked(True)
    
    # Test 1: No Data2 selected - button should be enabled (if data ready)
    # We'll mock cache status as READY
    op_tab.bars_cache_status = "READY"
    op_tab.features_cache_status = "READY"
    
    op_tab.update_run_analysis_button()
    # Button state depends on cache status, but gating logic should pass
    
    # Test 2: Data2 selected but not prepared - button should be disabled
    op_tab.selected_context_feeds.add("VX.FUT")
    op_tab.update_run_analysis_button()
    
    # Check tooltip for the expected message
    tooltip = op_tab.run_research_btn.toolTip()
    assert "Context feeds selected. Preparing required data..." in tooltip
    assert not op_tab.run_research_btn.isEnabled()
    
    # Test 3: Data2 selected and prepared - button should be enabled (if data ready)
    op_tab.data2_prepared_feeds.add("VX.FUT")
    op_tab.update_run_analysis_button()
    
    # Tooltip should change
    tooltip = op_tab.run_research_btn.toolTip()
    assert "Context feeds selected. Preparing required data..." not in tooltip
    # Button enabled state depends on cache status


@pytest.mark.skip(reason="UI feature 'data2 prepared feeds' not yet implemented")
def test_data2_selection_marks_prepare_dirty(op_tab):
    """Test that changing Data2 selection marks Prepare as DIRTY (clears prepared status)."""
    # Start with a prepared feed
    op_tab.data2_prepared_feeds.add("VX.FUT")
    op_tab.data2_prepared_feeds.add("DX.FUT")
    
    # Select VX.FUT
    op_tab.selected_context_feeds.add("VX.FUT")
    
    # Now change VX.FUT selection (uncheck)
    op_tab.on_context_feed_changed("VX.FUT", Qt.Unchecked)
    
    # VX.FUT should be removed from prepared feeds (since selection changed)
    assert "VX.FUT" not in op_tab.data2_prepared_feeds
    # DX.FUT should still be there (wasn't selected/changed)
    assert "DX.FUT" in op_tab.data2_prepared_feeds
    
    # Select VX.FUT again
    op_tab.on_context_feed_changed("VX.FUT", Qt.Checked)
    # Still not prepared (was just selected)
    assert "VX.FUT" not in op_tab.data2_prepared_feeds


def test_prepare_orchestration_contract():
    """Test the prepare orchestration function contract."""
    # Mock the dependencies
    with patch('control.prepare_orchestration.build_shared') as mock_build, \
         patch('control.prepare_orchestration._find_txt_path_for_feed') as mock_find_txt, \
         patch('control.prepare_orchestration.load_shared_manifest') as mock_load_manifest, \
         patch('control.prepare_orchestration.fingerprint_index_path') as mock_fingerprint_path:
        
        # Setup mocks
        mock_build.return_value = {
            "success": True,
            "fingerprint_path": "/fake/fingerprint.json",
            "manifest_path": "/fake/manifest.json",
        }
        mock_find_txt.return_value = Path("/fake/VX.FUT.txt")
        mock_load_manifest.return_value = None  # No manifest exists
        mock_fingerprint_path.return_value = Path("/fake/fingerprint.json")
        
        # Call prepare_with_data2_enforcement with Data2 feeds
        result = prepare_with_data2_enforcement(
            season="2026Q1",
            data1_dataset_id="MNQ.FUT",
            data1_txt_path=Path("/fake/MNQ.FUT.txt"),
            data2_feeds=["VX.FUT"],
            outputs_root=Path("/fake/outputs"),
            mode="FULL",
            build_bars=True,
            build_features=True,
            tfs=[15, 30, 60, 120, 240],
        )
        
        # Verify contract
        assert "success" in result
        assert "data1_report" in result
        assert "data2_reports" in result
        assert "data2_fingerprints" in result
        assert "data2_manifest_paths" in result
        assert "no_change" in result
        
        # Since Data2 feed had no manifest, it should have been auto-built
        assert "VX.FUT" in result["data2_reports"]
        assert result["no_change"] is False  # Data2 was newly prepared


def test_prepare_orchestration_with_existing_artifacts():
    """Test prepare orchestration when Data2 already has artifacts."""
    # Mock the dependencies
    with patch('control.prepare_orchestration.build_shared') as mock_build, \
         patch('control.prepare_orchestration._find_txt_path_for_feed') as mock_find_txt, \
         patch('control.prepare_orchestration.load_shared_manifest') as mock_load_manifest, \
         patch('control.prepare_orchestration.fingerprint_index_path') as mock_fingerprint_path, \
         patch('control.prepare_orchestration.load_fingerprint_index_if_exists') as mock_load_fingerprint:
        
        # Setup mocks - Data2 already has artifacts
        mock_build.return_value = {"success": True}
        mock_find_txt.return_value = Path("/fake/VX.FUT.txt")
        mock_load_manifest.return_value = {"manifest_sha256": "abc123"}  # Manifest exists (non-None)
        
        # Create a mock Path object that returns True for exists()
        mock_path = MagicMock(spec=Path)
        mock_path.exists.return_value = True
        mock_fingerprint_path.return_value = mock_path
        
        mock_load_fingerprint.return_value = MagicMock(index_sha256="abc123")
        
        # Call prepare_with_data2_enforcement
        result = prepare_with_data2_enforcement(
            season="2026Q1",
            data1_dataset_id="MNQ.FUT",
            data1_txt_path=Path("/fake/MNQ.FUT.txt"),
            data2_feeds=["VX.FUT"],
            outputs_root=Path("/fake/outputs"),
            mode="FULL",
            build_bars=True,
            build_features=True,
            tfs=[15, 30, 60, 120, 240],
        )
        
        # Verify contract
        assert result["success"] is True
        # Data2 should not be in reports (not auto-built)
        assert "VX.FUT" not in result.get("data2_reports", {})
        # But should be in fingerprints
        assert "VX.FUT" in result.get("data2_fingerprints", {})
        assert result.get("no_change", False) is True  # No change since artifacts exist