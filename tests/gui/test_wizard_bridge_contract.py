"""
Tests for WizardBridge contract enforcement.

WizardBridge MUST be the ONLY dependency entrypoint for wizard pages.
This test ensures:
1. WizardBridge validates required functions
2. Wizard pages import WizardBridge correctly
3. No direct migrate_ui_imports() usage in wizard pages
4. Graceful degradation on missing functions
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
import sys
import importlib

from FishBroWFS_V2.gui.nicegui.bridge.wizard_bridge import (
    WizardBridge,
    WizardBridgeError,
    WizardBridgeDiagnostics,
    get_wizard_bridge,
)


class TestWizardBridgeContract:
    """Test WizardBridge contract enforcement."""

    def test_wizard_bridge_creation_with_missing_funcs(self):
        """WizardBridge must raise WizardBridgeError when required functions are missing."""
        # Missing required functions
        funcs = {
            "get_dataset_catalog": None,  # Not callable
            # Missing get_strategy_catalog entirely
        }
        
        with pytest.raises(WizardBridgeError) as exc_info:
            WizardBridge(funcs)
        
        assert "missing" in str(exc_info.value).lower()
        assert "get_strategy_catalog" in str(exc_info.value)

    def test_wizard_bridge_creation_with_valid_funcs(self):
        """WizardBridge must accept valid callables for required functions."""
        funcs = {
            "get_dataset_catalog": Mock(return_value={"dataset1": "Dataset 1"}),
            "get_strategy_catalog": Mock(return_value={"strategy1": "Strategy 1"}),
        }
        
        bridge = WizardBridge(funcs)
        diag = bridge.diagnostics()
        
        assert diag.ok is True
        assert diag.missing == ()
        assert "get_dataset_catalog" in diag.available
        assert "get_strategy_catalog" in diag.available

    def test_wizard_bridge_get_dataset_options(self):
        """get_dataset_options must return deterministic list of (value, label) tuples."""
        # Mock catalog with various shapes
        mock_catalog = {
            "dataset1": {"id": "dataset1", "symbol": "MNQ", "timeframe": "60m"},
            "dataset2": {"id": "dataset2", "symbol": "MXF", "timeframe": "120m"},
        }
        
        funcs = {
            "get_dataset_catalog": Mock(return_value=mock_catalog),
            "get_strategy_catalog": Mock(return_value={}),
        }
        
        bridge = WizardBridge(funcs)
        options = bridge.get_dataset_options()
        
        # Should return sorted list of (id, id) tuples
        assert isinstance(options, list)
        assert len(options) == 2
        assert options[0] == ("dataset1", "dataset1")
        assert options[1] == ("dataset2", "dataset2")

    def test_wizard_bridge_get_dataset_options_empty_on_error(self):
        """get_dataset_options must return [] on error and log exception."""
        funcs = {
            "get_dataset_catalog": Mock(side_effect=RuntimeError("Catalog unavailable")),
            "get_strategy_catalog": Mock(return_value={}),
        }
        
        bridge = WizardBridge(funcs)
        options = bridge.get_dataset_options()
        
        assert options == []

    def test_wizard_bridge_get_strategy_options(self):
        """get_strategy_options must return deterministic list of (value, label) tuples."""
        mock_catalog = {
            "strategy1": {"id": "strategy1", "name": "Momentum"},
            "strategy2": {"id": "strategy2", "name": "Mean Reversion"},
        }
        
        funcs = {
            "get_dataset_catalog": Mock(return_value={}),
            "get_strategy_catalog": Mock(return_value=mock_catalog),
        }
        
        bridge = WizardBridge(funcs)
        options = bridge.get_strategy_options()
        
        assert isinstance(options, list)
        assert len(options) == 2
        assert options[0] == ("strategy1", "strategy1")
        assert options[1] == ("strategy2", "strategy2")

    def test_wizard_bridge_extract_ids_heuristic(self):
        """_extract_ids must handle various catalog shapes."""
        # Test dict mapping
        catalog_dict = {"id1": "obj1", "id2": "obj2"}
        ids = WizardBridge._extract_ids(catalog_dict)
        assert set(ids) == {"id1", "id2"}
        
        # Test object with .datasets attribute
        class MockCatalog:
            datasets = {"ds1": {}, "ds2": {}}
        
        ids = WizardBridge._extract_ids(MockCatalog())
        assert set(ids) == {"ds1", "ds2"}
        
        # Test object with .items() method
        class MockCatalog2:
            def items(self):
                return [("key1", "val1"), ("key2", "val2")]
        
        ids = WizardBridge._extract_ids(MockCatalog2())
        # Note: _extract_ids doesn't handle .items() method directly
        # It only handles dict-like objects with .keys() or dict mapping
        # So this should return empty list
        assert ids == []
        
        # Test list of descriptors with .id attribute inside an object
        class MockDescriptor:
            def __init__(self, id_):
                self.id = id_
        
        class MockCatalogWithDatasets:
            datasets = [MockDescriptor("a"), MockDescriptor("b")]
        
        ids = WizardBridge._extract_ids(MockCatalogWithDatasets())
        assert set(ids) == {"a", "b"}
        
        # Test None returns empty list
        assert WizardBridge._extract_ids(None) == []

    def test_get_wizard_bridge_graceful_degradation(self):
        """get_wizard_bridge must return minimal bridge on creation failure."""
        with patch.object(WizardBridge, 'create_default', side_effect=WizardBridgeError("Test error")):
            bridge = get_wizard_bridge()
            
            # Should return a WizardBridge instance with empty funcs
            assert isinstance(bridge, WizardBridge)
            # Bridge should have empty funcs dict
            assert bridge._funcs == {}


class TestWizardPagesImportContract:
    """Test that wizard pages follow import contract."""
    
    def test_wizard_py_imports_wizard_bridge_only(self):
        """wizard.py must import WizardBridge and not migrate_ui_imports directly."""
        # Read the wizard.py file
        import os
        wizard_path = os.path.join(
            os.path.dirname(__file__), 
            "..", "..", "src", "FishBroWFS_V2", "gui", "nicegui", "pages", "wizard.py"
        )
        
        with open(wizard_path, 'r') as f:
            content = f.read()
        
        # Must import WizardBridge
        assert "from FishBroWFS_V2.gui.nicegui.bridge.wizard_bridge import" in content
        # Must NOT call migrate_ui_imports() directly (except in docstring/comments)
        # Check that migrate_ui_imports is not called as a function in code
        lines = content.split('\n')
        in_docstring = False
        for line in lines:
            line_stripped = line.strip()
            if line_stripped.startswith('"""') or line_stripped.startswith("'''"):
                in_docstring = not in_docstring
                continue
            if not in_docstring and not line_stripped.startswith('#'):
                # This is actual code (not docstring, not comment)
                if "migrate_ui_imports()" in line:
                    pytest.fail(f"Found direct migrate_ui_imports() call in wizard.py: {line}")
        # Must use _wizard_bridge instance
        assert "_wizard_bridge = get_wizard_bridge()" in content

    def test_wizard_m1_py_imports_wizard_bridge_only(self):
        """wizard_m1.py must import WizardBridge and not migrate_ui_imports directly."""
        import os
        wizard_m1_path = os.path.join(
            os.path.dirname(__file__),
            "..", "..", "src", "FishBroWFS_V2", "gui", "nicegui", "pages", "wizard_m1.py"
        )
        
        with open(wizard_m1_path, 'r') as f:
            content = f.read()
        
        # Must import WizardBridge
        assert "from FishBroWFS_V2.gui.nicegui.bridge.wizard_bridge import" in content
        # Must NOT call migrate_ui_imports() directly (except in docstring/comments)
        # Check that migrate_ui_imports is not called as a function in code
        lines = content.split('\n')
        in_docstring = False
        for line in lines:
            line_stripped = line.strip()
            if line_stripped.startswith('"""') or line_stripped.startswith("'''"):
                in_docstring = not in_docstring
                continue
            if not in_docstring and not line_stripped.startswith('#'):
                # This is actual code (not docstring, not comment)
                if "migrate_ui_imports()" in line:
                    pytest.fail(f"Found direct migrate_ui_imports() call in wizard_m1.py: {line}")
        # Must use _wizard_bridge instance
        assert "_wizard_bridge = get_wizard_bridge()" in content


