"""Test UI Prune to Minimum Honest UI.

Tests for the UI capabilities system and tab filtering according to
Minimum Honest UI specification.
"""
import pytest
from src.gui.nicegui.services.ui_capabilities import (
    UICapabilities,
    get_ui_capabilities,
)
from src.gui.nicegui.layout.tabs import TAB_IDS, _CAPS


class TestUICapabilities:
    """Test UICapabilities dataclass and default values."""
    
    def test_default_capabilities_match_minimum_honest_ui(self):
        """Default capabilities should reflect Minimum Honest UI scope."""
        caps = get_ui_capabilities()
        
        # Core truthful sections (always enabled in Minimum Honest UI)
        assert caps.enable_dashboard is True
        assert caps.enable_wizard is True
        assert caps.enable_history is True
        assert caps.enable_settings is True
        
        # Non‑core sections (disabled by default)
        assert caps.enable_candidates is False
        assert caps.enable_portfolio is False
        assert caps.enable_deploy is False
        
        # Hidden forensic page (always accessible via direct URL)
        assert caps.enable_forensics is True
    
    def test_capabilities_to_dict(self):
        """Test conversion to dictionary."""
        caps = UICapabilities(
            enable_dashboard=True,
            enable_wizard=False,
            enable_history=True,
            enable_settings=False,
            enable_candidates=True,
            enable_portfolio=False,
            enable_deploy=True,
            enable_forensics=True,
        )
        
        data = caps.to_dict()
        
        assert data["enable_dashboard"] is True
        assert data["enable_wizard"] is False
        assert data["enable_history"] is True
        assert data["enable_settings"] is False
        assert data["enable_candidates"] is True
        assert data["enable_portfolio"] is False
        assert data["enable_deploy"] is True
        assert data["enable_forensics"] is True
    
    def test_capabilities_from_dict(self):
        """Test creation from dictionary."""
        data = {
            "enable_dashboard": False,
            "enable_wizard": True,
            "enable_history": False,
            "enable_settings": True,
            "enable_candidates": False,
            "enable_portfolio": True,
            "enable_deploy": False,
            "enable_forensics": False,
        }
        
        caps = UICapabilities.from_dict(data)
        
        assert caps.enable_dashboard is False
        assert caps.enable_wizard is True
        assert caps.enable_history is False
        assert caps.enable_settings is True
        assert caps.enable_candidates is False
        assert caps.enable_portfolio is True
        assert caps.enable_deploy is False
        assert caps.enable_forensics is False
    
    def test_capabilities_are_frozen(self):
        """UICapabilities should be frozen (immutable)."""
        caps = get_ui_capabilities()
        
        # Attempting to modify attributes should raise AttributeError
        with pytest.raises(AttributeError):
            caps.enable_dashboard = False
        
        with pytest.raises(AttributeError):
            caps.enable_candidates = True


class TestTabFiltering:
    """Test that tabs are filtered according to capabilities."""
    
    def test_tab_ids_filtered_by_default_capabilities(self):
        """TAB_IDS should only contain enabled tabs."""
        # Get the global _CAPS used in tabs.py
        from src.gui.nicegui.layout.tabs import _CAPS
        
        # With default capabilities, only dashboard, wizard, history, settings should be present
        expected_tabs = []
        if _CAPS.enable_dashboard:
            expected_tabs.append("dashboard")
        if _CAPS.enable_wizard:
            expected_tabs.append("wizard")
        if _CAPS.enable_history:
            expected_tabs.append("history")
        if _CAPS.enable_candidates:
            expected_tabs.append("candidates")
        if _CAPS.enable_portfolio:
            expected_tabs.append("portfolio")
        if _CAPS.enable_deploy:
            expected_tabs.append("deploy")
        if _CAPS.enable_settings:
            expected_tabs.append("settings")
        
        assert TAB_IDS == expected_tabs
        
        # With default capabilities, candidates, portfolio, deploy should NOT be present
        assert "candidates" not in TAB_IDS
        assert "portfolio" not in TAB_IDS
        assert "deploy" not in TAB_IDS
        
        # Core tabs should be present
        assert "dashboard" in TAB_IDS
        assert "wizard" in TAB_IDS
        assert "history" in TAB_IDS
        assert "settings" in TAB_IDS
    
    def test_tab_labels_and_icons_match_filtered_tabs(self):
        """TAB_LABELS and TAB_ICONS should only contain entries for enabled tabs."""
        from src.gui.nicegui.layout.tabs import TAB_LABELS, TAB_ICONS
        
        # All tab IDs in TAB_LABELS and TAB_ICONS should be in TAB_IDS
        for tab_id in TAB_LABELS:
            assert tab_id in TAB_IDS
        
        for tab_id in TAB_ICONS:
            assert tab_id in TAB_IDS
        
        # All tab IDs in TAB_IDS should have labels and icons
        for tab_id in TAB_IDS:
            assert tab_id in TAB_LABELS
            assert tab_id in TAB_ICONS


class TestMinimumHonestUIScope:
    """Test that Minimum Honest UI scope is correctly implemented."""
    
    def test_core_tabs_are_truthful(self):
        """Core tabs (Dashboard, Wizard, History, Settings) should be enabled."""
        caps = get_ui_capabilities()
        
        # These are the "fully truthful" sections per spec
        assert caps.enable_dashboard is True, "Dashboard must be enabled (truthful)"
        assert caps.enable_wizard is True, "Wizard must be enabled (truthful)"
        assert caps.enable_history is True, "History must be enabled (truthful)"
        assert caps.enable_settings is True, "Settings must be enabled (truthful)"
    
    def test_non_core_tabs_are_disabled_by_default(self):
        """Non‑core tabs should be disabled by default (read‑only/minimal)."""
        caps = get_ui_capabilities()
        
        # These are "read‑only/minimal" per spec
        assert caps.enable_candidates is False, "Candidates should be disabled by default"
        assert caps.enable_portfolio is False, "Portfolio should be disabled by default"
        assert caps.enable_deploy is False, "Deploy should be disabled by default"
    
    def test_forensics_page_always_accessible(self):
        """Forensics page should always be accessible via direct URL."""
        caps = get_ui_capabilities()
        assert caps.enable_forensics is True, "Forensics should be accessible"


def test_ui_capabilities_module_exists():
    """Smoke test that the ui_capabilities module can be imported."""
    from src.gui.nicegui.services import ui_capabilities
    assert ui_capabilities is not None
    assert hasattr(ui_capabilities, "UICapabilities")
    assert hasattr(ui_capabilities, "get_ui_capabilities")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])