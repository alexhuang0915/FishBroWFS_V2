"""Artifact Status Bar component for Viewer pages.

Renders consistent status bar across all Viewer pages.
Never raises exceptions - graceful degradation.
"""

from __future__ import annotations

import streamlit as st

from FishBroWFS_V2.gui.viewer.load_state import ArtifactLoadState, ArtifactLoadStatus


def render_artifact_status_bar(states: list[ArtifactLoadState]) -> None:
    """
    Render artifact status bar for Viewer page.
    
    Displays status badges for each artifact with error/dirty information.
    Never raises exceptions - page continues to render even if artifacts are missing/invalid.
    
    Args:
        states: List of ArtifactLoadState for each artifact
        
    Contract:
        - Never raises exceptions
        - Always renders something (even if states is empty)
        - INVALID shows error summary (max 1 line)
        - DIRTY shows dirty_reasons (collapsible expander)
        - Page continues to render even if artifacts are MISSING/INVALID
    """
    if not states:
        return
    
    st.subheader("Artifact Status")
    
    # Create columns for badges
    num_cols = min(len(states), 4)  # Max 4 columns
    cols = st.columns(num_cols)
    
    for idx, state in enumerate(states):
        col_idx = idx % num_cols
        with cols[col_idx]:
            _render_artifact_badge(state)
    
    # Show detailed error/dirty info below badges
    _render_detailed_info(states)


def _render_artifact_badge(state: ArtifactLoadState) -> None:
    """Render single artifact badge."""
    # Map status to badge color
    if state.status == ArtifactLoadStatus.OK:
        badge_color = "🟢"
        badge_text = f"{state.artifact_name}: OK"
    elif state.status == ArtifactLoadStatus.MISSING:
        badge_color = "⚪"
        badge_text = f"{state.artifact_name}: MISSING"
    elif state.status == ArtifactLoadStatus.INVALID:
        badge_color = "🔴"
        badge_text = f"{state.artifact_name}: INVALID"
    elif state.status == ArtifactLoadStatus.DIRTY:
        badge_color = "🟡"
        badge_text = f"{state.artifact_name}: DIRTY"
    else:
        badge_color = "⚪"
        badge_text = f"{state.artifact_name}: UNKNOWN"
    
    st.markdown(f"{badge_color} **{badge_text}**")
    
    # Show last modified time if available
    if state.last_modified_ts is not None:
        from datetime import datetime
        dt = datetime.fromtimestamp(state.last_modified_ts)
        st.caption(f"Updated: {dt.strftime('%Y-%m-%d %H:%M:%S')}")


def _render_detailed_info(states: list[ArtifactLoadState]) -> None:
    """Render detailed error/dirty information."""
    invalid_states = [s for s in states if s.status == ArtifactLoadStatus.INVALID]
    dirty_states = [s for s in states if s.status == ArtifactLoadStatus.DIRTY]
    
    if not invalid_states and not dirty_states:
        return
    
    # Show INVALID errors
    if invalid_states:
        st.error("**Invalid Artifacts:**")
        for state in invalid_states:
            error_summary = state.error or "Unknown error"
            # Truncate to 1 line if too long
            if len(error_summary) > 100:
                error_summary = error_summary[:97] + "..."
            st.text(f"• {state.artifact_name}: {error_summary}")
    
    # Show DIRTY reasons (collapsible)
    if dirty_states:
        with st.expander("**Dirty Artifacts (config_hash mismatch)**", expanded=False):
            for state in dirty_states:
                st.markdown(f"**{state.artifact_name}:**")
                if state.dirty_reasons:
                    for reason in state.dirty_reasons:
                        st.text(f"  • {reason}")
                else:
                    st.text("  • No specific reason provided")
                st.markdown("---")
