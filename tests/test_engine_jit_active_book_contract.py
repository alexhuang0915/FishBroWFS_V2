from __future__ import annotations

import os

import numpy as np
import pytest

from FishBroWFS_V2.data.layout import normalize_bars
from FishBroWFS_V2.engine.engine_jit import _simulate_with_ttl, simulate as simulate_jit
from FishBroWFS_V2.engine.matcher_core import simulate as simulate_py
from FishBroWFS_V2.engine.types import Fill, OrderIntent, OrderKind, OrderRole, Side


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


def test_jit_sorted_invariance_matches_python() -> None:
    # Bars: 3 bars, deterministic highs/lows for STOP triggers
    bars = normalize_bars(
        np.array([100.0, 100.0, 100.0], dtype=np.float64),
        np.array([110.0, 110.0, 110.0], dtype=np.float64),
        np.array([90.0, 90.0, 90.0], dtype=np.float64),
        np.array([100.0, 100.0, 100.0], dtype=np.float64),
    )

    # Intents across multiple activate bars (created_bar = t-1)
    intents = [
        # activate on bar0 (created -1)
        OrderIntent(3, -1, OrderRole.EXIT, OrderKind.STOP, Side.SELL, 95.0, 1),
        OrderIntent(2, -1, OrderRole.ENTRY, OrderKind.STOP, Side.BUY, 105.0, 1),
        # activate on bar1 (created 0)
        OrderIntent(6, 0, OrderRole.EXIT, OrderKind.LIMIT, Side.SELL, 110.0, 1),
        OrderIntent(5, 0, OrderRole.ENTRY, OrderKind.LIMIT, Side.BUY, 99.0, 1),
        # activate on bar2 (created 1)
        OrderIntent(9, 1, OrderRole.EXIT, OrderKind.STOP, Side.SELL, 90.0, 1),
        OrderIntent(8, 1, OrderRole.ENTRY, OrderKind.STOP, Side.BUY, 100.0, 1),
    ]

    shuffled = list(intents)
    rng = np.random.default_rng(123)
    rng.shuffle(shuffled)

    # JIT simulate sorts internally for cursor+book; it must be invariant to input ordering.
    jit_a = simulate_jit(bars, shuffled)
    jit_b = simulate_jit(bars, intents)
    _assert_fills_equal(jit_a, jit_b)

    # Also must match Python reference semantics.
    py = simulate_py(bars, shuffled)
    _assert_fills_equal(jit_a, py)


def test_one_bar_max_one_entry_one_exit_defense() -> None:
    # Single bar is enough: created_bar=-1 activates on bar 0.
    bars = normalize_bars(
        np.array([100.0], dtype=np.float64),
        np.array([120.0], dtype=np.float64),
        np.array([80.0], dtype=np.float64),
        np.array([110.0], dtype=np.float64),
    )

    # Same activate bar contains Entry1, Exit1, Entry2.
    intents = [
        OrderIntent(1, -1, OrderRole.ENTRY, OrderKind.STOP, Side.BUY, 105.0, 1),
        OrderIntent(2, -1, OrderRole.EXIT, OrderKind.STOP, Side.SELL, 95.0, 1),
        OrderIntent(3, -1, OrderRole.ENTRY, OrderKind.STOP, Side.BUY, 110.0, 1),
    ]

    fills = simulate_jit(bars, intents)
    assert len(fills) == 2
    assert fills[0].order_id == 1
    assert fills[1].order_id == 2


def test_ttl_one_shot_vs_gtc_extension_point() -> None:
    # Skip if JIT is disabled; ttl=0 is a JIT-only extension behavior.
    import FishBroWFS_V2.engine.engine_jit as ej

    if ej.nb is None or os.environ.get("NUMBA_DISABLE_JIT", "").strip() == "1":
        pytest.skip("numba not available or disabled; ttl=0 extension tested only under JIT")

    # Bar0: stop not touched, Bar1: stop touched
    bars = normalize_bars(
        np.array([90.0, 90.0], dtype=np.float64),
        np.array([99.0, 110.0], dtype=np.float64),
        np.array([90.0, 90.0], dtype=np.float64),
        np.array([95.0, 100.0], dtype=np.float64),
    )
    intents = [
        OrderIntent(1, -1, OrderRole.ENTRY, OrderKind.STOP, Side.BUY, 100.0, 1),
    ]

    # ttl=1 (default semantics): active only on bar0 -> no fill
    fills_ttl1 = simulate_jit(bars, intents)
    assert fills_ttl1 == []

    # ttl=0 (GTC extension): order stays in book and can fill on bar1
    fills_gtc = _simulate_with_ttl(bars, intents, ttl_bars=0)
    assert len(fills_gtc) == 1
    assert fills_gtc[0].bar_index == 1
    assert abs(fills_gtc[0].price - 100.0) <= 1e-9


