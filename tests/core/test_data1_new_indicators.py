import unittest
import numpy as np
from indicators.numba_indicators import (
    rsi_wilder, adx_wilder, macd_hist, roc, rolling_z_strict
)

class TestNewIndicators(unittest.TestCase):
    def test_rsi_wilder(self):
        # Synthetic uprend
        arr = np.linspace(100, 200, 100)
        out = rsi_wilder(arr, 14)
        self.assertEqual(len(out), 100)
        self.assertTrue(np.isnan(out[13]))
        self.assertFalse(np.isnan(out[14]))
        self.assertGreater(out[14], 90) # Should be high RSI for pure uptrend
        
    def test_adx_wilder(self):
        high = np.linspace(101, 201, 100)
        low = np.linspace(99, 199, 100)
        close = np.linspace(100, 200, 100)
        adx, di_plus, di_minus = adx_wilder(high, low, close, 14)
        
        self.assertEqual(len(adx), 100)
        # ADX(14) requires 2*window bars (initial seed at window, then smooth for window)
        # Actually in our impl: di_plus at window, dx at window, adx at 2*window-1 are SMA
        self.assertTrue(np.isnan(adx[26]))
        self.assertFalse(np.isnan(adx[27]))
        self.assertTrue(np.isnan(di_plus[13]))
        self.assertFalse(np.isnan(di_plus[14]))
        
        self.assertGreater(di_plus[14], di_minus[14]) # Uptrend
        
    def test_macd_hist(self):
        arr = np.linspace(100, 200, 100)
        out = macd_hist(arr, 12, 26, 9)
        self.assertEqual(len(out), 100)
        # macd needs 26, then signal needs 9 -> 34 warmup (index 33 is first valid)
        self.assertTrue(np.isnan(out[32]))
        self.assertFalse(np.isnan(out[33]))
        
    def test_roc(self):
        arr = np.array([100.0, 105.0, 110.0, 115.0, 120.0, 125.0], dtype=np.float64)
        out = roc(arr, 5)
        self.assertEqual(len(out), 6)
        self.assertTrue(np.isnan(out[4]))
        self.assertAlmostEqual(out[5], 0.25) # (125/100 - 1)
        
    def test_rolling_z_strict(self):
        arr = np.array([1, 2, 3, 4, 5, np.nan, 7, 8, 9, 10], dtype=np.float64)
        out = rolling_z_strict(arr, 3)
        # [1,2,3] -> mean=2, std=0.816 (pop) -> z=(3-2)/0.816 = 1.22
        # [2,3,4] -> mean=3, std=0.816 -> z=1.22
        # [4,5,nan] -> nan
        # [5,nan,7] -> nan
        # [nan,7,8] -> nan
        # [7,8,9] -> mean=8, std=0.816 -> z=1.22
        self.assertTrue(np.isnan(out[1]))
        self.assertFalse(np.isnan(out[2]))
        self.assertTrue(np.isnan(out[5]))
        self.assertTrue(np.isnan(out[6]))
        self.assertTrue(np.isnan(out[7]))
        self.assertFalse(np.isnan(out[8]))
        self.assertAlmostEqual(out[2], 1.224744871391589)

if __name__ == "__main__":
    unittest.main()
