
"""Strategy system.

Phase 7: Strategy registry, runner, and built-in strategies.
"""

from strategy.registry import (
    register,
    get,
    list_strategies,
    load_builtin_strategies,
)
from strategy.runner import run_strategy
from strategy.spec import StrategySpec, StrategyFn

__all__ = [
    "register",
    "get",
    "list_strategies",
    "load_builtin_strategies",
    "run_strategy",
    "StrategySpec",
    "StrategyFn",
]


