
"""Research Console Page Module (DEPRECATED).

Phase 10: Read-only Research UI + Decision Input.
This module is DEPRECATED after migration to NiceGUI.
"""

from __future__ import annotations

from pathlib import Path


def render(outputs_root: Path) -> None:
    """DEPRECATED: Research Console page renderer - no longer used after migration to NiceGUI.
    
    This function is kept for compatibility but will raise an ImportError
    if streamlit is not available.
    """
    raise ImportError(
        "research/page.py render() is deprecated. "
        "Streamlit UI has been migrated to NiceGUI. "
        "Use the NiceGUI dashboard instead."
    )


