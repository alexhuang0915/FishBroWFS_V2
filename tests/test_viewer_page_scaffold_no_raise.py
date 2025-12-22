
"""Tests for Viewer page scaffold - no raise contract.

Tests that render_viewer_page() never raises exceptions.
Uses monkeypatch to simulate MISSING/INVALID scenarios.

NOTE: This test is skipped because streamlit has been removed from the project.
"""

from __future__ import annotations

import pytest

pytest.skip("Streamlit tests skipped - streamlit removed from project", allow_module_level=True)

# Original test code below is not executed


def test_load_bundle_missing_manifest() -> None:
    """Test _load_bundle with missing manifest."""
    run_dir = Path("/test/run")
    
    with patch("FishBroWFS_V2.gui.viewer.page_scaffold.try_read_artifact") as mock_read:
        # Mock manifest as MISSING using try_read_artifact behavior
        missing_result = try_read_artifact(Path("/nonexistent/file.json"))
        assert missing_result.is_error
        
        mock_read.side_effect = [
            missing_result,  # manifest MISSING
            SafeReadResult(),  # winners (not used in this test)
            SafeReadResult(),  # governance (not used in this test)
        ]
        
        # Should not raise
        bundle = _load_bundle(run_dir)
        
        assert bundle.manifest_state.status.value == "MISSING"


def test_load_bundle_invalid_winners() -> None:
    """Test _load_bundle with invalid winners."""
    run_dir = Path("/test/run")
    
    with patch("FishBroWFS_V2.gui.viewer.page_scaffold.try_read_artifact") as mock_read, \
         patch("FishBroWFS_V2.gui.viewer.page_scaffold.validate_winners_v2_status") as mock_validate:
        
        # Mock winners read succeeds but validation fails
        ok_result = SafeReadResult(
            result=Mock(
                raw={"config_hash": "test"},
                meta=Mock(mtime_s=1234567890.0),
            ),
        )
        assert ok_result.is_ok
        
        mock_read.side_effect = [
            SafeReadResult(),  # manifest
            ok_result,  # winners read succeeds
            SafeReadResult(),  # governance
        ]
        
        mock_validate.return_value = ValidationResult(
            status=ArtifactStatus.INVALID,
            message="winners_v2.json 缺少欄位: config_hash",
            error_details="Field required: config_hash",
        )
        
        # Should not raise
        bundle = _load_bundle(run_dir)
        
        assert bundle.winners_v2_state.status.value == "INVALID"
        assert bundle.winners_v2_state.error is not None


def test_load_bundle_validation_exception_handled() -> None:
    """Test that validation exceptions are caught and handled."""
    run_dir = Path("/test/run")
    
    with patch("FishBroWFS_V2.gui.viewer.page_scaffold.try_read_artifact") as mock_read, \
         patch("FishBroWFS_V2.gui.viewer.page_scaffold.validate_manifest_status") as mock_validate:
        
        ok_result = SafeReadResult(
            result=Mock(
                raw={"run_id": "test"},
                meta=Mock(mtime_s=1234567890.0),
            ),
        )
        
        mock_read.side_effect = [
            ok_result,  # manifest read succeeds
            SafeReadResult(),  # winners
            SafeReadResult(),  # governance
        ]
        
        # Mock validation to raise exception
        mock_validate.side_effect = Exception("Validation error")
        
        # Should not raise - exception is caught
        bundle = _load_bundle(run_dir)
        
        # Should still have a state (computed from read_result only)
        assert bundle.manifest_state is not None


def test_render_viewer_page_no_raise_missing_artifacts() -> None:
    """Test render_viewer_page does not raise when artifacts are missing."""
    run_dir = Path("/test/run")
    
    with patch("FishBroWFS_V2.gui.viewer.page_scaffold._load_bundle") as mock_load:
        # Mock bundle with MISSING artifacts
        mock_load.return_value = Bundle(
            manifest_state=ArtifactLoadState(
                status=ArtifactLoadStatus.MISSING,
                artifact_name="manifest",
                path=Path("/test/manifest.json"),
            ),
            winners_v2_state=ArtifactLoadState(
                status=ArtifactLoadStatus.OK,
                artifact_name="winners_v2",
                path=Path("/test/winners.json"),
            ),
            governance_state=ArtifactLoadState(
                status=ArtifactLoadStatus.OK,
                artifact_name="governance",
                path=Path("/test/governance.json"),
            ),
        )
        
        # Mock streamlit functions
        with patch("streamlit.set_page_config"), \
             patch("streamlit.title"), \
             patch("FishBroWFS_V2.gui.viewer.components.status_bar.render_artifact_status_bar"), \
             patch("streamlit.error"), \
             patch("streamlit.info"):
            
            # Should not raise
            render_viewer_page("Test Page", run_dir)
            
            # Verify BLOCKED message was shown
            # (We can't easily test streamlit calls, but we verify no exception)


