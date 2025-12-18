"""Winners Viewer page.

Displays winners list and details.
"""

from __future__ import annotations

import streamlit as st

from FishBroWFS_V2.gui.viewer.page_scaffold import Bundle


def render_page(bundle: Bundle) -> None:
    """
    Render Winners viewer page.
    
    Args:
        bundle: Bundle containing artifact load states
        
    Contract:
        - Never raises exceptions
        - Displays winners list
    """
    try:
        st.subheader("Winners")
        
        if bundle.winners_v2_state.status.value == "OK":
            st.info("✅ Winners data loaded successfully")
            # TODO: Phase 6.2 - Display winners table
            st.info("Winners table display coming in Phase 6.2")
        else:
            st.warning(f"⚠️ Winners status: {bundle.winners_v2_state.status.value}")
            if bundle.winners_v2_state.error:
                st.error(f"Error: {bundle.winners_v2_state.error}")
    
    except Exception as e:
        st.error(f"Error rendering winners page: {e}")
