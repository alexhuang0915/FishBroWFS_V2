"""Test wizard strategy universe alignment with real strategies (S1/S2/S3 only)."""
import pytest
from unittest.mock import patch, MagicMock, call

# Import the wizard module (src already added to sys.path by conftest)
from gui.nicegui.pages.wizard import render
from gui.nicegui.services.strategy_catalog_service import (
    StrategyCatalogService,
    list_real_strategy_ids,
    get_strategy_catalog_service,
)


class TestWizardStrategyUniverse:
    """Test that wizard uses real strategies only."""
    
    def test_strategy_catalog_service_returns_only_s1_s2_s3(self):
        """Verify the strategy catalog service filters to S1/S2/S3."""
        service = StrategyCatalogService()
        strategies = service.get_real_strategies()
        strategy_ids = [s.strategy_id for s in strategies]
        assert set(strategy_ids) == {"S1", "S2", "S3"}
        assert len(strategy_ids) == 3
    
    def test_list_real_strategy_ids(self):
        """Public API returns sorted S1/S2/S3."""
        ids = list_real_strategy_ids()
        assert ids == ["S1", "S2", "S3"]
    
    @patch("gui.nicegui.pages.wizard.list_real_strategy_ids")
    def test_wizard_calls_real_strategy_ids(self, mock_list_ids):
        """Wizard render calls list_real_strategy_ids to populate checkboxes."""
        # Mock the return value
        mock_list_ids.return_value = ["S1", "S2", "S3"]
        # Mock UI components to avoid AttributeError
        with patch("gui.nicegui.pages.wizard.ui") as mock_ui:
            # Create a mock that has a classes method returning itself
            mock_label = MagicMock()
            mock_label.classes = MagicMock(return_value=mock_label)
            mock_ui.label.return_value = mock_label
            mock_ui.stepper.return_value.__enter__.return_value = MagicMock()
            mock_ui.step.return_value.__enter__.return_value = MagicMock()
            mock_ui.column.return_value.__enter__.return_value = MagicMock()
            mock_ui.row.return_value.__enter__.return_value = MagicMock()
            mock_ui.textarea.return_value = MagicMock()
            mock_ui.radio.return_value = MagicMock()
            mock_ui.stepper_navigation.return_value.__enter__.return_value = MagicMock()
            
            with patch("gui.nicegui.pages.wizard.uic") as mock_uic:
                mock_checkbox = MagicMock()
                mock_checkbox.value = False
                mock_checkbox.on = MagicMock()
                mock_uic.checkbox.return_value = mock_checkbox
                mock_uic.select.return_value = MagicMock()
                mock_uic.input_number.return_value = MagicMock()
                mock_uic.input_text.return_value = MagicMock()
                mock_uic.button.return_value = MagicMock()
                
                # Also mock render_card and other imports
                with patch("gui.nicegui.pages.wizard.render_card") as mock_render_card:
                    mock_render_card.return_value = MagicMock()
                    with patch("gui.nicegui.pages.wizard.show_toast"):
                        with patch("gui.nicegui.pages.wizard.WizardState") as mock_state_cls:
                            # Create a mock state with proper attributes
                            mock_state = MagicMock()
                            mock_state.run_mode = "LITE"
                            mock_state.timeframe = "60m"
                            mock_state.instrument = "MNQ"
                            mock_state.regime_filters = []
                            mock_state.regime_none = False
                            mock_state.long_strategies = []
                            mock_state.short_strategies = []
                            mock_state.compute_level = "MID"
                            mock_state.max_combinations = 1000
                            mock_state.margin_model = "Symbolic"
                            mock_state.contract_specs = {}
                            mock_state.risk_budget = "MEDIUM"
                            mock_state.estimated_combinations = 0
                            mock_state.risk_class = "LOW"
                            mock_state.execution_plan = None
                            mock_state.current_step = 1
                            mock_state.to_intent_dict.return_value = {}
                            mock_state.reset.return_value = None
                            mock_state_cls.return_value = mock_state
                            
                            with patch("gui.nicegui.pages.wizard.AppState") as mock_app_state:
                                mock_app_state.get.return_value = MagicMock()
                                # Mock json.dumps to avoid serialization error
                                with patch("json.dumps") as mock_dumps:
                                    mock_dumps.return_value = "{}"
                                    # Call render
                                    render()
        
        # Verify list_real_strategy_ids was called
        mock_list_ids.assert_called()
    
    def test_wizard_state_accepts_real_strategy_ids(self):
        """WizardState can store real strategy IDs."""
        from gui.nicegui.state.wizard_state import WizardState
        state = WizardState()
        state.long_strategies = ["S1", "S3"]
        state.short_strategies = ["S2"]
        assert state.long_strategies == ["S1", "S3"]
        assert state.short_strategies == ["S2"]
        
        # Convert to intent dict
        intent_dict = state.to_intent_dict()
        assert intent_dict["strategy_space"]["long"] == ["S1", "S3"]
        assert intent_dict["strategy_space"]["short"] == ["S2"]
    
    def test_no_placeholder_strategy_ids_in_catalog(self):
        """Ensure placeholder IDs (L1..L10, S4..S10) are not in real strategy list."""
        real_ids = list_real_strategy_ids()
        # Real strategies are S1, S2, S3; they are allowed.
        # Placeholder long strategies L1..L10 should not appear.
        placeholder_long = [f"L{i}" for i in range(1, 11)]
        # Placeholder short strategies S4..S10 should not appear.
        placeholder_short = [f"S{i}" for i in range(4, 11)]
        for pid in placeholder_long + placeholder_short:
            assert pid not in real_ids, f"Placeholder {pid} should not be in real strategies"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])