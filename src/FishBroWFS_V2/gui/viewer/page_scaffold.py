"""Viewer page scaffold - unified "never crash" page skeleton.

Provides consistent page structure that never raises exceptions.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import streamlit as st

from FishBroWFS_V2.core.artifact_reader import try_read_artifact
from FishBroWFS_V2.core.artifact_status import (
    ValidationResult,
    validate_manifest_status,
    validate_winners_v2_status,
    validate_governance_status,
)

from FishBroWFS_V2.gui.viewer.load_state import (
    ArtifactLoadState,
    ArtifactLoadStatus,
    compute_load_state,
)
from FishBroWFS_V2.gui.viewer.components.status_bar import render_artifact_status_bar


@dataclass(frozen=True)
class Bundle:
    """
    Bundle of artifacts for Viewer page.
    
    Contains loaded artifacts and their load states.
    """
    manifest_state: ArtifactLoadState
    winners_v2_state: ArtifactLoadState
    governance_state: ArtifactLoadState
    
    @property
    def all_ok(self) -> bool:
        """Check if all artifacts are OK."""
        return all(
            s.status.value == "OK"
            for s in [self.manifest_state, self.winners_v2_state, self.governance_state]
        )
    
    @property
    def has_blocking_error(self) -> bool:
        """Check if any artifact is MISSING or INVALID (blocks page content)."""
        blocking_statuses = {"MISSING", "INVALID"}
        return any(
            s.status.value in blocking_statuses
            for s in [self.manifest_state, self.winners_v2_state, self.governance_state]
        )


def render_viewer_page(
    title: str,
    run_dir: Path,
    content_render_fn: Optional[Callable[[Bundle], None]] = None,
) -> None:
    """
    Render Viewer page with unified scaffold.
    
    This function ensures Viewer pages never crash - all errors are handled gracefully.
    
    Args:
        title: Page title
        run_dir: Path to run directory containing artifacts
        content_render_fn: Optional function to render page content.
                         Receives Bundle with artifact states.
                         If None, only status bar is rendered.
    
    Contract:
        - Never raises exceptions
        - Always renders status bar
        - Shows BLOCKED panel if artifacts are MISSING/INVALID
        - Calls content_render_fn only if artifacts are OK or DIRTY (non-blocking)
    """
    st.set_page_config(page_title=title, layout="wide")
    st.title(title)
    
    # ❶ Load bundle - completely wrapped in try/except
    try:
        bundle = _load_bundle(run_dir)
    except Exception as e:
        # Load phase any error → BLOCKED
        states = [
            ArtifactLoadState(
                status=ArtifactLoadStatus.INVALID,
                artifact_name="bundle",
                path=None,
                error=f"load_bundle_fn exception: {e}",
                dirty_reasons=[],
                last_modified_ts=None,
            )
        ]
        render_artifact_status_bar(states)
        st.error("**BLOCKED / 無法載入**")
        st.error(f"Viewer BLOCKED: failed to load artifacts. Error: {e}")
        return
    
    # ❷ Bundle loaded successfully, but internal artifacts may still be missing/invalid
    states = [
        bundle.manifest_state,
        bundle.winners_v2_state,
        bundle.governance_state,
    ]
    
    render_artifact_status_bar(states)
    
    # Check if any artifact is MISSING or INVALID (blocks page content)
    if bundle.has_blocking_error:
        st.error("**BLOCKED / 無法載入**")
        st.warning("Viewer BLOCKED due to invalid or missing artifacts.")
        return
    
    # ❸ Only OK / DIRTY will reach content render
    if content_render_fn is not None:
        try:
            content_render_fn(bundle)
        except Exception as e:
            # Catch any exceptions from content renderer
            st.error(f"**內容渲染錯誤:** {e}")
            st.exception(e)


def _load_bundle(run_dir: Path) -> Bundle:
    """
    Load artifact bundle from run directory.
    
    Never raises exceptions - all errors are captured in ArtifactLoadState.
    """
    manifest_path = run_dir / "manifest.json"
    winners_path = run_dir / "winners.json"  # Note: file is winners.json but schema is winners_v2
    governance_path = run_dir / "governance.json"
    
    # Read artifacts (never raises)
    manifest_read = try_read_artifact(manifest_path)
    winners_read = try_read_artifact(winners_path)
    governance_read = try_read_artifact(governance_path)
    
    # Validate artifacts (may raise, but we catch exceptions)
    manifest_validation: Optional[ValidationResult] = None
    winners_validation: Optional[ValidationResult] = None
    governance_validation: Optional[ValidationResult] = None
    
    try:
        if manifest_read.is_ok and manifest_read.result:
            # Use already-read data for validation
            manifest_data = manifest_read.result.raw
            manifest_validation = validate_manifest_status(str(manifest_path), manifest_data)
    except Exception:
        pass  # Validation failed, will use read_result only
    
    try:
        if winners_read.is_ok and winners_read.result:
            # Use already-read data for validation
            winners_data = winners_read.result.raw
            winners_validation = validate_winners_v2_status(str(winners_path), winners_data)
    except Exception:
        pass
    
    try:
        if governance_read.is_ok and governance_read.result:
            # Use already-read data for validation
            governance_data = governance_read.result.raw
            governance_validation = validate_governance_status(str(governance_path), governance_data)
    except Exception:
        pass
    
    # Compute load states (never raises)
    manifest_state = compute_load_state(
        "manifest",
        manifest_path,
        manifest_read,
        manifest_validation,
    )
    
    winners_state = compute_load_state(
        "winners_v2",
        winners_path,
        winners_read,
        winners_validation,
    )
    
    governance_state = compute_load_state(
        "governance",
        governance_path,
        governance_read,
        governance_validation,
    )
    
    return Bundle(
        manifest_state=manifest_state,
        winners_v2_state=winners_state,
        governance_state=governance_state,
    )
