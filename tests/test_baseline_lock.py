
import numpy as np

from data.layout import normalize_bars
from engine.engine_jit import simulate as simulate_jit
from engine.matcher_core import simulate as simulate_py
from engine.types import OrderIntent, OrderKind, OrderRole, Side


def _fills_to_matrix(fills):
    # Columns: bar_index, role, kind, side, price, qty, order_id
    m = np.empty((len(fills), 7), dtype=np.float64)
    for i, f in enumerate(fills):
        m[i, 0] = float(f.bar_index)
        m[i, 1] = 0.0 if f.role == OrderRole.EXIT else 1.0
        m[i, 2] = 0.0 if f.kind == OrderKind.STOP else 1.0
        m[i, 3] = float(int(f.side.value))
        m[i, 4] = float(f.price)
        m[i, 5] = float(f.qty)
        m[i, 6] = float(f.order_id)
    return m


def test_gate_a_jit_matches_python_reference():
    # Two bars so we can test next-bar active + entry then exit.
    bars = normalize_bars(
        np.array([100.0, 100.0], dtype=np.float64),
        np.array([120.0, 120.0], dtype=np.float64),
        np.array([90.0, 80.0], dtype=np.float64),
        np.array([110.0, 90.0], dtype=np.float64),
    )

    intents = [
        # Entry active on bar0
        OrderIntent(order_id=1, created_bar=-1, role=OrderRole.ENTRY, kind=OrderKind.STOP, side=Side.BUY, price=105.0),
        # Exit active on bar0 (same bar), should execute after entry
        OrderIntent(order_id=2, created_bar=-1, role=OrderRole.EXIT, kind=OrderKind.STOP, side=Side.SELL, price=95.0),
        # Entry created on bar0 -> active on bar1
        OrderIntent(order_id=3, created_bar=0, role=OrderRole.ENTRY, kind=OrderKind.STOP, side=Side.BUY, price=110.0),
    ]

    py = simulate_py(bars, intents)
    jit = simulate_jit(bars, intents)

    m_py = _fills_to_matrix(py)
    m_jit = _fills_to_matrix(jit)

    assert m_py.shape == m_jit.shape
    # Event-level exactness except price tolerance
    np.testing.assert_array_equal(m_py[:, [0, 1, 2, 3, 5, 6]], m_jit[:, [0, 1, 2, 3, 5, 6]])
    np.testing.assert_allclose(m_py[:, 4], m_jit[:, 4], rtol=0.0, atol=1e-9)



