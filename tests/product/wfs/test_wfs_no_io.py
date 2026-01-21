
import builtins
from pathlib import Path

import numpy as np
import pytest

from core.feature_bundle import FeatureSeries, FeatureBundle
import wfs.runner as wfs_runner


class _DummySpec:
    """
    Minimal strategy spec object for tests.
    Must provide:
      - defaults: dict
      - fn(strategy_input: dict, params: dict) -> dict with {"intents": [...]}
    """
    def __init__(self):
        self.defaults = {}

        def _fn(strategy_input, params):
            # Must not do IO; return valid structure for run_strategy().
            return {"intents": []}

        self.fn = _fn


def test_run_wfs_with_features_disallows_file_io_without_real_strategy(monkeypatch):
    # 1) Hard deny all file IO primitives
    def _deny(*args, **kwargs):
        raise RuntimeError("IO is forbidden in run_wfs_with_features")

    monkeypatch.setattr(builtins, "open", _deny, raising=True)
    monkeypatch.setattr(Path, "open", _deny, raising=True)
    monkeypatch.setattr(Path, "read_text", _deny, raising=True)
    monkeypatch.setattr(Path, "exists", _deny, raising=True)

    # 2) Inject dummy strategy spec so we don't rely on repo strategy registry/ids
    # Primary patch target: symbol referenced by wfs_runner module
    monkeypatch.setattr(wfs_runner, "get_strategy_spec", lambda strategy_id: _DummySpec(), raising=False)

    # If get_strategy_spec isn't used in this repo layout, add fallback patches:
    # These should be kept harmless by raising=False.
    try:
        import strategy.registry as strat_registry
        monkeypatch.setattr(strat_registry, "get", lambda strategy_id: _DummySpec(), raising=False)
    except Exception:
        pass

    try:
        import strategy.runner as strat_runner
        monkeypatch.setattr(strat_runner, "get", lambda strategy_id: _DummySpec(), raising=False)
    except Exception:
        pass

    # 3) Build a minimal FeatureBundle
    ts = np.array(
        ["2025-01-01T00:00:00", "2025-01-01T00:01:00", "2025-01-01T00:02:00"],
        dtype="datetime64[s]",
    )
    v = np.array([1.0, 2.0, 3.0], dtype=np.float64)

    s1 = FeatureSeries(ts=ts, values=v, name="atr_14", timeframe_min=60)
    s2 = FeatureSeries(ts=ts, values=v, name="ret_z_200", timeframe_min=60)
    s3 = FeatureSeries(ts=ts, values=v, name="session_vwap", timeframe_min=60)

    # FeatureBundle requires meta dict with ts_dtype and breaks_policy
    meta = {
        "ts_dtype": "datetime64[s]",
        "breaks_policy": "drop",
    }
    bundle = FeatureBundle(
        dataset_id="D",
        season="S",
        series={(s.name, s.timeframe_min): s for s in [s1, s2, s3]},
        meta=meta,
    )

    out = wfs_runner.run_wfs_with_features(
        strategy_id="__dummy__",
        feature_bundle=bundle,
        config={"params": {}},
    )

    assert isinstance(out, dict)

