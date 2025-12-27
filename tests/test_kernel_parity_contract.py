
"""Kernel parity contract tests - Phase 4 Stage C.

These tests ensure that Cursor kernel results are bit-level identical to matcher_core.
This is a critical contract: any deviation indicates a semantic bug.

Tests use simulate_run() unified entry point to ensure we test the actual API used in production.
"""

import numpy as np

from data.layout import normalize_bars
from engine.simulate import simulate_run
from engine.types import OrderIntent, OrderKind, OrderRole, Side


def _bars1(o, h, l, c):
    """Helper to create single-bar BarArrays."""
    return normalize_bars(
        np.array([o], dtype=np.float64),
        np.array([h], dtype=np.float64),
        np.array([l], dtype=np.float64),
        np.array([c], dtype=np.float64),
    )


def _bars2(o0, h0, l0, c0, o1, h1, l1, c1):
    """Helper to create two-bar BarArrays."""
    return normalize_bars(
        np.array([o0, o1], dtype=np.float64),
        np.array([h0, h1], dtype=np.float64),
        np.array([l0, l1], dtype=np.float64),
        np.array([c0, c1], dtype=np.float64),
    )


def _bars3(o0, h0, l0, c0, o1, h1, l1, c1, o2, h2, l2, c2):
    """Helper to create three-bar BarArrays."""
    return normalize_bars(
        np.array([o0, o1, o2], dtype=np.float64),
        np.array([h0, h1, h2], dtype=np.float64),
        np.array([l0, l1, l2], dtype=np.float64),
        np.array([c0, c1, c2], dtype=np.float64),
    )


def _compute_position_path(fills):
    """
    Compute position path from fills sequence.
    
    Returns list of (bar_index, position) tuples where position is:
    - 0: flat
    - 1: long
    - -1: short
    """
    pos_path = []
    current_pos = 0
    
    # Group fills by bar_index
    fills_by_bar = {}
    for fill in fills:
        bar_idx = fill.bar_index
        if bar_idx not in fills_by_bar:
            fills_by_bar[bar_idx] = []
        fills_by_bar[bar_idx].append(fill)
    
    # Process fills chronologically
    for bar_idx in sorted(fills_by_bar.keys()):
        bar_fills = fills_by_bar[bar_idx]
        # Sort by role (ENTRY first), then kind, then order_id
        bar_fills.sort(key=lambda f: (
            0 if f.role == OrderRole.ENTRY else 1,
            0 if f.kind == OrderKind.STOP else 1,
            f.order_id
        ))
        
        for fill in bar_fills:
            if fill.role == OrderRole.ENTRY:
                if fill.side == Side.BUY:
                    current_pos = 1
                else:
                    current_pos = -1
            elif fill.role == OrderRole.EXIT:
                current_pos = 0
        
        pos_path.append((bar_idx, current_pos))
    
    return pos_path


def _assert_fills_identical(cursor_fills, reference_fills):
    """Assert that two fill sequences are bit-level identical."""
    assert len(cursor_fills) == len(reference_fills), (
        f"Fill count mismatch: cursor={len(cursor_fills)}, reference={len(reference_fills)}"
    )
    
    for i, (c_fill, r_fill) in enumerate(zip(cursor_fills, reference_fills)):
        assert c_fill.bar_index == r_fill.bar_index, (
            f"Fill {i}: bar_index mismatch: cursor={c_fill.bar_index}, reference={r_fill.bar_index}"
        )
        assert c_fill.role == r_fill.role, (
            f"Fill {i}: role mismatch: cursor={c_fill.role}, reference={r_fill.role}"
        )
        assert c_fill.kind == r_fill.kind, (
            f"Fill {i}: kind mismatch: cursor={c_fill.kind}, reference={r_fill.kind}"
        )
        assert c_fill.side == r_fill.side, (
            f"Fill {i}: side mismatch: cursor={c_fill.side}, reference={r_fill.side}"
        )
        assert c_fill.price == r_fill.price, (
            f"Fill {i}: price mismatch: cursor={c_fill.price}, reference={r_fill.price}"
        )
        assert c_fill.qty == r_fill.qty, (
            f"Fill {i}: qty mismatch: cursor={c_fill.qty}, reference={r_fill.qty}"
        )
        assert c_fill.order_id == r_fill.order_id, (
            f"Fill {i}: order_id mismatch: cursor={c_fill.order_id}, reference={r_fill.order_id}"
        )


def _assert_position_path_identical(cursor_fills, reference_fills):
    """Assert that position paths are identical."""
    cursor_path = _compute_position_path(cursor_fills)
    reference_path = _compute_position_path(reference_fills)
    
    assert cursor_path == reference_path, (
        f"Position path mismatch:\n"
        f"  cursor: {cursor_path}\n"
        f"  reference: {reference_path}"
    )


