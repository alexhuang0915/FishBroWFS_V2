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
    if "note_text" not in st.session_state:
        st.session_state.note_text = ""
    
    # Title and header
    st.title("📊 Research Console")
    
    # Configuration
    research_dir = outputs_root / "research"
    
    # Reload button at the top
    reload_col1, reload_col2 = st.columns([3, 1])
    with reload_col1:
        st.write(f"**Outputs Root:** `{outputs_root}`")
    with reload_col2:
        if st.button("🔄 Reload Index", use_container_width=True):
            st.session_state.last_refresh = datetime.now().timestamp()
            st.rerun()
    
    # Check if research artifacts exist
    try:
        artifacts = load_research_artifacts(outputs_root)
    except FileNotFoundError as e:
        st.error(f"Research artifacts not found: {e}")
        st.info("Please run research index generation first.")
        return
    
    # Header information
    col1, col2 = st.columns(2)
    with col1:
        index_mtime = datetime.fromtimestamp(artifacts["index_mtime"])
        st.metric("Index Last Updated", index_mtime.strftime("%Y-%m-%d %H:%M:%S"))
    with col2:
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
        text_filter = st.text_input(
            "Keyword Search",
            placeholder="run_id, symbol, or strategy",
            help="Search in run_id, symbol, or strategy_id"
        )
    
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
        
        if filtered_rows:
            # Convert to DataFrame for display
            import pandas as pd
            
            display_df = pd.DataFrame(filtered_rows)
            # Reorder columns for better display
            display_df = display_df[["run_id", "symbol", "strategy_id", "score_final", "trades", "decision"]]
            
            # Format numeric columns
            display_df["score_final"] = display_df["score_final"].round(3)
            display_df["trades"] = display_df["trades"].fillna(0).astype(int)
            
            # Replace NaN/None with appropriate values
            display_df["symbol"] = display_df["symbol"].fillna("N/A")
            display_df["strategy_id"] = display_df["strategy_id"].fillna("N/A")
            display_df["decision"] = display_df["decision"].fillna("EMPTY")
            
            # Display as interactive table with sorting
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
            
            # Row selection using radio buttons for better UX
            st.subheader("Select Run for Details")
            if len(filtered_rows) > 0:
                run_options = [row["run_id"] for row in filtered_rows]
                selected_run = st.radio(
                    "Choose a run to view details:",
                    options=run_options,
                    index=0,
                    key="run_selection",
                    label_visibility="collapsed"
                )
                st.session_state.selected_run_id = selected_run
            else:
                st.info("No runs match the current filters.")
                st.session_state.selected_run_id = None
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
                tab1, tab2, tab3 = st.tabs(["Manifest", "Metrics", "README"])
                
                with tab1:
                    if detail["manifest"]:
                        st.write("**Manifest Summary:**")
                        manifest = detail["manifest"]
                        for key, value in manifest.items():
                            if value is not None:
                                st.write(f"- **{key.replace('_', ' ').title()}:** `{value}`")
                        
                        # Show full manifest in expander
                        if detail["full_manifest"]:
                            with st.expander("View Full Manifest"):
                                st.json(detail["full_manifest"])
                    else:
                        st.info("No manifest.json found")
                
                with tab2:
                    if detail["metrics"]:
                        st.write("**Metrics Summary:**")
                        metrics = detail["metrics"]
                        
                        # Display key metrics in columns
                        metric_col1, metric_col2 = st.columns(2)
                        
                        with metric_col1:
                            if metrics.get("net_profit") is not None:
                                st.metric("Net Profit", f"{metrics['net_profit']:,.2f}")
                            if metrics.get("trades") is not None:
                                st.metric("Trades", metrics["trades"])
                        
                        with metric_col2:
                            if metrics.get("max_drawdown") is not None:
                                st.metric("Max Drawdown", f"{metrics['max_drawdown']:.2%}")
                            if metrics.get("profit_factor") is not None:
                                st.metric("Profit Factor", f"{metrics['profit_factor']:.2f}")
                        
                        # Show additional metrics
                        if metrics.get("sharpe") is not None:
                            st.metric("Sharpe Ratio", f"{metrics['sharpe']:.2f}")
                        if metrics.get("win_rate") is not None:
                            st.metric("Win Rate", f"{metrics['win_rate']:.2%}")
                        
                        # Show full metrics in expander
                        if detail["full_metrics"]:
                            with st.expander("View Full Metrics"):
                                st.json(detail["full_metrics"])
                    else:
                        st.info("No metrics.json found")
                
                with tab3:
                    if detail["readme"]:
                        st.write("**README Summary:**")
                        st.text_area(
                            "README Content",
                            value=detail["readme"],
                            height=300,
                            disabled=True,
                            label_visibility="collapsed"
                        )
                        
                        # Show full README in expander if truncated
                        if detail["full_readme"] and len(detail["full_readme"]) > 4000:
                            with st.expander("View Full README"):
                                st.text(detail["full_readme"])
                    else:
                        st.info("No README.md found")
                
                # Decision input section
                st.divider()
                st.subheader("🎯 Submit Decision")
                
                with st.form("decision_form", clear_on_submit=True):
                    decision_options = ["KEEP", "DROP", "ARCHIVE"]
                    selected_decision = st.selectbox(
                        "Decision",
                        options=decision_options,
                        index=0,
                        key="decision_select"
                    )
                    
                    note = st.text_area(
                        "Note (minimum 5 characters)",
                        placeholder="Explain your decision...",
                        height=100,
                        key="note_input",
                        help="Note must be at least 5 characters long"
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
                                
                                # Clear note and refresh
                                st.session_state.note_text = ""
                                st.rerun()
                            except Exception as e:
                                st.error(f"Error submitting decision: {e}")
                
            except Exception as e:
                st.error(f"Error loading run details: {e}")
                st.info(f"Run ID: {st.session_state.selected_run_id}")
        else:
            st.info("Select a run from the table to view details.")
    
    # Footer
    st.divider()
    st.caption("Research Console v1.0 • Phase 10.1 • Read-only UI with Decision Input")
