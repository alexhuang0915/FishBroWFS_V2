"""
Phase 4-C: Titanium Master Deployment - Switch-Case Master Wrapper Generator

This module implements the generator that merges multiple standalone PowerLanguage
strategies into a single Master .el file controlled by i_Strategy_ID and i_Lots.

Key Features:
- AST-level transformation with variable hoisting and namespace isolation
- Strict validation against forbidden constructs (Set* syntax, IOG, etc.)
- Automatic splitting for >50 strategies
- MaxBarsBack calculation
- Output to outputs/jobs/<DEPLOY_ID>/deployments/
"""

from .generator import (
    PowerLanguageStrategy,
    MasterWrapperGenerator,
    generate_master_wrapper,
    validate_strategy,
    parse_powerlanguage,
)

__all__ = [
    "PowerLanguageStrategy",
    "MasterWrapperGenerator",
    "generate_master_wrapper",
    "validate_strategy",
    "parse_powerlanguage",
]

__version__ = "1.0.0"