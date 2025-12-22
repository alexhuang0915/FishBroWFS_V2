
"""Strategy system.

Phase 7: Strategy registry, runner, and built-in strategies.
"""

from FishBroWFS_V2.strategy.registry import (
    register,
    get,
    list_strategies,
    load_builtin_strategies,
)
from FishBroWFS_V2.strategy.runner import run_strategy
from FishBroWFS_V2.strategy.spec import StrategySpec, StrategyFn

__all__ = [
    "register",
    "get",
    "list_strategies",
    "load_builtin_strategies",
    "run_strategy",
    "StrategySpec",
    "StrategyFn",
]


