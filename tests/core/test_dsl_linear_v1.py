import unittest

import numpy as np
import pandas as pd

from core.feature_bundle import FeatureBundle, FeatureSeries
from core.feature_context import FeatureContext
from core.strategies.v2.dsl_linear_v1 import DslLinearV1


def _bundle(*, tf: int, season: str, dataset_id: str, ts: np.ndarray, series: dict[str, np.ndarray]) -> FeatureBundle:
    s = {}
    for name, values in series.items():
        s[(name, tf)] = FeatureSeries(ts=ts, values=values.astype(np.float64), name=name, timeframe_min=tf)
    return FeatureBundle(dataset_id=dataset_id, season=season, series=s, meta={"ts_dtype": "datetime64[s]", "breaks_policy": "drop"})


class TestDslLinearV1(unittest.TestCase):
    def test_linear_score_cross_drives_direction(self) -> None:
        tf = 60
        n = 5
        ts = np.arange(n).astype("datetime64[s]")

        d1 = _bundle(tf=tf, season="2026Q1", dataset_id="CME.MNQ", ts=ts, series={"atr_14": np.ones(n)})
        x = _bundle(
            tf=tf,
            season="2026Q1",
            dataset_id="CME.MNQ__CFE.VX",
            ts=ts,
            series={
                "corr_60": np.array([0.0, 0.5, 0.6, -0.2, np.nan]),
                "spread_log_z_60": np.array([0.0, 0.3, 1.0, -0.5, 0.1]),
                "rel_vol_ratio": np.array([1.0, 1.0, 1.0, 1.0, 1.0]),
            },
        )
        ctx = FeatureContext(timeframe_min=tf, data1=d1, cross=x, data2=None, data2_id="CFE.VX")
        df = pd.DataFrame({"close": np.linspace(100, 104, n)})

        strat = DslLinearV1(
            {
                "w_corr": 1.0,
                "w_spread": 1.0,
                "w_rel_vol": 0.0,
                "th_long": 1.2,
                "th_short": -0.6,
                "dsl": {
                    "terms": [
                        {"source": "cross", "feature": "corr_60", "weight": "w_corr"},
                        {"source": "cross", "feature": "spread_log_z_60", "weight": "w_spread"},
                    ],
                    "thresholds": {"long_ge": "th_long", "short_le": "th_short"},
                },
            }
        )

        out = strat.compute_orders_ctx(ctx, df)
        target = out["target_dir"]
        self.assertEqual(target.dtype, np.int64)
        # score: [0.0, 0.8, 1.6, -0.7, NaN] => [0,0,1,-1,0]
        self.assertListEqual(target.tolist(), [0, 0, 1, -1, 0])

    def test_stop_entry_outputs_prices_and_fail_closed(self) -> None:
        tf = 60
        n = 4
        ts = np.arange(n).astype("datetime64[s]")

        d1 = _bundle(
            tf=tf,
            season="2026Q1",
            dataset_id="CME.MNQ",
            ts=ts,
            series={
                "atr_14": np.ones(n),
                "hh_20": np.array([10.0, 11.0, 12.0, 13.0]),
                "ll_20": np.array([9.0, 8.0, 7.0, 6.0]),
            },
        )
        x = _bundle(
            tf=tf,
            season="2026Q1",
            dataset_id="CME.MNQ__CFE.VX",
            ts=ts,
            series={"corr_60": np.array([1.0, 1.0, 1.0, 1.0])},
        )
        ctx = FeatureContext(timeframe_min=tf, data1=d1, cross=x, data2=None, data2_id="CFE.VX")
        df = pd.DataFrame({"open": [10.0, 10.0, 10.0, 10.0], "high": [10, 10, 10, 10], "low": [10, 10, 10, 10], "close": [10, 10, 10, 10]})

        strat = DslLinearV1(
            {
                "w": 1.0,
                "th_long": 0.5,
                "dsl": {
                    "terms": [{"source": "cross", "feature": "corr_60", "weight": "w"}],
                    "thresholds": {"long_ge": "th_long", "short_le": -999},
                    "entry": {
                        "mode": "stop",
                        "long": {"base": {"source": "data1", "feature": "hh_20"}, "offset": {"kind": "atr_mult", "value": 1.0, "sign": "+"}},
                    },
                },
            }
        )
        out = strat.compute_orders_ctx(ctx, df)
        self.assertIn("long_stop", out)
        self.assertTrue(np.isfinite(out["long_stop"][0]))

        # Now make it fail-closed by removing base feature name => should not trade (target set to 0).
        strat2 = DslLinearV1(
            {
                "w": 1.0,
                "th_long": 0.5,
                "dsl": {
                    "terms": [{"source": "cross", "feature": "corr_60", "weight": "w"}],
                    "thresholds": {"long_ge": "th_long", "short_le": -999},
                    "entry": {"mode": "stop", "long": {"base": {"source": "data1", "feature": ""}}},
                },
            }
        )
        out2 = strat2.compute_orders_ctx(ctx, df)
        self.assertTrue(np.all(out2["target_dir"] == 0))


if __name__ == "__main__":
    unittest.main()