def test_parity_next_bar_activation():
    """Test next-bar activation rule: order created at bar N activates at bar N+1."""
    # Order created at bar 0, should activate at bar 1
    bars = _bars2(
        100, 105, 95, 100,  # bar 0: high=105 would hit stop 102, but order not active yet
        100, 105, 95, 100,  # bar 1: order activates, should fill
    )
    intents = [
        OrderIntent(order_id=1, created_bar=0, role=OrderRole.ENTRY, kind=OrderKind.STOP, side=Side.BUY, price=102.0),
    ]
    
    # Use unified simulate_run() entry point
    cursor_result = simulate_run(bars, intents, use_reference=False)
    reference_result = simulate_run(bars, intents, use_reference=True)
    
    _assert_fills_identical(cursor_result.fills, reference_result.fills)
    _assert_position_path_identical(cursor_result.fills, reference_result.fills)
    
    # Verify: should fill at bar 1, not bar 0
    assert len(cursor_result.fills) == 1
    assert cursor_result.fills[0].bar_index == 1


def test_parity_stop_fill_price_exact():
    """Test stop fill price = stop_price (not max(open, stop_price))."""
    # Buy stop at 100, open=95, high=105 -> should fill at 100 (stop_price), not 105
    bars = _bars1(95, 105, 90, 100)
    intents = [
        OrderIntent(order_id=1, created_bar=-1, role=OrderRole.ENTRY, kind=OrderKind.STOP, side=Side.BUY, price=100.0),
    ]
    
    # Use unified simulate_run() entry point
    cursor_result = simulate_run(bars, intents, use_reference=False)
    reference_result = simulate_run(bars, intents, use_reference=True)
    
    _assert_fills_identical(cursor_result.fills, reference_result.fills)
    assert cursor_result.fills[0].price == 100.0  # stop_price, not high


def test_parity_stop_fill_price_gap_up():
    """Test stop fill price on gap up: fill at open if open >= stop_price."""
    # Buy stop at 100, open=105 (gap up) -> should fill at 105 (open), not 100
    bars = _bars1(105, 110, 105, 108)
    intents = [
        OrderIntent(order_id=1, created_bar=-1, role=OrderRole.ENTRY, kind=OrderKind.STOP, side=Side.BUY, price=100.0),
    ]
    
    # Use unified simulate_run() entry point
    cursor_result = simulate_run(bars, intents, use_reference=False)
    reference_result = simulate_run(bars, intents, use_reference=True)
    
    _assert_fills_identical(cursor_result.fills, reference_result.fills)
    assert cursor_result.fills[0].price == 105.0  # open (gap branch)


def test_parity_stop_fill_price_gap_down():
    """Test stop fill price on gap down: fill at open if open <= stop_price."""
    # Sell stop at 100, open=90 (gap down) -> should fill at 90 (open), not 100
    bars = _bars2(
        100, 100, 100, 100,  # bar 0: enter long
        90, 95, 80, 85,      # bar 1: exit stop gap down
    )
    intents = [
        OrderIntent(order_id=1, created_bar=-1, role=OrderRole.ENTRY, kind=OrderKind.STOP, side=Side.BUY, price=100.0),
        OrderIntent(order_id=2, created_bar=0, role=OrderRole.EXIT, kind=OrderKind.STOP, side=Side.SELL, price=100.0),
    ]
    
    # Use unified simulate_run() entry point
    cursor_result = simulate_run(bars, intents, use_reference=False)
    reference_result = simulate_run(bars, intents, use_reference=True)
    
    _assert_fills_identical(cursor_result.fills, reference_result.fills)
    _assert_position_path_identical(cursor_result.fills, reference_result.fills)
    # Exit fill should be at open (90) due to gap down
    assert cursor_result.fills[1].price == 90.0


def test_parity_same_bar_entry_then_exit():
    """Test same-bar entry then exit is allowed."""
    # Same bar: entry buy stop 105, exit sell stop 95
    # Bar: O=100 H=120 L=90
    # Entry: Buy Stop 105 -> fills at 105
    # Exit: Sell Stop 95 -> fills at 95 (after entry)
    bars = _bars1(100, 120, 90, 110)
    intents = [
        OrderIntent(order_id=1, created_bar=-1, role=OrderRole.ENTRY, kind=OrderKind.STOP, side=Side.BUY, price=105.0),
        OrderIntent(order_id=2, created_bar=-1, role=OrderRole.EXIT, kind=OrderKind.STOP, side=Side.SELL, price=95.0),
    ]
    
    # Use unified simulate_run() entry point
    cursor_result = simulate_run(bars, intents, use_reference=False)
    reference_result = simulate_run(bars, intents, use_reference=True)
    
    _assert_fills_identical(cursor_result.fills, reference_result.fills)
    _assert_position_path_identical(cursor_result.fills, reference_result.fills)
    
    assert len(cursor_result.fills) == 2
    assert cursor_result.fills[0].role == OrderRole.ENTRY
    assert cursor_result.fills[0].price == 105.0
    assert cursor_result.fills[1].role == OrderRole.EXIT
    assert cursor_result.fills[1].price == 95.0
    assert cursor_result.fills[0].bar_index == cursor_result.fills[1].bar_index


