"""Unit tests for header component."""
import pytest
from unittest.mock import patch, MagicMock, call
from gui.nicegui.layout.header import (
    _state_to_color,
    _state_to_text,
    _state_to_style_class,
    render_header,
)
from gui.nicegui.theme.nexus_tokens import TOKENS


def test_state_to_color():
    """Mapping of state strings to color tokens."""
    assert _state_to_color("ONLINE") == TOKENS['accents']['success']
    assert _state_to_color("DEGRADED") == TOKENS['accents']['warning']
    assert _state_to_color("OFFLINE") == TOKENS['accents']['danger']
    # Unknown state defaults to danger
    assert _state_to_color("UNKNOWN") == TOKENS['accents']['danger']


def test_state_to_text():
    """Mapping of state strings to display text."""
    assert _state_to_text("ONLINE") == "System Online"
    assert _state_to_text("DEGRADED") == "System Degraded"
    assert _state_to_text("OFFLINE") == "System Offline"
    assert _state_to_text("UNKNOWN") == "System Offline"


def test_state_to_style_class():
    """Mapping of state strings to CSS classes."""
    assert _state_to_style_class("ONLINE") == "text-success"
    assert _state_to_style_class("DEGRADED") == "text-warning"
    assert _state_to_style_class("OFFLINE") == "text-danger"
    assert _state_to_style_class("UNKNOWN") == "text-danger"


@patch("gui.nicegui.layout.header.ui")
@patch("gui.nicegui.layout.header.uic")
@patch("gui.nicegui.services.status_service.get_state")
@patch("gui.nicegui.services.status_service.get_summary")
def test_render_header_creates_elements(
    mock_get_summary, mock_get_state, mock_uic, mock_ui
):
    """Header renders without error and creates expected UI elements."""
    mock_get_state.return_value = "ONLINE"
    mock_get_summary.return_value = "All systems operational"
    
    # Mock UI components
    mock_header = MagicMock()
    mock_ui.header.return_value.__enter__ = MagicMock(return_value=mock_header)
    mock_ui.header.return_value.__exit__ = MagicMock()
    
    mock_row = MagicMock()
    mock_ui.row.return_value.__enter__ = MagicMock(return_value=mock_row)
    mock_ui.row.return_value.__exit__ = MagicMock()
    
    mock_icon = MagicMock()
    mock_uic.icon.return_value = mock_icon
    
    mock_label = MagicMock()
    mock_ui.label.return_value = mock_label
    
    mock_separator = MagicMock()
    mock_ui.separator.return_value = mock_separator
    
    mock_tooltip = MagicMock()
    mock_ui.tooltip.return_value = mock_tooltip
    
    mock_button = MagicMock()
    mock_ui.button.return_value.__enter__ = MagicMock(return_value=mock_button)
    mock_ui.button.return_value.__exit__ = MagicMock()
    
    mock_timer = MagicMock()
    mock_ui.timer.return_value = mock_timer
    
    # Call render_header
    render_header()
    
    # Verify UI elements were created
    assert mock_ui.header.called
    assert mock_ui.row.called
    assert mock_uic.icon.called
    assert mock_ui.label.called
    # Timer for status updates
    assert mock_ui.timer.called
    # Timer for time updates
    assert mock_ui.timer.call_count == 2


if __name__ == "__main__":
    pytest.main([__file__])