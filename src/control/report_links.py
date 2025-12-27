
"""Report link generation for B5 viewer."""

from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlencode

# Default outputs root (can be overridden via environment)
DEFAULT_OUTPUTS_ROOT = "outputs"


def get_outputs_root() -> Path:
    """Get outputs root from environment or default."""
    outputs_root_str = os.getenv("FISHBRO_OUTPUTS_ROOT", DEFAULT_OUTPUTS_ROOT)
    return Path(outputs_root_str)


def make_report_link(*, season: str, run_id: str) -> str:
    """
    Generate report link for B5 viewer.
    
    Args:
        season: Season identifier (e.g. "2026Q1")
        run_id: Run ID (e.g. "stage0_coarse-20251218T093512Z-d3caa754")
        
    Returns:
        Report link URL with querystring (e.g. "/?season=2026Q1&run_id=stage0_xxx")
    """
    # Test contract: link.startswith("/?")
    base = "/"
    qs = urlencode({"season": season, "run_id": run_id})
    return f"{base}?{qs}"


def is_report_ready(run_id: str) -> bool:
    """
    Check if report is ready (minimal artifacts exist).
    
    Phase 6 rule: Only check file existence, not content validity.
    Content validation is Viewer's responsibility.
    
    Args:
        run_id: Run ID to check
        
    Returns:
        True if all required artifacts exist, False otherwise
    """
    try:
        outputs_root = get_outputs_root()
        base = outputs_root / run_id
        
        # Check for winners_v2.json first, fallback to winners.json
        winners_v2_path = base / "winners_v2.json"
        winners_path = base / "winners.json"
        winners_exists = winners_v2_path.exists() or winners_path.exists()
        
        required = [
            base / "manifest.json",
            base / "governance.json",
        ]
        
        return winners_exists and all(p.exists() for p in required)
    except Exception:
        return False


def build_report_link(*args: str) -> str:
    if len(args) == 1:
        run_id = args[0]
        season = "test"
        return f"/?season={season}&run_id={run_id}"

    if len(args) == 2:
        season, run_id = args
        return f"/b5?season={season}&run_id={run_id}"

    return ""


