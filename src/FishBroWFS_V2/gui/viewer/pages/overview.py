
"""Overview Viewer page.

Displays run overview and summary information.
"""

from __future__ import annotations

import streamlit as st

from FishBroWFS_V2.gui.viewer.page_scaffold import Bundle


def render_page(bundle: Bundle) -> None:
    """
    Render Overview viewer page.
    
    Args:
        bundle: Bundle containing artifact load states
        
    Contract:
        - Never raises exceptions
        - Displays run overview and summary
    """
    try:
        st.subheader("Run Overview")
        
        # Display manifest info if available
        if bundle.manifest_state.status.value == "OK":
            st.info("✅ Manifest loaded successfully")
        else:
            st.warning(f"⚠️ Manifest status: {bundle.manifest_state.status.value}")
        
        # Display summary stats
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.metric("Manifest", bundle.manifest_state.status.value)
        with col2:
            st.metric("Winners", bundle.winners_v2_state.status.value)
        with col3:
            st.metric("Governance", bundle.governance_state.status.value)
    
    except Exception as e:
        st.error(f"Error rendering overview page: {e}")


