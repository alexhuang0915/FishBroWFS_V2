"""UI Compatibility Wrapper - Canonical NiceGUI patterns for FishBroWFS_V2.

This module provides wrapper functions that enforce the canonical UI patterns:
1. No label= keyword argument in widget constructors
2. Labels are separate ui.label() widgets
3. Consistent spacing and styling
4. Built-in bindability support

Usage:
    from FishBroWFS_V2.gui.nicegui.ui_compat import labeled_date, labeled_input
    
    # Instead of: ui.date(label="Start Date")
    # Use:
    labeled_date("Start Date").bind_value(state, "start_date")
"""

from typing import Any, Callable, Optional, List, Dict, Union
from nicegui import ui


def labeled(widget_factory: Callable, label: str, *args, **kwargs) -> Any:
    """Create a labeled widget using the canonical pattern.
    
    Args:
        widget_factory: UI widget constructor (e.g., ui.date, ui.input)
        label: Label text to display above the widget
        *args, **kwargs: Passed to widget_factory
        
    Returns:
        The created widget instance
        
    Example:
        >>> date_widget = labeled(ui.date, "Start Date", value="2024-01-01")
        >>> date_widget.bind_value(state, "start_date")
    """
    with ui.column().classes("gap-1 w-full"):
        ui.label(label)
        widget = widget_factory(*args, **kwargs)
        return widget


def labeled_date(label: str, **kwargs) -> Any:
    """Create a labeled date picker.
    
    Args:
        label: Label text
        **kwargs: Passed to ui.date()
        
    Returns:
        ui.date widget instance
    """
    return labeled(ui.date, label, **kwargs)


def labeled_input(label: str, **kwargs) -> Any:
    """Create a labeled text input.
    
    Args:
        label: Label text
        **kwargs: Passed to ui.input()
        
    Returns:
        ui.input widget instance
    """
    return labeled(ui.input, label, **kwargs)


def labeled_select(label: str, **kwargs) -> Any:
    """Create a labeled select/dropdown.
    
    Args:
        label: Label text
        **kwargs: Passed to ui.select()
        
    Returns:
        ui.select widget instance
    """
    return labeled(ui.select, label, **kwargs)


def labeled_number(label: str, **kwargs) -> Any:
    """Create a labeled number input.
    
    Args:
        label: Label text
        **kwargs: Passed to ui.number()
        
    Returns:
        ui.number widget instance
    """
    return labeled(ui.number, label, **kwargs)


def labeled_textarea(label: str, **kwargs) -> Any:
    """Create a labeled textarea.
    
    Args:
        label: Label text
        **kwargs: Passed to ui.textarea()
        
    Returns:
        ui.textarea widget instance
    """
    return labeled(ui.textarea, label, **kwargs)


def labeled_slider(label: str, **kwargs) -> Any:
    """Create a labeled slider.
    
    Args:
        label: Label text
        **kwargs: Passed to ui.slider()
        
    Returns:
        ui.slider widget instance
    """
    return labeled(ui.slider, label, **kwargs)


def labeled_checkbox(label: str, **kwargs) -> Any:
    """Create a labeled checkbox.
    
    Note: ui.checkbox already has built-in label support via first positional arg.
    This wrapper maintains consistency with other labeled widgets.
    
    Args:
        label: Label text
        **kwargs: Passed to ui.checkbox()
        
    Returns:
        ui.checkbox widget instance
    """
    return labeled(ui.checkbox, label, **kwargs)


def labeled_switch(label: str, **kwargs) -> Any:
    """Create a labeled switch.
    
    Note: ui.switch already has built-in label support via first positional arg.
    This wrapper maintains consistency with other labeled widgets.
    
    Args:
        label: Label text
        **kwargs: Passed to ui.switch()
        
    Returns:
        ui.switch widget instance
    """
    return labeled(ui.switch, label, **kwargs)


def labeled_radio(label: str, **kwargs) -> Any:
    """Create a labeled radio button group.
    
    Args:
        label: Label text
        **kwargs: Passed to ui.radio()
        
    Returns:
        ui.radio widget instance
    """
    return labeled(ui.radio, label, **kwargs)


def labeled_color_input(label: str, **kwargs) -> Any:
    """Create a labeled color input.
    
    Args:
        label: Label text
        **kwargs: Passed to ui.color_input()
        
    Returns:
        ui.color_input widget instance
    """
    return labeled(ui.color_input, label, **kwargs)


def labeled_upload(label: str, **kwargs) -> Any:
    """Create a labeled file upload.
    
    Args:
        label: Label text
        **kwargs: Passed to ui.upload()
        
    Returns:
        ui.upload widget instance
    """
    return labeled(ui.upload, label, **kwargs)


def form_section(title: str) -> Any:
    """Create a form section with consistent styling.
    
    Args:
        title: Section title
        
    Returns:
        Context manager for the form section
    """
    return ui.card().classes("w-full p-4 mb-6 bg-nexus-900")


def form_row() -> Any:
    """Create a form row with consistent spacing.
    
    Returns:
        Context manager for the form row
    """
    return ui.row().classes("w-full gap-4 mb-4")


def form_column() -> Any:
    """Create a form column with consistent spacing.
    
    Returns:
        Context manager for the form column
    """
    return ui.column().classes("gap-2 w-full")


# Convenience function for wizard forms
def wizard_field(label: str, widget_type: str = "input", **kwargs) -> Any:
    """Create a wizard form field with consistent styling.
    
    Args:
        label: Field label
        widget_type: Type of widget ('date', 'input', 'select', 'number', 'textarea')
        **kwargs: Passed to the widget constructor
        
    Returns:
        The created widget instance
        
    Raises:
        ValueError: If widget_type is not supported
    """
    widget_map = {
        'date': labeled_date,
        'input': labeled_input,
        'select': labeled_select,
        'number': labeled_number,
        'textarea': labeled_textarea,
        'slider': labeled_slider,
        'checkbox': labeled_checkbox,
        'switch': labeled_switch,
        'radio': labeled_radio,
        'color': labeled_color_input,
        'upload': labeled_upload,
    }
    
    if widget_type not in widget_map:
        raise ValueError(f"Unsupported widget_type: {widget_type}. "
                       f"Supported: {list(widget_map.keys())}")
    
    widget = widget_map[widget_type](label, **kwargs)
    widget.classes("w-full")
    return widget


# Example usage (commented out for documentation):
"""
# Before (forbidden):
# ui.date(label="Start Date", value="2024-01-01")  # This is the forbidden pattern

# After (canonical):
from FishBroWFS_V2.gui.nicegui.ui_compat import labeled_date
labeled_date("Start Date", value="2024-01-01").bind_value(state, "start_date")

# Or using wizard_field for wizard forms:
wizard_field("Start Date", "date", value="2024-01-01").bind_value(state, "start_date")
"""