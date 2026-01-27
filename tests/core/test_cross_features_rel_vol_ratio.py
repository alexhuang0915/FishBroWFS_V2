import unittest

import numpy as np

from core.features.cross import compute_cross_features_v1


class TestCrossFeaturesRelVolRatio(unittest.TestCase):
    def test_rel_vol_ratio_is_scale_invariant_using_atr_pct(self):
        # Build two price series with the same *relative* volatility but different price scales.
        n = 200
        base = np.linspace(100.0, 120.0, n)
        # deterministic wiggle
        wiggle = 0.5 * np.sin(np.linspace(0, 10.0, n))
        c1 = base + wiggle
        c2 = 10.0 * c1  # same shape, 10x scale

        # Make OHLC consistent
        o1 = c1.copy()
        h1 = c1 + 1.0
        l1 = c1 - 1.0

        o2 = c2.copy()
        h2 = c2 + 10.0
        l2 = c2 - 10.0

        feats = compute_cross_features_v1(o1=o1, h1=h1, l1=l1, c1=c1, o2=o2, h2=h2, l2=l2, c2=c2)
        ratio = feats["rel_vol_ratio"]

        # After warmup, ATR% ratios should be close to 1 (scale-invariant).
        tail = ratio[50:]
        tail = tail[np.isfinite(tail)]
        self.assertGreater(len(tail), 0)
        self.assertTrue(np.all((tail > 0.8) & (tail < 1.25)))

