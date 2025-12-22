
from __future__ import annotations

import numpy as np

from FishBroWFS_V2.pipeline.runner_grid import run_grid


def test_run_grid_perf_fields_present_and_non_negative(monkeypatch) -> None:
    # Enable perf observability.
    monkeypatch.setenv("FISHBRO_PROFILE_GRID", "1")

    o = np.array([100, 101, 102, 103, 104, 105], dtype=np.float64)
    h = np.array([101, 102, 103, 104, 106, 107], dtype=np.float64)
    l = np.array([99, 100, 101, 102, 103, 104], dtype=np.float64)
    c = np.array([100.5, 101.5, 102.5, 103.5, 105.5, 106.5], dtype=np.float64)

    params = np.array([[2, 2, 1.0], [3, 2, 1.5]], dtype=np.float64)
    out = run_grid(o, h, l, c, params, commission=0.0, slip=0.0, order_qty=1, sort_params=False)

    assert "perf" in out
    perf = out["perf"]
    assert isinstance(perf, dict)

    for k in ("t_features", "t_indicators", "t_intent_gen", "t_simulate"):
        assert k in perf
        # allow None (JSON null) when measurement is unavailable; never assume 0 is meaningful
        if perf[k] is not None:
            assert float(perf[k]) >= 0.0

    assert "simulate_impl" in perf
    assert perf["simulate_impl"] in ("jit", "py")

    assert "intents_total" in perf
    if perf["intents_total"] is not None:
        assert int(perf["intents_total"]) >= 0

    # Perf harness hook: confirm we can observe intent mode when profiling is enabled.
    assert "intent_mode" in perf
    if perf["intent_mode"] is not None:
        assert perf["intent_mode"] in ("arrays", "objects")




