
"""Streamlit Viewer entrypoint (official).

This is the single source of truth for launching the B5 Viewer.
"""

from __future__ import annotations

import os
from pathlib import Path

import streamlit as st

from FishBroWFS_V2.gui.viewer.page_scaffold import render_viewer_page
from FishBroWFS_V2.gui.viewer.pages.kpi import render_page as render_kpi_page
from FishBroWFS_V2.gui.viewer.pages.overview import render_page as render_overview_page
from FishBroWFS_V2.gui.viewer.pages.winners import render_page as render_winners_page
from FishBroWFS_V2.gui.viewer.pages.governance import render_page as render_governance_page
from FishBroWFS_V2.gui.viewer.pages.artifacts import render_page as render_artifacts_page
from FishBroWFS_V2.gui.research.page import render as render_research_page

# Use HTTP-based UI Bridge for Zero-Violation Split-Brain Architecture
from FishBroWFS_V2.gui.adapters.ui_bridge import migrate_ui_imports

# Migrate imports to use HTTP bridge
migrate_ui_imports()

# The migrate_ui_imports() function provides get_paths() which returns the paths module
# We can use get_paths().get_outputs_root() instead of direct import


def get_run_dir_from_query() -> Path | None:
    """
    Get run_dir from query parameters.
    
    Returns:
        Path to run directory if season and run_id are provided, None otherwise
    """
    season = st.query_params.get("season", "")
    run_id = st.query_params.get("run_id", "")
    
    if not season or not run_id:
        return None
    
    # Get outputs root from environment or default
    outputs_root_str = os.getenv("FISHBRO_OUTPUTS_ROOT", "outputs")
    outputs_root = Path(outputs_root_str)
    run_dir = outputs_root / "seasons" / season / "runs" / run_id
    
    return run_dir


def main() -> None:
    """Main Viewer entrypoint."""
    st.set_page_config(
        page_title="FishBroWFS B5 Viewer",
        layout="wide",
    )
    
    # Mode selection: Viewer or Research Console
    mode = st.sidebar.radio(
        "Mode",
        ["Viewer", "Research Console"],
        index=0,
    )
    
    if mode == "Research Console":
        # Research Console mode - doesn't need query parameters
        outputs_root_str = os.getenv("FISHBRO_OUTPUTS_ROOT", "outputs")
        outputs_root = Path(outputs_root_str)

        # Show Research Console
        render_research_page(outputs_root)
        return

    # Viewer mode - requires query parameters
    # Get run_dir from query params
    run_dir = get_run_dir_from_query()
    
    if not run_dir:
        st.error("Missing query parameters: season and run_id required")
        st.info("Usage: /?season=...&run_id=...")
        st.info("Example: /?season=2026Q1&run_id=demo_20250101T000000Z")
        return
    
    if not run_dir.exists():
        st.error(f"Run directory does not exist: {run_dir}")
        st.info(f"Outputs root: {run_dir.parent.parent.parent}")
        st.info(f"Expected path: {run_dir}")
        return

    # Page selection for Viewer mode
    page = st.sidebar.selectbox(
        "Viewer Pages",
        [
            "Overview",
            "KPI",
            "Winners",
            "Governance",
            "Artifacts",
        ],
    )
    
    # Render selected page
    if page == "Overview":
        render_viewer_page("Overview", run_dir, render_overview_page)
    elif page == "KPI":
        render_viewer_page("KPI", run_dir, render_kpi_page)
    elif page == "Winners":
        render_viewer_page("Winners", run_dir, render_winners_page)
    elif page == "Governance":
        render_viewer_page("Governance", run_dir, render_governance_page)
    elif page == "Artifacts":
        render_viewer_page("Artifacts", run_dir, render_artifacts_page)


if __name__ == "__main__":
    main()



