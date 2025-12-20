"""Research Console Page Module.

Phase 10: Read-only Research UI + Decision Input.
This is NOT a standalone Streamlit entrypoint - it must be called from the official viewer.
"""

from __future__ import annotations

import streamlit as st
from datetime import datetime
from pathlib import Path
from typing import Any

from FishBroWFS_V2.gui.research_console import (
    load_research_artifacts,
    summarize_index,
    apply_filters,
    load_run_detail,
    submit_decision,
    get_unique_values,
)


def render(outputs_root: Path) -> None:
    """Render the Research Console page.
    
    This function is called from the official viewer entrypoint.
    It does NOT contain main() or __name__ guard to avoid being detected as a duplicate entrypoint.
    """
    # Initialize session state
    if "selected_run_id" not in st.session_state:
        st.session_state.selected_run_id = None
    if "last_refresh" not in st.session_state:
        st.session_state.last_refresh = datetime.now().timestamp()
    
    # Title and header
    st.title("📊 Research Console")
    
    # Configuration
    research_dir = outputs_root / "research"
    
    # Check if research artifacts exist
    try:
        artifacts = load_research_artifacts(outputs_root)
    except FileNotFoundError as e:
        st.error(f"Research artifacts not found: {e}")
        st.info("Please run research index generation first.")
        return
    
    # Header information
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Outputs Root", str(outputs_root))
    with col2:
        index_mtime = datetime.fromtimestamp(artifacts["index_mtime"])
        st.metric("Index Last Updated", index_mtime.strftime("%Y-%m-%d %H:%M:%S"))
    with col3:
        total_runs = artifacts["index"].get("total_runs", 0)
        st.metric("Total Runs", total_runs)
    
    # Load and summarize index
    index_data = artifacts["index"]
    all_rows = summarize_index(index_data)
    
    # Calculate KPI counts
    decisions = [row.get("decision", "UNDECIDED") for row in all_rows]
    keep_count = decisions.count("KEEP")
    drop_count = decisions.count("DROP")
    archive_count = decisions.count("ARCHIVE")
    undecided_count = decisions.count("UNDECIDED")
    
    # KPI Cards
    st.subheader("📈 Research Overview")
    kpi_col1, kpi_col2, kpi_col3, kpi_col4 = st.columns(4)
    with kpi_col1:
        st.metric("KEEP", keep_count)
    with kpi_col2:
        st.metric("DROP", drop_count)
    with kpi_col3:
        st.metric("ARCHIVE", archive_count)
    with kpi_col4:
        st.metric("UNDECIDED", undecided_count)
    
    # Filters section
    st.subheader("🔍 Filters")
    
    # Get unique values for dropdowns
    unique_symbols = get_unique_values(all_rows, "symbol")
    unique_strategies = get_unique_values(all_rows, "strategy_id")
    
    # Create filter columns
    filter_col1, filter_col2, filter_col3, filter_col4 = st.columns(4)
    
    with filter_col1:
        text_filter = st.text_input("Search (run_id/symbol/strategy)", "")
    
    with filter_col2:
        symbol_filter = st.selectbox(
            "Symbol",
            options=["ALL"] + unique_symbols,
            index=0,
        )
        if symbol_filter == "ALL":
            symbol_filter = None
    
    with filter_col3:
        strategy_filter = st.selectbox(
            "Strategy",
            options=["ALL"] + unique_strategies,
            index=0,
        )
        if strategy_filter == "ALL":
            strategy_filter = None
    
    with filter_col4:
        decision_filter = st.selectbox(
            "Decision",
            options=["ALL", "KEEP", "DROP", "ARCHIVE", "UNDECIDED"],
            index=0,
        )
        if decision_filter == "ALL":
            decision_filter = None
    
    # Apply filters
    filtered_rows = apply_filters(
        all_rows,
        text=text_filter if text_filter else None,
        symbol=symbol_filter,
        strategy_id=strategy_filter,
        decision=decision_filter,
    )
    
    # Display filtered count
    st.caption(f"Showing {len(filtered_rows)} of {len(all_rows)} runs")
    
    # Main layout: Table on left, Detail on right
    detail_col, table_col = st.columns([2, 3])
    
    with table_col:
        st.subheader("📋 Research Index")
        
        # Create display table with clickable rows
        if filtered_rows:
            # Convert to DataFrame for display
            import pandas as pd
            
            display_df = pd.DataFrame(filtered_rows)
            # Reorder columns for better display
            display_df = display_df[["run_id", "symbol", "strategy_id", "score_final", "trades", "decision"]]
            
            # Format numeric columns
            display_df["score_final"] = display_df["score_final"].round(3)
            
            # Display as interactive table
            st.dataframe(
                display_df,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "run_id": st.column_config.TextColumn("Run ID", width="medium"),
                    "symbol": st.column_config.TextColumn("Symbol", width="small"),
                    "strategy_id": st.column_config.TextColumn("Strategy", width="medium"),
                    "score_final": st.column_config.NumberColumn("Score", format="%.3f"),
                    "trades": st.column_config.NumberColumn("Trades", format="%d"),
                    "decision": st.column_config.TextColumn("Decision", width="small"),
                }
            )
            
            # Row selection
            selected_index = st.selectbox(
                "Select a run for details:",
                options=[row["run_id"] for row in filtered_rows],
                index=0,
                key="run_selector",
            )
            st.session_state.selected_run_id = selected_index
        else:
            st.info("No runs match the current filters.")
            st.session_state.selected_run_id = None
    
    with detail_col:
        st.subheader("📄 Run Details")
        
        if st.session_state.selected_run_id:
            try:
                detail = load_run_detail(st.session_state.selected_run_id, outputs_root)
                
                # Display basic info
                st.write(f"**Run ID:** `{detail['run_id']}`")
                st.write(f"**Directory:** `{detail['run_dir']}`")
                
                # Tabs for different artifact types
                tab1, tab2, tab3, tab4 = st.tabs(["Manifest", "Metrics", "Winners", "README"])
                
                with tab1:
                    if detail["manifest"]:
                        st.json(detail["manifest"], expanded=False)
                    else:
                        st.info("No manifest.json found")
                
                with tab2:
                    if detail["metrics"]:
                        # Display key metrics
                        metrics = detail["metrics"]
                        if isinstance(metrics, dict):
                            # Show important metrics
                            important_keys = ["net_profit", "max_drawdown", "profit_factor", "sharpe", "trades"]
                            for key in important_keys:
                                if key in metrics:
                                    st.metric(key.replace("_", " ").title(), metrics[key])
                            
                            # Show full JSON
                            with st.expander("Full metrics.json"):
                                st.json(metrics)
                        else:
                            st.json(metrics)
                    else:
                        st.info("No metrics.json found")
                
                with tab3:
                    if detail["winners_v2"]:
                        st.json(detail["winners_v2"], expanded=False)
                    elif detail["winners"]:
                        st.json(detail["winners"], expanded=False)
                    else:
                        st.info("No winners.json or winners_v2.json found")
                
                with tab4:
                    if detail["readme"]:
                        st.text(detail["readme"])
                    else:
                        st.info("No README.md found")
                
                # Decision input section
                st.divider()
                st.subheader("🎯 Submit Decision")
                
                with st.form("decision_form"):
                    decision_options = ["KEEP", "DROP", "ARCHIVE"]
                    selected_decision = st.selectbox(
                        "Decision",
                        options=decision_options,
                        index=0,
                    )
                    
                    note = st.text_area(
                        "Note (minimum 5 characters)",
                        placeholder="Explain your decision...",
                        height=100,
                    )
                    
                    submitted = st.form_submit_button("Submit Decision", type="primary")
                    
                    if submitted:
                        if len(note.strip()) < 5:
                            st.error("Note must be at least 5 characters long")
                        else:
                            try:
                                submit_decision(
                                    outputs_root=outputs_root,
                                    run_id=st.session_state.selected_run_id,
                                    decision=selected_decision,
                                    note=note.strip(),
                                )
                                st.success(f"Decision '{selected_decision}' submitted successfully!")
                                
                                # Refresh the page to show updated decision
                                st.rerun()
                            except Exception as e:
                                st.error(f"Error submitting decision: {e}")
                
            except Exception as e:
                st.error(f"Error loading run details: {e}")
        else:
            st.info("Select a run from the table to view details.")
    
    # Refresh button
    if st.button("🔄 Refresh Data"):
        st.rerun()
    
    # Footer
    st.divider()
    st.caption("Research Console v1.0 • Phase 10 • Read-only UI with Decision Input")