def test_parity_stop_priority_over_limit():
    """Test STOP priority over LIMIT (same role, same bar)."""
    # Entry: Buy Stop 102 and Buy Limit 110 both triggerable
    # STOP must win
    bars = _bars1(100, 115, 95, 105)
    intents = [
        OrderIntent(order_id=1, created_bar=-1, role=OrderRole.ENTRY, kind=OrderKind.STOP, side=Side.BUY, price=102.0),
        OrderIntent(order_id=2, created_bar=-1, role=OrderRole.ENTRY, kind=OrderKind.LIMIT, side=Side.BUY, price=110.0),
    ]
    
    # Use unified simulate_run() entry point
    cursor_result = simulate_run(bars, intents, use_reference=False)
    reference_result = simulate_run(bars, intents, use_reference=True)
    
    _assert_fills_identical(cursor_result.fills, reference_result.fills)
    assert cursor_result.fills[0].kind == OrderKind.STOP
    assert cursor_result.fills[0].order_id == 1


def test_parity_stop_priority_exit():
    """Test STOP priority over LIMIT on exit."""
    # Enter long first, then exit with both stop and limit triggerable
    # STOP must win
    bars = _bars2(
        100, 100, 100, 100,  # bar 0: enter long
        100, 110, 80, 90,    # bar 1: exit stop 90 and exit limit 110 both triggerable
    )
    intents = [
        OrderIntent(order_id=1, created_bar=-1, role=OrderRole.ENTRY, kind=OrderKind.STOP, side=Side.BUY, price=100.0),
        OrderIntent(order_id=2, created_bar=0, role=OrderRole.EXIT, kind=OrderKind.STOP, side=Side.SELL, price=90.0),
        OrderIntent(order_id=3, created_bar=0, role=OrderRole.EXIT, kind=OrderKind.LIMIT, side=Side.SELL, price=110.0),
    ]
    
    # Use unified simulate_run() entry point
    cursor_result = simulate_run(bars, intents, use_reference=False)
    reference_result = simulate_run(bars, intents, use_reference=True)
    
    _assert_fills_identical(cursor_result.fills, reference_result.fills)
    _assert_position_path_identical(cursor_result.fills, reference_result.fills)
    
    # Exit fill should be STOP
    assert cursor_result.fills[1].kind == OrderKind.STOP
    assert cursor_result.fills[1].order_id == 2


def test_parity_order_id_tie_break():
    """Test order_id tie-break when kind is same."""
    # Two STOP orders, lower order_id should win
    bars = _bars1(100, 110, 95, 105)
    intents = [
        OrderIntent(order_id=2, created_bar=-1, role=OrderRole.ENTRY, kind=OrderKind.STOP, side=Side.BUY, price=102.0),
        OrderIntent(order_id=1, created_bar=-1, role=OrderRole.ENTRY, kind=OrderKind.STOP, side=Side.BUY, price=102.0),
    ]
    
    # Use unified simulate_run() entry point
    cursor_result = simulate_run(bars, intents, use_reference=False)
    reference_result = simulate_run(bars, intents, use_reference=True)
    
    _assert_fills_identical(cursor_result.fills, reference_result.fills)
    assert cursor_result.fills[0].order_id == 1  # Lower order_id wins


def test_parity_limit_gap_down_better_fill():
    """Test limit order gap down: fill at open if better."""
    # Buy limit at 100, open=90 (gap down) -> should fill at 90 (open), not 100
    bars = _bars1(90, 95, 85, 92)
    intents = [
        OrderIntent(order_id=1, created_bar=-1, role=OrderRole.ENTRY, kind=OrderKind.LIMIT, side=Side.BUY, price=100.0),
    ]
    
    # Use unified simulate_run() entry point
    cursor_result = simulate_run(bars, intents, use_reference=False)
    reference_result = simulate_run(bars, intents, use_reference=True)
    
    _assert_fills_identical(cursor_result.fills, reference_result.fills)
    assert cursor_result.fills[0].price == 90.0  # open (better fill)