class TestWizardBridgeIntegration:
    """Integration tests for WizardBridge with actual UI bridge."""
    
    @pytest.fixture
    def mock_migrate_ui_imports(self):
        """Mock migrate_ui_imports to return required functions."""
        mock_funcs = {
            "get_dataset_catalog": Mock(return_value={"dataset1": "Dataset 1"}),
            "get_strategy_catalog": Mock(return_value={"strategy1": "Strategy 1"}),
            "calculate_units": Mock(return_value=42),
            "check_season_not_frozen": Mock(),
            "create_job_from_wizard": Mock(return_value={"job_id": "test_job"}),
            "get_descriptor": Mock(return_value=None),
        }
        
        def mock_migrate(globals_dict):
            globals_dict.update(mock_funcs)
        
        # Patch migrate_ui_imports in the ui_bridge module where it's imported from
        with patch('FishBroWFS_V2.gui.adapters.ui_bridge.migrate_ui_imports',
                  side_effect=mock_migrate):
            yield mock_funcs
    
    def test_wizard_bridge_create_default_with_mock(self, mock_migrate_ui_imports):
        """WizardBridge.create_default must work with mocked migrate_ui_imports."""
        bridge = WizardBridge.create_default()
        
        assert isinstance(bridge, WizardBridge)
        diag = bridge.diagnostics()
        assert diag.ok is True
        
        # Should have all required functions
        assert bridge.has_function("get_dataset_catalog")
        assert bridge.has_function("get_strategy_catalog")
        
        # Test dataset options
        options = bridge.get_dataset_options()
        assert isinstance(options, list)
        
        # Test strategy options
        options = bridge.get_strategy_options()
        assert isinstance(options, list)
        
        # Test function access
        calc_func = bridge.get_function("calculate_units")
        assert calc_func is not None
        assert calc_func() == 42

    def test_wizard_bridge_missing_required_funcs_in_mock(self):
        """WizardBridge.create_default must raise when migrate_ui_imports provides incomplete funcs."""
        def mock_migrate_incomplete(globals_dict):
            # Only provide one required function
            globals_dict.update({
                "get_dataset_catalog": Mock(),
                # Missing get_strategy_catalog
            })
        
        with patch('FishBroWFS_V2.gui.adapters.ui_bridge.migrate_ui_imports',
                  side_effect=mock_migrate_incomplete):
            with pytest.raises(WizardBridgeError) as exc_info:
                WizardBridge.create_default()
            
            assert "missing" in str(exc_info.value).lower()
            assert "get_strategy_catalog" in str(exc_info.value)


def test_regression_wizard_page_import_no_nameerror():
    """Regression: Importing wizard page must not raise NameError."""
    # This test ensures the fix for "whack-a-mole" NameErrors
    try:
        # Try to import wizard page
        import FishBroWFS_V2.gui.nicegui.pages.wizard as wizard_module
        # If import succeeds, we're good
        assert wizard_module is not None
    except NameError as e:
        pytest.fail(f"Wizard page import raised NameError: {e}")
    except ImportError as e:
        # Allow other import errors (missing dependencies)
        pass


if __name__ == "__main__":
    pytest.main([__file__, "-v"])