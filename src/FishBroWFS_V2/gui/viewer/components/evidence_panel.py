
"""Evidence Panel component.

Displays evidence for active KPI from artifacts.
"""

from __future__ import annotations

import json

import streamlit as st

from FishBroWFS_V2.gui.viewer.json_pointer import resolve_json_pointer


def render_evidence_panel(artifacts: dict[str, dict]) -> None:
    """
    Render evidence panel showing active KPI evidence.
    
    Args:
        artifacts: Dictionary mapping artifact names to their JSON data
                  e.g., {"manifest": {...}, "winners_v2": {...}, "governance": {...}}
        
    Contract:
        - Never raises exceptions
        - Shows warning if evidence is missing
        - Handles missing session_state gracefully
        - Unknown render_hint falls back to "highlight" (never raises)
    """
    try:
        # Get active evidence from session state
        active_evidence = st.session_state.get("active_evidence", None)
        
        if not active_evidence:
            # No active evidence selected
            return
        
        st.subheader("Evidence")
        
        # Extract evidence info safely
        kpi_name = active_evidence.get("kpi_name", "unknown")
        artifact_name = active_evidence.get("artifact", "unknown")
        json_pointer = active_evidence.get("json_pointer", "")
        description = active_evidence.get("description", "")
        
        # Extract render_hint with allowlist check and warning
        render_hint = active_evidence.get("render_hint", "highlight")
        allowed_hints = {"highlight", "chart_annotation", "diff"}
        if render_hint not in allowed_hints:
            st.warning(f"Unsupported render_hint={render_hint}, fallback to highlight")
            render_hint = "highlight"  # Fallback for unknown hints
        
        render_payload = active_evidence.get("render_payload", {})
        
        # Display KPI info
        st.markdown(f"**KPI:** {kpi_name}")
        if description:
            st.caption(description)
        
        st.markdown("---")
        
        # Get artifact data
        artifact_data = artifacts.get(artifact_name)
        
        if artifact_data is None:
            st.warning(f"⚠️ Artifact '{artifact_name}' not available.")
            return
        
        # Resolve JSON pointer
        found, value = resolve_json_pointer(artifact_data, json_pointer)
        
        if not found:
            st.warning("⚠️ Evidence missing: JSON pointer not found.")
            st.info(f"**Artifact:** {artifact_name}")
            st.info(f"**JSON Pointer:** `{json_pointer}`")
            return
        
        # Display evidence based on render_hint
        st.markdown(f"**Artifact:** `{artifact_name}`")
        st.markdown(f"**JSON Pointer:** `{json_pointer}`")
        
        if render_hint == "chart_annotation":
            # Chart annotation mode: show compact preview for chart overlays
            st.markdown("**Value:**")
            st.caption(f"({render_hint} mode)")
            st.code(str(value)[:100] + "..." if len(str(value)) > 100 else str(value), language=None)
        elif render_hint == "diff":
            # Diff mode: show full details with diff highlighting
            st.markdown("**Value:**")
            st.caption(f"({render_hint} mode)")
            if isinstance(value, (dict, list)):
                st.json(value)
            else:
                st.code(str(value), language=None)
        else:
            # Default "highlight" mode
            st.markdown("**Value:**")
            try:
                if isinstance(value, (dict, list)):
                    st.json(value)
                else:
                    st.code(str(value), language=None)
            except Exception:
                st.text(str(value))
    
    except Exception as e:
        st.error(f"Error rendering evidence panel: {e}")


