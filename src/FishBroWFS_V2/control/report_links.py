"""Report link generation for B5 viewer."""

from __future__ import annotations

from urllib.parse import urlencode


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
