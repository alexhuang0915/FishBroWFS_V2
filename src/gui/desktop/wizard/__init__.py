"""
Wizard Engine UI Shell (v1.8) - QStackedWidget-based wizard interface.

This module provides the UI shell for wizard workflows using QStackedWidget
to manage wizard steps with zero-silent validation and action gating.

Key Principles:
1. QStackedWidget for step management
2. Zero-silent UI (every blocked "Next" shows reason_code → explain)
3. Integration with WizardViewModel for business logic
4. Reuse of existing card components from OP tab
"""

from .wizard_dialog import WizardDialog
from .wizard_step_widgets import (
    WizardStepWidget,
    RunJobStepWidget,
    GateFixStepWidget,
    SelectionStepWidget,
    ValidationStepWidget,
    ConfirmationStepWidget,
    ProgressStepWidget,
    CompletionStepWidget,
)
from .wizard_navigation import WizardNavigationBar
from .wizard_validation_banner import WizardValidationBanner

__all__ = [
    "WizardDialog",
    "WizardStepWidget",
    "RunJobStepWidget",
    "GateFixStepWidget",
    "SelectionStepWidget",
    "ValidationStepWidget",
    "ConfirmationStepWidget",
    "ProgressStepWidget",
    "CompletionStepWidget",
    "WizardNavigationBar",
    "WizardValidationBanner",
]