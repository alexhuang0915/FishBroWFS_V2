
from __future__ import annotations

import numpy as np
import pytest

from data.layout import normalize_bars
from engine.engine_jit import simulate_arrays
from engine.engine_types import Fill, OrderKind, OrderRole, Side
from strategy.kernel import DonchianAtrParams, run_kernel_arrays, run_kernel_object_mode


def _assert_fills_equal(a: list[Fill], b: list[Fill]) -> None:
    assert len(a) == len(b)
    for fa, fb in zip(a, b):
        assert fa.bar_index == fb.bar_index
        assert fa.role == fb.role
        assert fa.kind == fb.kind
        assert fa.side == fb.side
        assert fa.qty == fb.qty
        assert fa.order_id == fb.order_id
        assert abs(fa.price - fb.price) <= 1e-9


@pytest.mark.xfail(reason="gap blindness fix causes parity discrepancy; need to align object/array exit intent generation")
def test_strategy_object_vs_array_mode_parity() -> None:
    rng = np.random.default_rng(42)
    n = 300
    close = 100.0 + np.cumsum(rng.standard_normal(n)).astype(np.float64)
    high = close + 1.0
    low = close - 1.0
    open_ = (high + low) * 0.5

    bars = normalize_bars(open_, high, low, close)
    params = DonchianAtrParams(channel_len=20, atr_len=14, stop_mult=2.0)

    out_obj = run_kernel_object_mode(bars, params, commission=0.0, slip=0.0, order_qty=1)
    out_arr = run_kernel_arrays(bars, params, commission=0.0, slip=0.0, order_qty=1)

    _assert_fills_equal(out_obj["fills"], out_arr["fills"])  # type: ignore[arg-type]


def test_simulate_arrays_same_bar_entry_exit_parity() -> None:
    # Construct a same-bar entry then exit scenario (created_bar=-1 activates on bar0).
    bars = normalize_bars(
        np.array([100.0], dtype=np.float64),
        np.array([120.0], dtype=np.float64),
        np.array([80.0], dtype=np.float64),
        np.array([110.0], dtype=np.float64),
    )

    # ENTRY BUY STOP 105, EXIT SELL STOP 95, both active on bar0.
    order_id = np.array([1, 2], dtype=np.int64)
    created_bar = np.array([-1, -1], dtype=np.int64)
    role = np.array([1, 0], dtype=np.int8)  # ENTRY then EXIT (order_id tie-break handles)
    kind = np.array([0, 0], dtype=np.int8)  # STOP
    side = np.array([1, -1], dtype=np.int8)  # BUY, SELL
    price = np.array([105.0, 95.0], dtype=np.float64)
    qty = np.array([1, 1], dtype=np.int64)

    fills = simulate_arrays(
        bars,
        order_id=order_id,
        created_bar=created_bar,
        role=role,
        kind=kind,
        side=side,
        price=price,
        qty=qty,
        ttl_bars=1,
    )

    assert len(fills) == 2
    assert fills[0].role == OrderRole.ENTRY and fills[0].side == Side.BUY and fills[0].kind == OrderKind.STOP
    assert fills[1].role == OrderRole.EXIT and fills[1].side == Side.SELL and fills[1].kind == OrderKind.STOP




