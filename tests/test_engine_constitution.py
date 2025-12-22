
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


def _bars2(o0, h0, l0, c0, o1, h1, l1, c1):
    return normalize_bars(
        np.array([o0, o1], dtype=np.float64),
        np.array([h0, h1], dtype=np.float64),
        np.array([l0, l1], dtype=np.float64),
        np.array([c0, c1], dtype=np.float64),
    )


def test_tc01_buy_stop_normal():
    bars = _bars1(90, 105, 90, 100)
    intents = [
        OrderIntent(order_id=1, created_bar=-1, role=OrderRole.ENTRY, kind=OrderKind.STOP, side=Side.BUY, price=100.0),
    ]
    fills = simulate(bars, intents)
    assert len(fills) == 1
    assert fills[0].price == 100.0


def test_tc02_buy_stop_gap_up_fill_open():
    bars = _bars1(105, 110, 105, 108)
    intents = [
        OrderIntent(order_id=1, created_bar=-1, role=OrderRole.ENTRY, kind=OrderKind.STOP, side=Side.BUY, price=100.0),
    ]
    fills = simulate(bars, intents)
    assert len(fills) == 1
    assert fills[0].price == 105.0


def test_tc03_sell_stop_gap_down_fill_open():
    bars = _bars1(90, 95, 80, 85)
    intents = [
        # Exit a long position requires SELL stop; we will enter long first in same bar is not allowed here,
        # so we simulate already-in-position by forcing an entry earlier: created_bar=-2 triggers at -1 (ignored),
        # Instead: use two bars and enter on bar0, exit on bar1.
    ]
    bars2 = _bars2(
        100, 100, 100, 100,   # bar0: enter long at 100 (buy stop gap/normal both ok)
        90, 95, 80, 85        # bar1: exit stop triggers gap down open
    )
    intents2 = [
        OrderIntent(order_id=1, created_bar=-1, role=OrderRole.ENTRY, kind=OrderKind.STOP, side=Side.BUY, price=100.0),
        OrderIntent(order_id=2, created_bar=0, role=OrderRole.EXIT, kind=OrderKind.STOP, side=Side.SELL, price=100.0),
    ]
    fills = simulate(bars2, intents2)
    assert len(fills) == 2
    # second fill is the exit
    assert fills[1].price == 90.0


def test_tc08_next_bar_active_not_same_bar():
    # bar0 has high 105 which would hit stop 102, but order created at bar0 must not fill at bar0.
    # bar1 hits again, should fill at bar1.
    bars = _bars2(
        100, 105, 95, 100,
        100, 105, 95, 100,
    )
    intents = [
        OrderIntent(order_id=1, created_bar=0, role=OrderRole.ENTRY, kind=OrderKind.STOP, side=Side.BUY, price=102.0),
    ]
    fills = simulate(bars, intents)
    assert len(fills) == 1
    assert fills[0].bar_index == 1
    assert fills[0].price == 102.0


def test_tc09_open_equals_stop_gap_branch_but_same_price():
    bars = _bars1(100, 100, 90, 95)
    intents = [
        OrderIntent(order_id=1, created_bar=-1, role=OrderRole.ENTRY, kind=OrderKind.STOP, side=Side.BUY, price=100.0),
    ]
    fills = simulate(bars, intents)
    assert len(fills) == 1
    assert fills[0].price == 100.0


def test_tc10_no_fill_when_not_touched():
    bars = _bars1(90, 95, 90, 92)
    intents = [
        OrderIntent(order_id=1, created_bar=-1, role=OrderRole.ENTRY, kind=OrderKind.STOP, side=Side.BUY, price=100.0),
    ]
    fills = simulate(bars, intents)
    assert fills == []



