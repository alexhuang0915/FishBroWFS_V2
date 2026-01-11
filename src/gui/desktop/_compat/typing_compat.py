"""
Typing helpers for desktop UI.

Centralizes common type aliases and optional‑assertion patterns.
"""

from __future__ import annotations

from pathlib import Path
from typing import TypeVar, Union, Optional, cast
from PySide6.QtCore import QModelIndex, QPersistentModelIndex  # type: ignore
from PySide6.QtWidgets import QStyleOptionViewItem  # type: ignore
from PySide6.QtCore import QRect  # type: ignore

T = TypeVar("T")

# Union for model‑index parameters that accept both QModelIndex and QPersistentModelIndex.
IndexLike = Union[QModelIndex, QPersistentModelIndex]

# Path‑like string or Path object (used in file‑dialog helpers).
PathLikeStr = Union[str, Path]


def assert_not_none(x: Optional[T], msg: str = "") -> T:
    """
    Assert that `x` is not None and return it, satisfying type checkers.

    Use this for optional widget attributes that are guaranteed to be initialized
    before the point of use (e.g., after `setup_ui`).

    Example:
        self.tab_widget = assert_not_none(self.tab_widget, "tab_widget not initialized")
    """
    assert x is not None, msg or "expected non‑None value"
    return x


def option_rect(option: QStyleOptionViewItem) -> QRect:
    """
    Return the `rect` attribute of a QStyleOptionViewItem with a single type ignore.

    QStyleOptionViewItem.rect is not recognized by some PySide6 stubs;
    this helper isolates the ignore to one location.
    """
    return option.rect  # type: ignore[attr-defined]