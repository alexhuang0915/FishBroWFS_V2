"""
State Styles Helper - Apply enabled/disabled styles consistently.

Provides helper functions to apply consistent styling for enabled/disabled states
across all desktop UI widgets.
"""

from PySide6.QtWidgets import QWidget, QPushButton, QComboBox, QSpinBox, QDoubleSpinBox, QLineEdit, QTextEdit  # type: ignore
from PySide6.QtCore import Qt  # type: ignore


def apply_enabled(widget: QWidget) -> None:
    """
    Apply enabled styling to a widget.
    
    Args:
        widget: Any QWidget to apply enabled styling to
    """
    if isinstance(widget, (QPushButton, QComboBox, QSpinBox, QDoubleSpinBox, QLineEdit, QTextEdit)):
        widget.setEnabled(True)
    
    # Remove any disabled styling
    widget.setStyleSheet(widget.styleSheet().replace("state-disabled", ""))
    
    # Ensure widget is not visually disabled
    widget.setProperty("disabled", False)
    widget.style().unpolish(widget)
    widget.style().polish(widget)


def apply_disabled(widget: QWidget) -> None:
    """
    Apply disabled styling to a widget.
    
    Args:
        widget: Any QWidget to apply disabled styling to
    """
    if isinstance(widget, (QPushButton, QComboBox, QSpinBox, QDoubleSpinBox, QLineEdit, QTextEdit)):
        widget.setEnabled(False)
    
    # Add disabled state property for QSS targeting
    widget.setProperty("disabled", True)
    
    # Apply visual disabled styling via QSS class
    current_style = widget.styleSheet()
    if "state-disabled" not in current_style:
        widget.setStyleSheet(current_style + " state-disabled")
    
    widget.style().unpolish(widget)
    widget.style().polish(widget)


def set_widget_state(widget: QWidget, enabled: bool) -> None:
    """
    Set widget state (enabled or disabled) with appropriate styling.
    
    Args:
        widget: Widget to update
        enabled: True for enabled, False for disabled
    """
    if enabled:
        apply_enabled(widget)
    else:
        apply_disabled(widget)


def is_visually_disabled(widget: QWidget) -> bool:
    """
    Check if a widget is visually disabled (greyed out).
    
    Args:
        widget: Widget to check
        
    Returns:
        True if widget appears disabled, False otherwise
    """
    return not widget.isEnabled() or widget.property("disabled") == True


def apply_button_group_state(buttons: list, enabled: bool) -> None:
    """
    Apply consistent state to a group of buttons.
    
    Args:
        buttons: List of QPushButton widgets
        enabled: True for enabled, False for disabled
    """
    for button in buttons:
        set_widget_state(button, enabled)


def create_disabled_tooltip(widget: QWidget, reason: str) -> None:
    """
    Create a helpful tooltip explaining why a widget is disabled.
    
    Args:
        widget: Widget to add tooltip to
        reason: Human-readable reason for disabled state
    """
    if not widget.isEnabled():
        widget.setToolTip(f"Disabled: {reason}")
    else:
        widget.setToolTip("")


# Pre-defined disabled reasons for common UI states
DISABLED_REASONS = {
    "no_market_selected": "Select a market first",
    "data_not_ready": "Prepare data first",
    "analysis_not_ready": "Run analysis first",
    "no_artifact_ready": "No strategy result ready",
    "no_selection": "Select an item first",
    "no_changes": "No changes to apply",
    "operation_in_progress": "Operation in progress",
    "demo_mode_only": "Available in demo mode only",
}