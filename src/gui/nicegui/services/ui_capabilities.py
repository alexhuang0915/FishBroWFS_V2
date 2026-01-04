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
    
    Default values reflect the Phase 11-12 Constitution:
    - OP, Registry, Allocation, Audit: constitution-mandated tabs
    """
    # Constitution-mandated tabs (Phase 11-12)
    enable_op: bool = True  # OP tab (Operator Console)
    enable_registry: bool = True  # Registry tab (Strategy Inventory)
    enable_allocation: bool = True  # Allocation tab (Read-only)
    enable_audit: bool = True  # Audit tab (Historian)
    
    # Legacy tabs (disabled in Phase 11-12)
    enable_dashboard: bool = False
    enable_wizard: bool = False
    enable_history: bool = False
    enable_candidates: bool = False
    enable_portfolio: bool = False
    enable_deploy: bool = False
    enable_settings: bool = False
    
    # Hidden forensic page (always accessible via direct URL)
    enable_forensics: bool = True
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert capabilities to a dictionary for serialization."""
        return {
            "enable_op": self.enable_op,
            "enable_registry": self.enable_registry,
            "enable_allocation": self.enable_allocation,
            "enable_audit": self.enable_audit,
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
    """Return the default UI capabilities for Phase 11-12 Constitution.
    
    This function is the primary API for obtaining the current UI capabilities.
    It returns a UICapabilities instance with the default values that implement
    the Phase 11-12 Constitution requirements.
    
    Returns:
        UICapabilities: Default capabilities with constitution-mandated tabs enabled,
        legacy tabs disabled.
    """
    return UICapabilities(
        enable_op=True,
        enable_registry=True,
        enable_allocation=True,
        enable_audit=True,
        enable_dashboard=False,
        enable_wizard=False,
        enable_history=False,
        enable_settings=False,
        enable_candidates=False,
        enable_portfolio=False,
        enable_deploy=False,
        enable_forensics=True,
    )