"""
Wizard Engine Contracts (v1.8) - SSOT for guided workflow engine.

These contracts define the wizard state, steps, actions, and results for the
Wizard Engine v1.8 (MVP: Run Job Wizard + Gate Fix Wizard).

Key Principles:
1. Pure Pydantic models (no UI imports)
2. Frozen configuration (immutable after creation)
3. Zero-silent validation (every blocked action has reason_code → explain)
4. Reuse v1.7 UI governance state + v1.4 explain dictionary
"""

from .wizard_steps import WizardStep
from .wizard_state import WizardState, WizardValidationResult
from .wizard_actions import WizardAction, WizardActionDecision
from .wizard_results import WizardResult, WizardJobResult, WizardGateFixResult

__all__ = [
    "WizardStep",
    "WizardState",
    "WizardValidationResult",
    "WizardAction",
    "WizardActionDecision",
    "WizardResult",
    "WizardJobResult",
    "WizardGateFixResult",
]