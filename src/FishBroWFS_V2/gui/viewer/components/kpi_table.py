"""KPI Table component with evidence drill-down.

Renders KPI table with clickable evidence links.
"""

from __future__ import annotations

from typing import Any

import streamlit as st

from FishBroWFS_V2.gui.viewer.kpi_registry import get_evidence_link


def render_kpi_table(kpi_rows: list[dict]) -> None:
    """
    Render KPI table with evidence drill-down capability.
    
    Each row must include:
      - name: str - KPI name
      - value: Any - KPI value (will be converted to string for display)
    
    Optional:
      - label: str - Display label (defaults to name)
      - format: str - Value format hint
    
    Args:
        kpi_rows: List of KPI row dictionaries
        
    Contract:
        - Never raises exceptions
        - KPI names not in registry are displayed but not clickable
        - Missing name/value fields are handled gracefully
    """
    try:
        if not kpi_rows:
            st.info("No KPI data available.")
            return
        
        st.subheader("Key Performance Indicators")
        
        # Render table
        for row in kpi_rows:
            _render_kpi_row(row)
    
    except Exception as e:
        st.error(f"Error rendering KPI table: {e}")


def _render_kpi_row(row: dict) -> None:
    """Render single KPI row."""
    try:
        # Extract row data safely
        kpi_name = row.get("name", "unknown")
        kpi_value = row.get("value", None)
        kpi_label = row.get("label", kpi_name)
        
        # Format value
        value_str = _format_value(kpi_value)
        
        # Check if KPI has evidence link
        evidence_link = get_evidence_link(kpi_name)
        
        if evidence_link:
            # Render with clickable evidence link
            col1, col2, col3 = st.columns([3, 2, 1])
            with col1:
                st.markdown(f"**{kpi_label}**")
            with col2:
                st.text(value_str)
            with col3:
                if st.button("🔍 View Evidence", key=f"evidence_{kpi_name}"):
                    # Store evidence link in session state
                    st.session_state["active_evidence"] = {
                        "kpi_name": kpi_name,
                        "artifact": evidence_link.artifact,
                        "json_pointer": evidence_link.json_pointer,
                        "description": evidence_link.description or "",
                    }
                    st.rerun()
        else:
            # Render without evidence link
            col1, col2 = st.columns([3, 2])
            with col1:
                st.markdown(f"**{kpi_label}**")
            with col2:
                st.text(value_str)
    
    except Exception:
        # Silently handle errors in row rendering
        pass


def _format_value(value: Any) -> str:
    """Format KPI value for display."""
    try:
        if value is None:
            return "N/A"
        if isinstance(value, (int, float)):
            # Format numbers with appropriate precision
            if isinstance(value, float):
                return f"{value:,.2f}"
            return f"{value:,}"
        return str(value)
    except Exception:
        return str(value) if value is not None else "N/A"
