"""Unit tests for Wizard intent preview and step gating."""
import pytest
from unittest.mock import patch, MagicMock, call
from gui.nicegui.pages.wizard import render
from gui.nicegui.state.wizard_state import WizardState
from gui.nicegui.state.app_state import AppState


@patch("gui.nicegui.pages.wizard.ui")
@patch("gui.nicegui.pages.wizard.uic")
@patch("gui.nicegui.pages.wizard.render_card")
@patch("gui.nicegui.pages.wizard.show_toast")
@patch("gui.nicegui.pages.wizard.write_intent")
@patch("gui.nicegui.pages.wizard.validate_intent")
@patch("gui.nicegui.pages.wizard.derive_and_write")
def test_wizard_renders_intent_preview(
    mock_derive,
    mock_validate,
    mock_write,
    mock_show_toast,
    mock_render_card,
    mock_uic,
    mock_ui,
):
    """Wizard page renders and includes intent preview textarea."""
    # Mock UI components
    mock_stepper = MagicMock()
    mock_stepper.__enter__ = MagicMock(return_value=mock_stepper)
    mock_stepper.__exit__ = MagicMock()
    mock_ui.stepper.return_value = mock_stepper
    
    mock_step = MagicMock()
    mock_step.__enter__ = MagicMock(return_value=mock_step)
    mock_step.__exit__ = MagicMock()
    mock_ui.step.return_value = mock_step
    
    mock_stepper_nav = MagicMock()
    mock_stepper_nav.__enter__ = MagicMock(return_value=mock_stepper_nav)
    mock_stepper_nav.__exit__ = MagicMock()
    mock_ui.stepper_navigation.return_value = mock_stepper_nav
    
    mock_label = MagicMock()
    mock_ui.label.return_value = mock_label
    
    mock_radio = MagicMock()
    mock_ui.radio.return_value = mock_radio
    
    mock_row = MagicMock()
    mock_row.__enter__ = MagicMock(return_value=mock_row)
    mock_row.__exit__ = MagicMock()
    mock_ui.row.return_value = mock_row
    
    mock_column = MagicMock()
    mock_column.__enter__ = MagicMock(return_value=mock_column)
    mock_column.__exit__ = MagicMock()
    mock_ui.column.return_value = mock_column
    
    mock_textarea = MagicMock()
    mock_ui.textarea.return_value = mock_textarea
    
    # Mock ui_compat components
    mock_button = MagicMock()
    mock_select = MagicMock()
    mock_checkbox = MagicMock()
    mock_input_number = MagicMock()
    mock_input_text = MagicMock()
    mock_uic.button.return_value = mock_button
    mock_uic.select.return_value = mock_select
    mock_uic.checkbox.return_value = mock_checkbox
    mock_uic.input_number.return_value = mock_input_number
    mock_uic.input_text.return_value = mock_input_text
    
    # Mock render_card
    mock_card = MagicMock()
    mock_card.content = ""
    mock_render_card.return_value = mock_card
    
    # Mock validate_intent to return valid
    mock_validate.return_value = (True, [])
    
    # Mock state
    with patch.object(WizardState, "__init__", lambda self: None):
        state = WizardState()
        state.run_mode = "SMOKE"
        state.timeframe = "30m"
        state.instrument = "MNQ"
        state.regime_none = False
        state.regime_filters = []
        state.long_strategies = []
        state.short_strategies = []
        state.compute_level = "LOW"
        state.max_combinations = 1000
        state.margin_model = "symbolic"
        state.contract_specs = {}
        state.risk_budget = "medium"
        state.estimated_combinations = 240
        state.risk_class = "MEDIUM"
        state.to_intent_dict = MagicMock(return_value={"test": "intent"})
        state.reset = MagicMock()
    
    with patch.object(AppState, "get", return_value=MagicMock(season="2026Q1")):
        # Call render
        render()
    
    # Verify UI components created
    assert mock_ui.stepper.called
    assert mock_ui.textarea.called  # intent preview textarea
    # Ensure preview update logic triggered
    # (mock_textarea.value should have been set)
    # The actual value is set inside update_preview, which is called after render.
    # We'll just verify that textarea mock was called.
    
    # Verify validation called
    mock_validate.assert_called()


def test_wizard_step_gating():
    """Step navigation respects required fields."""
    # This test can be expanded later; for now just a placeholder
    pass


if __name__ == "__main__":
    pytest.main([__file__])