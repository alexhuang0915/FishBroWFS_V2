from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import List, Optional

import numpy as np


@dataclass(frozen=True)
class BarArrays:
    open: np.ndarray
    high: np.ndarray
    low: np.ndarray
    close: np.ndarray


class Side(int, Enum):
    BUY = 1
    SELL = -1


class OrderKind(str, Enum):
    STOP = "STOP"
    LIMIT = "LIMIT"


class OrderRole(str, Enum):
    ENTRY = "ENTRY"
    EXIT = "EXIT"


@dataclass(frozen=True)
class OrderIntent:
    """
    Order intent created at bar `created_bar` and becomes active at bar `created_bar + 1`.
    Deterministic ordering is controlled via `order_id` (smaller = earlier).
    """
    order_id: int
    created_bar: int
    role: OrderRole
    kind: OrderKind
    side: Side
    price: float
    qty: int = 1


@dataclass(frozen=True)
class Fill:
    bar_index: int
    role: OrderRole
    kind: OrderKind
    side: Side
    price: float
    qty: int
    order_id: int


@dataclass(frozen=True)
class SimResult:
    """
    Simulation result from simulate_run().
    
    This is the standard return type for Phase 4 unified simulate entry point.
    """
    fills: List[Fill]

