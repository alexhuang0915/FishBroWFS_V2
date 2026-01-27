import unittest

import numpy as np

from core.features.compute import compute_atr_14


class TestAtrNanRecovery(unittest.TestCase):
    def test_atr_recovers_after_nan_gap(self):
        n = 60
        # NaNs in the first segment emulate missing data2 before first bar.
        c = np.full(n, np.nan, dtype=np.float64)
        c[20:] = 100.0 + np.linspace(0.0, 1.0, n - 20)
        o = c.copy()
        h = c + 1.0
        l = c - 1.0

        atr = compute_atr_14(o, h, l, c)

        # Before we have 14 consecutive valid TR points, ATR remains NaN.
        self.assertTrue(np.all(np.isnan(atr[:33])))

        # After enough valid bars, ATR becomes finite.
        finite_after = np.isfinite(atr[33:]).sum()
        self.assertGreater(finite_after, 0)

