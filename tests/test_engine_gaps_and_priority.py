
import numpy as np

from FishBroWFS_V2.data.layout import normalize_bars
from FishBroWFS_V2.engine.matcher_core import simulate
from FishBroWFS_V2.engine.types import OrderIntent, OrderKind, OrderRole, Side


def _bars1(o, h, l, c):
    return normalize_bars(
        np.array([o], dtype=np.float64),
        np.array([h], dtype=np.float64),
        np.array([l], dtype=np.float64),
        np.array([c], dtype=np.float64),
    )


def test_tc04_buy_limit_gap_down_better_fill_open():
    bars = _bars1(90, 95, 85, 92)
    intents = [
        OrderIntent(order_id=1, created_bar=-1, role=OrderRole.ENTRY, kind=OrderKind.LIMIT, side=Side.BUY, price=100.0),
    ]
    fills = simulate(bars, intents)
    assert len(fills) == 1
    assert fills[0].price == 90.0


def test_tc05_sell_limit_gap_up_better_fill_open():
    bars = _bars1(105, 110, 100, 108)
    intents = [
        OrderIntent(order_id=1, created_bar=-1, role=OrderRole.ENTRY, kind=OrderKind.LIMIT, side=Side.SELL, price=100.0),
    ]
    fills = simulate(bars, intents)
    assert len(fills) == 1
    assert fills[0].price == 105.0


def test_tc06_priority_stop_wins_over_limit_on_exit():
    # First enter long on this same bar, then exit on next bar where both stop and limit are triggerable.
    # Bar0: enter long at 100 (buy stop hits)
    # Bar1: both exit stop 90 and exit limit 110 are touchable (high=110, low=80), STOP must win (fill=90)
    bars = normalize_bars(
        np.array([100, 100], dtype=np.float64),
        np.array([110, 110], dtype=np.float64),
        np.array([90, 80], dtype=np.float64),
        np.array([100, 90], dtype=np.float64),
    )

    intents = [
        OrderIntent(order_id=1, created_bar=-1, role=OrderRole.ENTRY, kind=OrderKind.STOP, side=Side.BUY, price=100.0),
        OrderIntent(order_id=2, created_bar=0, role=OrderRole.EXIT, kind=OrderKind.STOP, side=Side.SELL, price=90.0),
        OrderIntent(order_id=3, created_bar=0, role=OrderRole.EXIT, kind=OrderKind.LIMIT, side=Side.SELL, price=110.0),
    ]
    fills = simulate(bars, intents)
    assert len(fills) == 2
    # Second fill is exit; STOP wins -> 90
    assert fills[1].kind == OrderKind.STOP
    assert fills[1].price == 90.0


def test_tc07_same_bar_entry_then_exit():
    # Same bar allows Entry then Exit.
    # Bar: O=100 H=120 L=90 C=110
    # Entry: Buy Stop 105 -> fills at 105 (since open 100 < 105 and high 120 >= 105)
    # Exit: Sell Stop 95 -> after entry, low 90 <= 95 -> fills at 95
    bars = _bars1(100, 120, 90, 110)
    intents = [
        OrderIntent(order_id=1, created_bar=-1, role=OrderRole.ENTRY, kind=OrderKind.STOP, side=Side.BUY, price=105.0),
        OrderIntent(order_id=2, created_bar=-1, role=OrderRole.EXIT, kind=OrderKind.STOP, side=Side.SELL, price=95.0),
    ]
    fills = simulate(bars, intents)
    assert len(fills) == 2
    assert fills[0].price == 105.0
    assert fills[1].price == 95.0