def test_render_viewer_page_no_raise_content_renderer_exception() -> None:
    """Test render_viewer_page handles content_renderer exceptions."""
    run_dir = Path("/test/run")
    
    def failing_content_renderer(bundle: Bundle) -> None:
        raise ValueError("Content renderer failed")
    
    with patch("FishBroWFS_V2.gui.viewer.page_scaffold._load_bundle") as mock_load:
        # Mock bundle with OK artifacts
        mock_load.return_value = Bundle(
            manifest_state=ArtifactLoadState(
                status=ArtifactLoadStatus.OK,
                artifact_name="manifest",
                path=Path("/test/manifest.json"),
            ),
            winners_v2_state=ArtifactLoadState(
                status=ArtifactLoadStatus.OK,
                artifact_name="winners_v2",
                path=Path("/test/winners.json"),
            ),
            governance_state=ArtifactLoadState(
                status=ArtifactLoadStatus.OK,
                artifact_name="governance",
                path=Path("/test/governance.json"),
            ),
        )
        
        # Mock streamlit functions
        with patch("streamlit.set_page_config"), \
             patch("streamlit.title"), \
             patch("FishBroWFS_V2.gui.viewer.components.status_bar.render_artifact_status_bar"), \
             patch("streamlit.error"), \
             patch("streamlit.exception"):
            
            # Should not raise - exception is caught
            render_viewer_page("Test Page", run_dir, content_render_fn=failing_content_renderer)
            
            # Verify error was shown (via streamlit.error call)


def test_bundle_has_blocking_error() -> None:
    """Test Bundle.has_blocking_error property."""
    # MISSING blocks
    bundle1 = Bundle(
        manifest_state=ArtifactLoadState(
            status=ArtifactLoadStatus.MISSING,
            artifact_name="manifest",
            path=Path("/test/manifest.json"),
        ),
        winners_v2_state=ArtifactLoadState(
            status=ArtifactLoadStatus.OK,
            artifact_name="winners_v2",
            path=Path("/test/winners.json"),
        ),
        governance_state=ArtifactLoadState(
            status=ArtifactLoadStatus.OK,
            artifact_name="governance",
            path=Path("/test/governance.json"),
        ),
    )
    assert bundle1.has_blocking_error is True
    
    # INVALID blocks
    bundle2 = Bundle(
        manifest_state=ArtifactLoadState(
            status=ArtifactLoadStatus.OK,
            artifact_name="manifest",
            path=Path("/test/manifest.json"),
        ),
        winners_v2_state=ArtifactLoadState(
            status=ArtifactLoadStatus.INVALID,
            artifact_name="winners_v2",
            path=Path("/test/winners.json"),
            error="Test error",
        ),
        governance_state=ArtifactLoadState(
            status=ArtifactLoadStatus.OK,
            artifact_name="governance",
            path=Path("/test/governance.json"),
        ),
    )
    assert bundle2.has_blocking_error is True
    
    # DIRTY does not block
    bundle3 = Bundle(
        manifest_state=ArtifactLoadState(
            status=ArtifactLoadStatus.OK,
            artifact_name="manifest",
            path=Path("/test/manifest.json"),
        ),
        winners_v2_state=ArtifactLoadState(
            status=ArtifactLoadStatus.DIRTY,
            artifact_name="winners_v2",
            path=Path("/test/winners.json"),
            dirty_reasons=["config_hash mismatch"],
        ),
        governance_state=ArtifactLoadState(
            status=ArtifactLoadStatus.OK,
            artifact_name="governance",
            path=Path("/test/governance.json"),
        ),
    )
    assert bundle3.has_blocking_error is False
    
    # All OK does not block
    bundle4 = Bundle(
        manifest_state=ArtifactLoadState(
            status=ArtifactLoadStatus.OK,
            artifact_name="manifest",
            path=Path("/test/manifest.json"),
        ),
        winners_v2_state=ArtifactLoadState(
            status=ArtifactLoadStatus.OK,
            artifact_name="winners_v2",
            path=Path("/test/winners.json"),
        ),
        governance_state=ArtifactLoadState(
            status=ArtifactLoadStatus.OK,
            artifact_name="governance",
            path=Path("/test/governance.json"),
        ),
    )
    assert bundle4.has_blocking_error is False


def test_bundle_all_ok() -> None:
    """Test Bundle.all_ok property."""
    # All OK
    bundle1 = Bundle(
        manifest_state=ArtifactLoadState(
            status=ArtifactLoadStatus.OK,
            artifact_name="manifest",
            path=Path("/test/manifest.json"),
        ),
        winners_v2_state=ArtifactLoadState(
            status=ArtifactLoadStatus.OK,
            artifact_name="winners_v2",
            path=Path("/test/winners.json"),
        ),
        governance_state=ArtifactLoadState(
            status=ArtifactLoadStatus.OK,
            artifact_name="governance",
            path=Path("/test/governance.json"),
        ),
    )
    assert bundle1.all_ok is True
    
    # One DIRTY
    bundle2 = Bundle(
        manifest_state=ArtifactLoadState(
            status=ArtifactLoadStatus.OK,
            artifact_name="manifest",
            path=Path("/test/manifest.json"),
        ),
        winners_v2_state=ArtifactLoadState(
            status=ArtifactLoadStatus.DIRTY,
            artifact_name="winners_v2",
            path=Path("/test/winners.json"),
            dirty_reasons=["config_hash mismatch"],
        ),
        governance_state=ArtifactLoadState(
            status=ArtifactLoadStatus.OK,
            artifact_name="governance",
            path=Path("/test/governance.json"),
        ),
    )
    assert bundle2.all_ok is False
    
    # One MISSING
    bundle3 = Bundle(
        manifest_state=ArtifactLoadState(
            status=ArtifactLoadStatus.MISSING,
            artifact_name="manifest",
            path=Path("/test/manifest.json"),
        ),
        winners_v2_state=ArtifactLoadState(
            status=ArtifactLoadStatus.OK,
            artifact_name="winners_v2",
            path=Path("/test/winners.json"),
        ),
        governance_state=ArtifactLoadState(
            status=ArtifactLoadStatus.OK,
            artifact_name="governance",
            path=Path("/test/governance.json"),
        ),
    )
    assert bundle3.all_ok is False