def test_parity_limit_gap_up_better_fill():
    """Test limit order gap up: fill at open if better."""
    # Sell limit at 100, open=105 (gap up) -> should fill at 105 (open), not 100
    bars = _bars1(105, 110, 100, 108)
    intents = [
        OrderIntent(order_id=1, created_bar=-1, role=OrderRole.ENTRY, kind=OrderKind.LIMIT, side=Side.SELL, price=100.0),
    ]
    
    # Use unified simulate_run() entry point
    cursor_result = simulate_run(bars, intents, use_reference=False)
    reference_result = simulate_run(bars, intents, use_reference=True)
    
    _assert_fills_identical(cursor_result.fills, reference_result.fills)
    assert cursor_result.fills[0].price == 105.0  # open (better fill)


def test_parity_no_fill_when_not_touched():
    """Test no fill when price not touched."""
    bars = _bars1(90, 95, 90, 92)
    intents = [
        OrderIntent(order_id=1, created_bar=-1, role=OrderRole.ENTRY, kind=OrderKind.STOP, side=Side.BUY, price=100.0),
    ]
    
    # Use unified simulate_run() entry point
    cursor_result = simulate_run(bars, intents, use_reference=False)
    reference_result = simulate_run(bars, intents, use_reference=True)
    
    _assert_fills_identical(cursor_result.fills, reference_result.fills)
    assert len(cursor_result.fills) == 0


def test_parity_open_equals_stop_gap_branch():
    """Test open equals stop price: gap branch but same price."""
    bars = _bars1(100, 100, 90, 95)
    intents = [
        OrderIntent(order_id=1, created_bar=-1, role=OrderRole.ENTRY, kind=OrderKind.STOP, side=Side.BUY, price=100.0),
    ]
    
    # Use unified simulate_run() entry point
    cursor_result = simulate_run(bars, intents, use_reference=False)
    reference_result = simulate_run(bars, intents, use_reference=True)
    
    _assert_fills_identical(cursor_result.fills, reference_result.fills)
    assert cursor_result.fills[0].price == 100.0  # open == stop_price


def test_parity_multiple_bars_complex():
    """Test complex multi-bar scenario with entry and exit."""
    bars = _bars3(
        100, 105, 95, 100,   # bar 0: enter long at 102 (buy stop)
        100, 110, 80, 90,    # bar 1: exit stop 90 triggers
        95, 100, 90, 95,     # bar 2: no fills
    )
    intents = [
        OrderIntent(order_id=1, created_bar=-1, role=OrderRole.ENTRY, kind=OrderKind.STOP, side=Side.BUY, price=102.0),
        OrderIntent(order_id=2, created_bar=0, role=OrderRole.EXIT, kind=OrderKind.STOP, side=Side.SELL, price=90.0),
    ]
    
    # Use unified simulate_run() entry point
    cursor_result = simulate_run(bars, intents, use_reference=False)
    reference_result = simulate_run(bars, intents, use_reference=True)
    
    _assert_fills_identical(cursor_result.fills, reference_result.fills)
    _assert_position_path_identical(cursor_result.fills, reference_result.fills)
    
    # Verify position path
    pos_path = _compute_position_path(cursor_result.fills)
    assert pos_path == [(0, 1), (1, 0)]  # Enter at bar 0, exit at bar 1


def test_parity_entry_skipped_when_position_exists():
    """Test that entry is skipped when position already exists."""
    # Enter long at bar 0, then at bar 1 try to enter again (should be skipped) and exit
    bars = _bars2(
        100, 100, 100, 100,  # bar 0: enter long
        100, 110, 90, 100,   # bar 1: exit stop 95 triggers, entry stop 105 also triggerable but skipped
    )
    intents = [
        OrderIntent(order_id=1, created_bar=-1, role=OrderRole.ENTRY, kind=OrderKind.STOP, side=Side.BUY, price=100.0),
        OrderIntent(order_id=2, created_bar=0, role=OrderRole.EXIT, kind=OrderKind.STOP, side=Side.SELL, price=95.0),
        OrderIntent(order_id=3, created_bar=0, role=OrderRole.ENTRY, kind=OrderKind.STOP, side=Side.BUY, price=105.0),
    ]
    
    # Use unified simulate_run() entry point
    cursor_result = simulate_run(bars, intents, use_reference=False)
    reference_result = simulate_run(bars, intents, use_reference=True)
    
    _assert_fills_identical(cursor_result.fills, reference_result.fills)
    _assert_position_path_identical(cursor_result.fills, reference_result.fills)
    
    # Should have entry at bar 0 and exit at bar 1
    # Entry at bar 1 should be skipped (position already exists)
    assert len(cursor_result.fills) == 2
    assert cursor_result.fills[0].bar_index == 0
    assert cursor_result.fills[0].role == OrderRole.ENTRY
    assert cursor_result.fills[1].bar_index == 1
    assert cursor_result.fills[1].role == OrderRole.EXIT


