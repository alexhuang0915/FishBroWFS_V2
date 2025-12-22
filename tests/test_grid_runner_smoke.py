
import numpy as np

from FishBroWFS_V2.pipeline.runner_grid import run_grid


def _ohlc():
    o = np.array([100, 101, 102, 103, 104, 105], dtype=np.float64)
    h = np.array([101, 102, 103, 104, 106, 107], dtype=np.float64)
    l = np.array([99, 100, 101, 102, 103, 104], dtype=np.float64)
    c = np.array([100.5, 101.5, 102.5, 103.5, 105.5, 106.5], dtype=np.float64)
    return o, h, l, c


def test_grid_runner_smoke_shapes_and_no_crash():
    o, h, l, c = _ohlc()

    # params: [channel_len, atr_len, stop_mult]
    params = np.array(
        [
            [2, 2, 1.0],
            [3, 2, 1.5],
            [99999, 3, 2.0],  # should produce 0 trades
            [2, 99999, 2.0],  # atr_len > n should be safe (atr_wilder returns all-NaN -> kernel => 0 trades)
        ],
        dtype=np.float64,
    )

    out = run_grid(o, h, l, c, params, commission=0.0, slip=0.0, order_qty=1, sort_params=True)
    m = out["metrics"]
    order = out["order"]

    assert isinstance(m, np.ndarray)
    assert m.shape == (params.shape[0], 3)
    assert isinstance(order, np.ndarray)
    assert order.shape == (params.shape[0],)
    assert set(order.tolist()) == set(range(params.shape[0]))
    # Optional stronger assertion: at least one row should have 0 trades due to atr_len > n
    assert np.any(m[:, 1] == 0.0)


def test_grid_runner_sorting_toggle():
    o, h, l, c = _ohlc()
    params = np.array(
        [
            [3, 2, 1.5],
            [2, 2, 1.0],
            [2, 3, 2.0],
        ],
        dtype=np.float64,
    )

    out_sorted = run_grid(o, h, l, c, params, commission=0.0, slip=0.0, order_qty=1, sort_params=True)
    out_unsorted = run_grid(o, h, l, c, params, commission=0.0, slip=0.0, order_qty=1, sort_params=False)

    assert out_sorted["metrics"].shape == out_unsorted["metrics"].shape == (3, 3)
    assert out_sorted["order"].shape == out_unsorted["order"].shape == (3,)
    # unsorted order should be identity
    np.testing.assert_array_equal(out_unsorted["order"], np.array([0, 1, 2], dtype=np.int64))



