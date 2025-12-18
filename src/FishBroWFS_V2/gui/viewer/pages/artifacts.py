"""Artifacts Viewer page.

Displays raw artifacts JSON.
"""

from __future__ import annotations

import streamlit as st

from FishBroWFS_V2.gui.viewer.page_scaffold import Bundle
from FishBroWFS_V2.core.artifact_reader import try_read_artifact


def render_page(bundle: Bundle) -> None:
    """
    Render Artifacts viewer page.
    
    Args:
        bundle: Bundle containing artifact load states
        
    Contract:
        - Never raises exceptions
        - Displays raw artifacts JSON
    """
    try:
        st.subheader("Raw Artifacts")
        
        # Display manifest
        if bundle.manifest_state.status.value == "OK" and bundle.manifest_state.path:
            st.markdown("### manifest.json")
            manifest_read = try_read_artifact(bundle.manifest_state.path)
            if manifest_read.is_ok and manifest_read.result:
                st.json(manifest_read.result.raw)
        
        # Display winners_v2
        if bundle.winners_v2_state.status.value == "OK" and bundle.winners_v2_state.path:
            st.markdown("### winners_v2.json")
            winners_read = try_read_artifact(bundle.winners_v2_state.path)
            if winners_read.is_ok and winners_read.result:
                st.json(winners_read.result.raw)
        
        # Display governance
        if bundle.governance_state.status.value == "OK" and bundle.governance_state.path:
            st.markdown("### governance.json")
            governance_read = try_read_artifact(bundle.governance_state.path)
            if governance_read.is_ok and governance_read.result:
                st.json(governance_read.result.raw)
    
    except Exception as e:
        st.error(f"Error rendering artifacts page: {e}")
