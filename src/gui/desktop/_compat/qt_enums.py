"""
Qt6 enum convenience helpers.

Provides short‑hand constants for commonly used Qt enum values.
"""

from PySide6.QtCore import Qt  # type: ignore

# Alignment flags
AlignLeft = Qt.AlignmentFlag.AlignLeft
AlignRight = Qt.AlignmentFlag.AlignRight
AlignCenter = Qt.AlignmentFlag.AlignCenter
AlignTop = Qt.AlignmentFlag.AlignTop
AlignBottom = Qt.AlignmentFlag.AlignBottom

# Orientations
Horizontal = Qt.Orientation.Horizontal
Vertical = Qt.Orientation.Vertical

# Item data roles
DisplayRole = Qt.ItemDataRole.DisplayRole
TextAlignmentRole = Qt.ItemDataRole.TextAlignmentRole
ForegroundRole = Qt.ItemDataRole.ForegroundRole
BackgroundRole = Qt.ItemDataRole.BackgroundRole
FontRole = Qt.ItemDataRole.FontRole
UserRole = Qt.ItemDataRole.UserRole

# Standard colors (QColor constants)
darkGreen = Qt.GlobalColor.darkGreen
darkRed = Qt.GlobalColor.darkRed

__all__ = [
    "AlignLeft",
    "AlignRight",
    "AlignCenter",
    "AlignTop",
    "AlignBottom",
    "Horizontal",
    "Vertical",
    "DisplayRole",
    "TextAlignmentRole",
    "ForegroundRole",
    "BackgroundRole",
    "FontRole",
    "UserRole",
    "darkGreen",
    "darkRed",
]