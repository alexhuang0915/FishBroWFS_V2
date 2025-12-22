
"""Tests for KPI drill-down - no raise contract.

Tests missing artifacts, wrong pointers, empty session_state.
UI functions should never raise exceptions.

Zero-side-effect imports: All I/O and stateful operations are inside test functions.

NOTE: This test is skipped because streamlit has been removed from the project.
"""

from __future__ import annotations

import pytest

pytest.skip("Streamlit tests skipped - streamlit removed from project", allow_module_level=True)

# Original test code below is not executed


def test_kpi_table_missing_name() -> None:
    """Test KPI table handles missing name field."""
    # Import inside test function to prevent collection errors
    from FishBroWFS_V2.gui.viewer.components.kpi_table import render_kpi_table
    
    with patch("streamlit.subheader"), \
         patch("streamlit.columns"), \
         patch("streamlit.markdown"), \
         patch("streamlit.text"), \
         patch("streamlit.button"):
        
        # Row without name
        kpi_rows = [
            {"value": 100}
        ]
        
        # Should not raise
        render_kpi_table(kpi_rows)


def test_kpi_table_missing_value() -> None:
    """Test KPI table handles missing value field."""
    # Import inside test function to prevent collection errors
    from FishBroWFS_V2.gui.viewer.components.kpi_table import render_kpi_table
    
    with patch("streamlit.subheader"), \
         patch("streamlit.columns"), \
         patch("streamlit.markdown"), \
         patch("streamlit.text"), \
         patch("streamlit.button"):
        
        # Row without value
        kpi_rows = [
            {"name": "net_profit"}
        ]
        
        # Should not raise
        render_kpi_table(kpi_rows)


def test_kpi_table_empty_rows() -> None:
    """Test KPI table handles empty rows list."""
    # Import inside test function to prevent collection errors
    from FishBroWFS_V2.gui.viewer.components.kpi_table import render_kpi_table
    
    with patch("streamlit.info"):
        # Empty list
        render_kpi_table([])
        
        # Should not raise


def test_kpi_table_unknown_kpi() -> None:
    """Test KPI table handles unknown KPI (not in registry)."""
    # Import inside test function to prevent collection errors
    from FishBroWFS_V2.gui.viewer.components.kpi_table import render_kpi_table
    
    with patch("streamlit.subheader"), \
         patch("streamlit.columns"), \
         patch("streamlit.markdown"), \
         patch("streamlit.text"), \
         patch("streamlit.button"):
        
        # KPI not in registry
        kpi_rows = [
            {"name": "unknown_kpi", "value": 100}
        ]
        
        # Should not raise - displays but not clickable
        render_kpi_table(kpi_rows)


def test_evidence_panel_missing_artifact() -> None:
    """Test evidence panel handles missing artifact."""
    # Import inside test function to prevent collection errors
    from FishBroWFS_V2.gui.viewer.components.evidence_panel import render_evidence_panel
    
    with patch("streamlit.subheader"), \
         patch("streamlit.markdown"), \
         patch("streamlit.warning"), \
         patch("streamlit.caption"):
        
        # Mock session state with missing artifact
        with patch.dict(st.session_state, {
            "active_evidence": {
                "kpi_name": "net_profit",
                "artifact": "winners_v2",
                "json_pointer": "/summary/net_profit",
            }
        }):
            # Artifacts dict missing winners_v2
            artifacts = {
                "manifest": {},
            }
            
            # Should not raise - shows warning
            render_evidence_panel(artifacts)


def test_evidence_panel_wrong_pointer() -> None:
    """Test evidence panel handles wrong JSON pointer."""
    # Import inside test function to prevent collection errors
    from FishBroWFS_V2.gui.viewer.components.evidence_panel import render_evidence_panel
    
    with patch("streamlit.subheader"), \
         patch("streamlit.markdown"), \
         patch("streamlit.warning"), \
         patch("streamlit.info"), \
         patch("streamlit.caption"):
        
        # Mock session state
        with patch.dict(st.session_state, {
            "active_evidence": {
                "kpi_name": "net_profit",
                "artifact": "winners_v2",
                "json_pointer": "/nonexistent/pointer",
            }
        }):
            # Artifact exists but pointer is wrong
            artifacts = {
                "winners_v2": {
                    "summary": {
                        "net_profit": 100
                    }
                }
            }
            
            # Should not raise - shows warning
            render_evidence_panel(artifacts)


def test_evidence_panel_empty_session_state() -> None:
    """Test evidence panel handles empty session_state."""
    # Import inside test function to prevent collection errors
    from FishBroWFS_V2.gui.viewer.components.evidence_panel import render_evidence_panel
    
    with patch("streamlit.subheader"):
        # Empty session state
        with patch.dict(st.session_state, {}, clear=True):
            artifacts = {
                "winners_v2": {}
            }
            
            # Should not raise - returns early
            render_evidence_panel(artifacts)


def test_evidence_panel_invalid_session_state() -> None:
    """Test evidence panel handles invalid session_state structure."""
    # Import inside test function to prevent collection errors
    from FishBroWFS_V2.gui.viewer.components.evidence_panel import render_evidence_panel
    
    with patch("streamlit.subheader"), \
         patch("streamlit.markdown"), \
         patch("streamlit.warning"):
        
        # Invalid session state structure
        with patch.dict(st.session_state, {
            "active_evidence": "not_a_dict"
        }):
            artifacts = {}
            
            # Should not raise - handles gracefully
            render_evidence_panel(artifacts)


def test_evidence_panel_missing_fields() -> None:
    """Test evidence panel handles missing fields in session_state."""
    # Import inside test function to prevent collection errors
    from FishBroWFS_V2.gui.viewer.components.evidence_panel import render_evidence_panel
    
    with patch("streamlit.subheader"), \
         patch("streamlit.markdown"), \
         patch("streamlit.warning"):
        
        # Missing fields in active_evidence
        with patch.dict(st.session_state, {
            "active_evidence": {
                "kpi_name": "net_profit",
                # Missing artifact, json_pointer
            }
        }):
            artifacts = {}
            
            # Should not raise - handles gracefully
            render_evidence_panel(artifacts)


def test_kpi_table_exception_handling() -> None:
    """Test KPI table handles exceptions gracefully."""
    # Import inside test function to prevent collection errors
    from FishBroWFS_V2.gui.viewer.components.kpi_table import render_kpi_table
    
    # Mock streamlit to raise exception
    with patch("streamlit.subheader", side_effect=Exception("Streamlit error")):
        kpi_rows = [
            {"name": "net_profit", "value": 100}
        ]
        
        # Should catch exception and show error
        with patch("streamlit.error"):
            render_kpi_table(kpi_rows)
            # Should not raise


def test_evidence_panel_exception_handling() -> None:
    """Test evidence panel handles exceptions gracefully."""
    # Import inside test function to prevent collection errors
    from FishBroWFS_V2.gui.viewer.components.evidence_panel import render_evidence_panel
    
    # Mock streamlit to raise exception
    with patch("streamlit.subheader", side_effect=Exception("Streamlit error")):
        artifacts = {}
        
        # Should catch exception and show error
        with patch("streamlit.error"):
            render_evidence_panel(artifacts)
            # Should not raise


