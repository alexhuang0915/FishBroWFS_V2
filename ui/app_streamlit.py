"""Streamlit B5 Audit Console - Viewer-only."""

from __future__ import annotations

import os
from pathlib import Path

import streamlit as st

from ui.core.artifact_reader import read_artifact
from ui.core.status import (
    ArtifactStatus,
    validate_governance_status,
    validate_manifest_status,
    validate_winners_v2_status,
)

# Contract: Only use ui/core/* to read artifacts
# Strictly NO import of FishBroWFS_V2.pipeline / engine


def main() -> None:
    """Main Streamlit app."""
    st.set_page_config(page_title="B5 Audit Console", layout="wide")
    
    # Read query params
    season = st.query_params.get("season", "")
    run_id = st.query_params.get("run_id", "")
    
    if not season or not run_id:
        st.error("Missing query parameters: season and run_id required")
        st.info("Usage: /?season=...&run_id=...")
        st.info("Example: /?season=2026Q1&run_id=stage0_coarse-20251218T093512Z-d3caa754")
        return
    
    st.title(f"B5 Audit Console - {season} / {run_id}")
    
    # Determine run directory
    # Get outputs_root from environment or use default
    outputs_root_str = os.getenv("FISHBRO_OUTPUTS_ROOT", "outputs")
    outputs_root = Path(outputs_root_str)
    run_dir = outputs_root / "seasons" / season / "runs" / run_id
    
    if not run_dir.exists():
        st.error(f"Run directory does not exist: {run_dir}")
        st.info(f"Outputs root: {outputs_root}")
        st.info(f"Expected path: {run_dir}")
        return
    
    st.info(f"Run directory: {run_dir}")
    
    # Check artifact status
    st.subheader("Artifact Status")
    
    manifest_path = run_dir / "manifest.json"
    metrics_path = run_dir / "metrics.json"
    winners_path = run_dir / "winners.json"
    governance_path = run_dir / "governance.json"
    
    manifest_result = validate_manifest_status(str(manifest_path))
    winners_result = validate_winners_v2_status(str(winners_path))
    governance_result = validate_governance_status(str(governance_path))
    
    # Simple check for metrics
    metrics_status = ArtifactStatus.OK if metrics_path.exists() else ArtifactStatus.MISSING
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Manifest", manifest_result.status.value)
    with col2:
        st.metric("Metrics", metrics_status.value)
    with col3:
        st.metric("Winners", winners_result.status.value)
    with col4:
        st.metric("Governance", governance_result.status.value)
    
    # Read and display artifacts
    st.subheader("Artifacts")
    
    try:
        manifest_result = read_artifact(run_dir / "manifest.json")
        st.json(manifest_result.raw)
    except Exception as e:
        st.error(f"Error reading manifest: {e}")
    
    try:
        metrics_result = read_artifact(run_dir / "metrics.json")
        st.json(metrics_result.raw)
    except Exception as e:
        st.error(f"Error reading metrics: {e}")
    
    try:
        winners_result = read_artifact(run_dir / "winners.json")
        st.json(winners_result.raw)
    except Exception as e:
        st.error(f"Error reading winners: {e}")
    
    try:
        governance_result = read_artifact(run_dir / "governance.json")
        st.json(governance_result.raw)
    except Exception as e:
        st.error(f"Error reading governance: {e}")


if __name__ == "__main__":
    main()

