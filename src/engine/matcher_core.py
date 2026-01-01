
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Optional, Tuple

import numpy as np

from engine.engine_types import (
    BarArrays,
    Fill,
    OrderIntent,
    OrderKind,
    OrderRole,
    Side,
)


@dataclass
class PositionState:
    """
    Minimal single-position state for Phase 1 tests.
    pos: 0 = flat, 1 = long, -1 = short
    """
    pos: int = 0


def _is_active(intent: OrderIntent, bar_index: int) -> bool:
    return bar_index == intent.created_bar + 1


def _stop_fill_price(side: Side, stop_price: float, o: float, h: float, l: float) -> Optional[float]:
    # Open==price goes to GAP branch by definition.
    if side == Side.BUY:
        if o >= stop_price:
            return o
        if h >= stop_price:
            return stop_price
        return None
    else:
        if o <= stop_price:
            return o
        if l <= stop_price:
            return stop_price
        return None


def _limit_fill_price(side: Side, limit_price: float, o: float, h: float, l: float) -> Optional[float]:
    # Open==price goes to GAP branch by definition.
    if side == Side.BUY:
        if o <= limit_price:
            return o
        if l <= limit_price:
            return limit_price
        return None
    else:
        if o >= limit_price:
            return o
        if h >= limit_price:
            return limit_price
        return None


def _intent_fill_price(intent: OrderIntent, o: float, h: float, l: float) -> Optional[float]:
    if intent.kind == OrderKind.STOP:
        return _stop_fill_price(intent.side, intent.price, o, h, l)
    return _limit_fill_price(intent.side, intent.price, o, h, l)


def _sort_key(intent: OrderIntent) -> Tuple[int, int, int]:
    """
    Deterministic priority:
    1) Role: EXIT first when selecting within same-stage bucket.
    2) Kind: STOP before LIMIT.
    3) order_id: ascending.
    Note: Entry-vs-Exit ordering is handled at a higher level (Entry then Exit).
    """
    role_rank = 0 if intent.role == OrderRole.EXIT else 1
    kind_rank = 0 if intent.kind == OrderKind.STOP else 1
    return (role_rank, kind_rank, intent.order_id)


def simulate(
    bars: BarArrays,
    intents: Iterable[OrderIntent],
) -> List[Fill]:
    """
    Phase 1 slow reference matcher.

    Rules enforced:
    - next-bar active only (bar_index == created_bar + 1)
    - STOP/LIMIT gap behavior at Open
    - STOP over LIMIT
    - Same-bar Entry then Exit
    - Same-kind tie: EXIT-first, order_id ascending
    """
    o = bars.open
    h = bars.high
    l = bars.low
    n = int(o.shape[0])

    intents_list = list(intents)
    fills: List[Fill] = []
    state = PositionState(pos=0)

    for t in range(n):
        ot = float(o[t])
        ht = float(h[t])
        lt = float(l[t])

        active = [x for x in intents_list if _is_active(x, t)]
        if not active:
            continue

        # Partition by role for same-bar entry then exit.
        entry_intents = [x for x in active if x.role == OrderRole.ENTRY]
        exit_intents = [x for x in active if x.role == OrderRole.EXIT]

        # Stage 1: ENTRY stage
        if entry_intents:
            # Among entries: STOP before LIMIT, then order_id.
            entry_sorted = sorted(entry_intents, key=lambda x: (0 if x.kind == OrderKind.STOP else 1, x.order_id))
            for it in entry_sorted:
                if state.pos != 0:
                    break  # single-position only
                px = _intent_fill_price(it, ot, ht, lt)
                if px is None:
                    continue
                fills.append(
                    Fill(
                        bar_index=t,
                        role=it.role,
                        kind=it.kind,
                        side=it.side,
                        price=float(px),
                        qty=int(it.qty),
                        order_id=int(it.order_id),
                    )
                )
                # Apply position change
                if it.side == Side.BUY:
                    state.pos = 1
                else:
                    state.pos = -1
                break  # at most one entry fill per bar in Phase 1 reference

        # Stage 2: EXIT stage (after entry)
        if exit_intents and state.pos != 0:
            # Same-kind tie rule: EXIT-first already, and STOP before LIMIT, then order_id
            exit_sorted = sorted(exit_intents, key=_sort_key)
            for it in exit_sorted:
                # Only allow exits that reduce/close current position in this minimal model:
                # long exits are SELL, short exits are BUY.
                if state.pos == 1 and it.side != Side.SELL:
                    continue
                if state.pos == -1 and it.side != Side.BUY:
                    continue

                px = _intent_fill_price(it, ot, ht, lt)
                if px is None:
                    continue
                fills.append(
                    Fill(
                        bar_index=t,
                        role=it.role,
                        kind=it.kind,
                        side=it.side,
                        price=float(px),
                        qty=int(it.qty),
                        order_id=int(it.order_id),
                    )
                )
                state.pos = 0
                break  # at most one exit fill per bar in Phase 1 reference

    return fills



