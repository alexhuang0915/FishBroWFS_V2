
"""Pure page module for portfolio plan viewer (read-only, zero-write).

IMPORTANT:
- No main() function (conforms to single entrypoint rule)
- No side effects on import (no scanning, no file writes)
- All streamlit imports are deferred inside render_page()
- outputs_root must be injected by the entrypoint
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional, List, Dict, Any

from FishBroWFS_V2.portfolio.plan_view_loader import load_plan_view_json


def scan_plan_ids(outputs_root: Path) -> List[str]:
    """Read-only: list plan_ids that have plan_view.json under outputs_root."""
    base = outputs_root / "portfolio" / "plans"
    if not base.exists():
        return []
    
    plan_ids: List[str] = []
    for p in sorted(base.iterdir(), key=lambda x: x.name):
        if not p.is_dir():
            continue
        if (p / "plan_view.json").exists():
            plan_ids.append(p.name)
    return plan_ids


def load_view(outputs_root: Path, plan_id: str) -> Dict[str, Any]:
    """Read-only: load view model."""
    plan_dir = outputs_root / "portfolio" / "plans" / plan_id
    view = load_plan_view_json(plan_dir)
    return view.model_dump()


def render_page(outputs_root: Path) -> None:
    """
    DEPRECATED: Streamlit page renderer - no longer used after migration to NiceGUI.
    
    This function is kept for compatibility but will raise an ImportError
    if streamlit is not available.
    """
    raise ImportError(
        "plan_viewer.py render_page() is deprecated. "
        "Streamlit UI has been migrated to NiceGUI. "
        "Use the NiceGUI dashboard instead."
    )


