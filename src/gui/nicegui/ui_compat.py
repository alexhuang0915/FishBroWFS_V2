"""
UI Compat Contract Layer.

Provides stable wrappers for NiceGUI widgets that have version‑sensitive APIs.
All UI code in `src/gui/nicegui/` MUST use these wrappers instead of direct
`ui.button`, `ui.input`, `ui.select`, etc. when dealing with unstable kwargs.

Constitutional invariants:
  - No unstable kwargs (size=, disabled=) passed to underlying NiceGUI constructors.
  - Value‑change events are wired via `update:model‑value` only (no `.on_change`).
  - No `.add` in tabs/panels assembly.
  - No sys.path hacks in non‑legacy tests.

This file is the single source of truth for UI compatibility.
"""
from __future__ import annotations
from typing import Callable, Optional, Any, Union, List
from nicegui import ui
from .theme.nexus_tokens import TOKENS
from .contract.ui_contract import UI_CONTRACT, PAGE_IDS, PAGE_MODULES
from typing import Dict, Any
import os
import sys

# UI element registry for forensic diagnostics
UI_REGISTRY = {
    "buttons": [],
    "inputs": [],
    "selects": [],
    "checkboxes": [],
    "cards": [],
    "tables": [],
    "logs": [],
    "pages": list(PAGE_IDS),
}

# UI element registry v2 (scoped counts)
# UI element registry v2 (scoped counts) - imported from shared module
from gui.nicegui.shared_registry import (
    _UI_REGISTRY_SCOPED,
    _current_scope_stack,
    registry_reset,
    registry_begin_scope,
    registry_end_scope,
    registry_snapshot,
    registry_counts_for_scope,
    snapshot_by_page,
    increment_count as _increment_count,
    _ensure_page_bucket,
)

# Re-export for backward compatibility
__all__ = [
    "registry_reset",
    "registry_begin_scope",
    "registry_end_scope",
    "registry_snapshot",
    "registry_counts_for_scope",
    "snapshot_by_page",
    "_increment_count",
    "_UI_REGISTRY_SCOPED",
    "_current_scope_stack",
]

def register_element(element_type: str, metadata: Dict[str, Any]) -> None:
    """Register a UI element for forensic diagnostics."""
    if os.environ.get("FISHBRO_UI_FORENSICS"):
        sys.stderr.write(f"[ui_compat] register_element {element_type}\n")
    if element_type in UI_REGISTRY:
        UI_REGISTRY[element_type].append(metadata)
    # Increment scoped counts
    _increment_count(element_type)

def register_page(page_name: str) -> None:
    """Register a page that has rendered at least one element (no‑op for contract pages)."""
    # Pages are contract‑defined; we do NOT mutate the pages list.
    # Ensure by_page entry exists with zero counts (already initialized, but guard for robustness).
    _ensure_page_bucket(page_name)


# -----------------------------------------------------------------------------
# Sizing Tokens (contracted)
# -----------------------------------------------------------------------------

class BtnSize:
    """Button size tokens mapped to stable CSS utility classes."""
    SM = "sm"
    MD = "md"
    LG = "lg"


class IconSize:
    """Icon size tokens mapped to stable CSS utility classes."""
    XS = "xs"
    SM = "sm"
    MD = "md"
    LG = "lg"
    XL = "xl"


# -----------------------------------------------------------------------------
# Size → CSS mapping (centralized, one‑line changes in future)
# -----------------------------------------------------------------------------

_BTN_SIZE_CLASSES = {
    BtnSize.SM: "text-sm px-3 py-1",
    BtnSize.MD: "text-base px-4 py-2",
    BtnSize.LG: "text-lg px-5 py-3",
}

_ICON_SIZE_CLASSES = {
    IconSize.XS: "text-xs",
    IconSize.SM: "text-sm",
    IconSize.MD: "text-base",
    IconSize.LG: "text-lg",
    IconSize.XL: "text-xl",
}


# -----------------------------------------------------------------------------
# Core Widget Wrappers
# -----------------------------------------------------------------------------

def button(
    text: str,
    *,
    size: str = BtnSize.MD,
    on_click: Optional[Callable[..., Any]] = None,
    color: Optional[str] = None,
    icon: Optional[str] = None,
    tooltip: Optional[str] = None,
    classes: str = "",
) -> Any:
    """
    Contract:
    - Never pass NiceGUI‑unstable kwargs like size= to ui.button
    - Implement sizing via CSS classes only
    - Wire click events via `.on('click', ...)` for stability
    """
    btn = ui.button(text, color=color, icon=icon)
    btn.classes(_BTN_SIZE_CLASSES.get(size, _BTN_SIZE_CLASSES[BtnSize.MD]))
    if classes:
        btn.classes(classes)
    if tooltip:
        btn.tooltip(tooltip)
    if on_click:
        btn.on("click", on_click)
    # Register for forensic diagnostics
    register_element("buttons", {"text": text, "size": size, "color": color})
    return btn


