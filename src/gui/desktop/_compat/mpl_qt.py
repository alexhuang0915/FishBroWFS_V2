"""
Matplotlib Qt6 backend compatibility.

Provides stable imports for FigureCanvas and NavigationToolbar across different
Matplotlib versions and Qt bindings.

Usage:
    from gui.desktop._compat.mpl_qt import FigureCanvas, NavigationToolbar
"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING, Type, cast

if TYPE_CHECKING:
    from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg  # type: ignore
    from matplotlib.backends.backend_qt import NavigationToolbar2QT  # type: ignore
else:
    # Runtime import with fallback for older Matplotlib or missing Qt6 bindings.
    try:
        # Modern Matplotlib (>=3.5) with Qt6 backend.
        from matplotlib.backends.backend_qtagg import (  # type: ignore
            FigureCanvasQTAgg as FigureCanvasQTAggImpl,
            NavigationToolbar2QT as NavigationToolbar2QTImpl,
        )
    except ImportError:
        # Fallback to Qt5 backend (still works with Qt6 bindings in many cases).
        from matplotlib.backends.backend_qt5agg import (  # type: ignore
            FigureCanvasQTAgg as FigureCanvasQTAggImpl,
            NavigationToolbar2QT as NavigationToolbar2QTImpl,
        )

    FigureCanvasQTAgg = FigureCanvasQTAggImpl
    NavigationToolbar2QT = NavigationToolbar2QTImpl

# Export the concrete classes as type‑stable aliases.
FigureCanvas = FigureCanvasQTAgg  # type: ignore[no-redef]
NavigationToolbar = NavigationToolbar2QT  # type: ignore[no-redef]

__all__ = ["FigureCanvas", "NavigationToolbar"]