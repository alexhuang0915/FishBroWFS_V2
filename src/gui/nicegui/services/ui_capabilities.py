"""UI Capabilities for Minimum Honest UI.

This module defines which UI sections are enabled/disabled according to the
"Minimum Honest UI" principle. The UI should only show tabs and features that
are fully truthful and implemented.

Capabilities are used to conditionally render tabs and page content.
"""
from dataclasses import dataclass
from typing import Dict, Any


@dataclass(frozen=True)
class UICapabilities:
    """Boolean flags for all UI sections.
    
    A flag set to True means the corresponding UI section is enabled and
    should be rendered. False means the section is disabled and should not
    appear in the UI at all (or should show a "not implemented" message).
    
    Default values reflect the "Minimum Honest UI" scope:
    - Dashboard, Wizard, History, Settings: fully truthful, enabled
    - Candidates, Portfolio, Deploy: read‑only/minimal, disabled by default
    """
    # Core truthful sections (always enabled in Minimum Honest UI)
    enable_dashboard: bool = True
    enable_wizard: bool = True
    enable_history: bool = True
    enable_settings: bool = True
    
    # Non‑core sections (disabled by default; can be shown as read‑only)
    enable_candidates: bool = False
    enable_portfolio: bool = False
    enable_deploy: bool = False
    
    # Hidden forensic page (always accessible via direct URL)
    enable_forensics: bool = True
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert capabilities to a dictionary for serialization."""
        return {
            "enable_dashboard": self.enable_dashboard,
            "enable_wizard": self.enable_wizard,
            "enable_history": self.enable_history,
            "enable_settings": self.enable_settings,
            "enable_candidates": self.enable_candidates,
            "enable_portfolio": self.enable_portfolio,
            "enable_deploy": self.enable_deploy,
            "enable_forensics": self.enable_forensics,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "UICapabilities":
        """Create capabilities from a dictionary."""
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


def get_ui_capabilities() -> UICapabilities:
    """Return the default UI capabilities for Minimum Honest UI.
    
    This function is the primary API for obtaining the current UI capabilities.
    It returns a UICapabilities instance with the default values that implement
    the "Minimum Honest UI" scope.
    
    Returns:
        UICapabilities: Default capabilities with truthful sections enabled,
        non‑core sections disabled.
    """
    return UICapabilities(
        enable_dashboard=True,
        enable_wizard=True,
        enable_history=True,
        enable_settings=True,
        enable_candidates=False,
        enable_portfolio=False,
        enable_deploy=False,
        enable_forensics=True,
    )