def icon(
    name: str,
    *,
    size: str = IconSize.MD,
    color: Optional[str] = None,
    classes: str = "",
) -> Any:
    """
    Contract:
    - Map size token to CSS class, do not pass size= to ui.icon
    """
    ic = ui.icon(name, color=color)
    ic.classes(_ICON_SIZE_CLASSES.get(size, _ICON_SIZE_CLASSES[IconSize.MD]))
    if classes:
        ic.classes(classes)
    return ic


def input_text(
    label: str,
    *,
    value: str = "",
    on_change: Optional[Callable[[str], Any]] = None,
    placeholder: str = "",
    classes: str = "",
) -> Any:
    """
    Contract:
    - Use `update:model‑value` event if on_change provided
    - Avoid `.on_change`
    """
    inp = ui.input(label, value=value, placeholder=placeholder)
    if classes:
        inp.classes(classes)
    if on_change:
        inp.on("update:model-value", lambda e: on_change(e.args))
    # Register for forensic diagnostics
    register_element("inputs", {"label": label, "placeholder": placeholder})
    return inp


def input_number(
    label: str,
    *,
    value: float = 0.0,
    min: Optional[float] = None,
    max: Optional[float] = None,
    step: Optional[float] = None,
    on_change: Optional[Callable[[float], Any]] = None,
    classes: str = "",
) -> Any:
    """
    Contract:
    - Use `update:model‑value` event if on_change provided
    - Avoid `.on_change`
    """
    inp = ui.number(label, value=value, min=min, max=max, step=step)
    if classes:
        inp.classes(classes)
    if on_change:
        inp.on("update:model-value", lambda e: on_change(float(e.args)))
    # Register for forensic diagnostics
    register_element("inputs", {"label": label, "type": "number"})
    return inp


def select(
    label: str,
    options: List[str],
    *,
    value: Optional[str] = None,
    on_change: Optional[Callable[[str], Any]] = None,
    classes: str = "",
) -> Any:
    """
    Contract:
    - Use `update:model‑value` event only
    """
    sel = ui.select(options, value=value, label=label)
    if classes:
        sel.classes(classes)
    if on_change:
        sel.on("update:model-value", lambda e: on_change(e.args))
    # Register for forensic diagnostics
    register_element("selects", {"label": label, "options": options})
    return sel


def checkbox(
    label: str,
    *,
    value: bool = False,
    on_change: Optional[Callable[[bool], Any]] = None,
    classes: str = "",
) -> Any:
    """
    Contract:
    - Use `update:model‑value` event only
    """
    cb = ui.checkbox(label, value=value)
    if classes:
        cb.classes(classes)
    if on_change:
        cb.on("update:model-value", lambda e: on_change(e.args))
    # Register for forensic diagnostics
    register_element("checkboxes", {"label": label, "value": value})
    return cb


# -----------------------------------------------------------------------------
# Tabs/TabPanels Assembly (canonical declarative pattern)
# -----------------------------------------------------------------------------

def create_tabbed_interface(
    tabs: List[str],
    panels: List[Callable[[], None]],
    *,
    active_tab: str = "",
) -> tuple[Any, Any]:
    """
    Create a tabbed interface using NiceGUI's canonical declarative pattern.
    Returns (tabs_element, panels_element).
    """
    tabs_element = ui.tabs().classes("w-full")
    for tab in tabs:
        ui.tab(tab).classes("text-sm font-medium")
    panels_element = ui.tab_panels(tabs_element, value=active_tab).classes("w-full")
    for i, panel_func in enumerate(panels):
        with ui.tab_panel(tabs[i]):
            panel_func()
    return tabs_element, panels_element


# -----------------------------------------------------------------------------
# Guard Utilities (for tests)
# -----------------------------------------------------------------------------

def get_forbidden_patterns() -> List[str]:
    """Return regex patterns that must not appear in UI modules."""
    return [
        r'\.on_change\(',
        r'ui\.button\([^)]*size\s*=',
        r'\.add\(',  # in UI context, but may have false positives; guard test can refine
    ]


def get_forbidden_test_patterns() -> List[str]:
    """Return regex patterns that must not appear in non‑legacy tests."""
    return [
        r'sys\.path\.(insert|append)\(',
    ]