"""KPI Viewer page.

Displays KPIs with evidence drill-down capability.
"""

from __future__ import annotations

import streamlit as st

from FishBroWFS_V2.gui.viewer.page_scaffold import Bundle
from FishBroWFS_V2.gui.viewer.components.kpi_table import render_kpi_table
from FishBroWFS_V2.gui.viewer.components.evidence_panel import render_evidence_panel
from FishBroWFS_V2.core.artifact_reader import try_read_artifact


def render_page(bundle: Bundle) -> None:
    """
    Render KPI viewer page.
    
    Args:
        bundle: Bundle containing artifact load states
        
    Contract:
        - Never raises exceptions
        - Extracts KPIs from artifacts
        - Renders KPI table and evidence panel
    """
    try:
        # Extract artifacts data
        artifacts = _extract_artifacts(bundle)
        
        # Extract KPIs from artifacts
        kpi_rows = _extract_kpis(artifacts)
        
        # Layout: KPI table on left, evidence panel on right
        col1, col2 = st.columns([2, 1])
        
        with col1:
            render_kpi_table(kpi_rows)
        
        with col2:
            render_evidence_panel(artifacts)
    
    except Exception as e:
        st.error(f"Error rendering KPI page: {e}")


def _extract_artifacts(bundle: Bundle) -> dict[str, dict]:
    """
    Extract artifact data from bundle.
    
    Returns dictionary mapping artifact names to their JSON data.
    """
    artifacts: dict[str, dict] = {}
    
    try:
        # Extract manifest
        if bundle.manifest_state.status.value == "OK" and bundle.manifest_state.path:
            manifest_read = try_read_artifact(bundle.manifest_state.path)
            if manifest_read.is_ok and manifest_read.result:
                artifacts["manifest"] = manifest_read.result.raw
        
        # Extract winners_v2
        if bundle.winners_v2_state.status.value == "OK" and bundle.winners_v2_state.path:
            winners_read = try_read_artifact(bundle.winners_v2_state.path)
            if winners_read.is_ok and winners_read.result:
                artifacts["winners_v2"] = winners_read.result.raw
        
        # Extract governance
        if bundle.governance_state.status.value == "OK" and bundle.governance_state.path:
            governance_read = try_read_artifact(bundle.governance_state.path)
            if governance_read.is_ok and governance_read.result:
                artifacts["governance"] = governance_read.result.raw
    
    except Exception:
        pass
    
    return artifacts


def _extract_kpis(artifacts: dict[str, dict]) -> list[dict]:
    """
    Extract KPI rows from artifacts.
    
    Returns list of KPI row dictionaries.
    """
    kpi_rows: list[dict] = []
    
    try:
        # Extract from winners_v2 summary
        winners_v2 = artifacts.get("winners_v2", {})
        summary = winners_v2.get("summary", {})
        
        if "net_profit" in summary:
            kpi_rows.append({
                "name": "net_profit",
                "value": summary["net_profit"],
                "label": "Net Profit",
            })
        
        if "max_drawdown" in summary:
            kpi_rows.append({
                "name": "max_drawdown",
                "value": summary["max_drawdown"],
                "label": "Max Drawdown",
            })
        
        if "num_trades" in summary:
            kpi_rows.append({
                "name": "num_trades",
                "value": summary["num_trades"],
                "label": "Number of Trades",
            })
        
        # Extract from governance scoring
        governance = artifacts.get("governance", {})
        scoring = governance.get("scoring", {})
        
        if "final_score" in scoring:
            kpi_rows.append({
                "name": "final_score",
                "value": scoring["final_score"],
                "label": "Final Score",
            })
    
    except Exception:
        pass
    
    return kpi_rows
