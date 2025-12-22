
"""Governance Viewer page.

Displays governance decisions and evidence.
"""

from __future__ import annotations

import streamlit as st

from FishBroWFS_V2.gui.viewer.page_scaffold import Bundle


def render_page(bundle: Bundle) -> None:
    """
    Render Governance viewer page.
    
    Args:
        bundle: Bundle containing artifact load states
        
    Contract:
        - Never raises exceptions
        - Displays governance decisions table with lifecycle_state
    """
    try:
        st.subheader("Governance Decisions")
        
        if bundle.governance_state.status.value == "OK":
            st.info("✅ Governance data loaded successfully")
            
            # Display governance decisions table
            if bundle.governance_state.result:
                governance_data = bundle.governance_state.result.raw
                
                # Extract rows if available
                rows = governance_data.get("rows", [])
                if not rows and "items" in governance_data:
                    # Fallback to items format (backward compatibility)
                    items = governance_data.get("items", [])
                    rows = items
                
                if rows:
                    # Display table
                    import pandas as pd
                    
                    table_data = []
                    for row in rows:
                        table_data.append({
                            "Strategy ID": row.get("strategy_id", "N/A"),
                            "Decision": row.get("decision", "N/A"),
                            "Rule ID": row.get("rule_id", "N/A"),
                            "Lifecycle State": row.get("lifecycle_state", "INCUBATION"),  # Default for backward compatibility
                            "Reason": row.get("reason", ""),
                            "Run ID": row.get("run_id", "N/A"),
                            "Stage": row.get("stage", "N/A"),
                        })
                    
                    df = pd.DataFrame(table_data)
                    st.dataframe(df, use_container_width=True)
                else:
                    st.info("No governance decisions found.")
        else:
            st.warning(f"⚠️ Governance status: {bundle.governance_state.status.value}")
            if bundle.governance_state.error:
                st.error(f"Error: {bundle.governance_state.error}")
    
    except Exception as e:
        st.error(f"Error rendering governance page: {e}")


