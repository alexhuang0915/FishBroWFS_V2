import unittest

import numpy as np

from core.backtest.simulator import CostConfig, simulate_bar_engine


class TestDslLinearStopEntrySim(unittest.TestCase):
    def test_stop_entry_triggers_and_records_trade(self) -> None:
        # Construct 6 bars. Signal at T=1 requests long stop-entry at 101.
        # At T+1 (i=2), high reaches 101 and open is 100.5 => fill at stop (101).
        ts = np.arange(6).astype("datetime64[s]")
        open_ = np.array([100, 100, 100.5, 102, 103, 104], dtype=np.float64)
        high = np.array([100, 100, 101.0, 103, 104, 105], dtype=np.float64)
        low = np.array([100, 100, 100.0, 101, 102, 103], dtype=np.float64)
        close = np.array([100, 100, 101.2, 102.5, 103.5, 104.5], dtype=np.float64)

        target_dir = np.zeros(6, dtype=np.int64)
        long_stop = np.full(6, np.nan, dtype=np.float64)
        # signal bar index s_idx=1 triggers bar i=2
        target_dir[1] = 1
        long_stop[1] = 101.0

        # exit market at next bar signal
        target_dir[3] = 0

        cost = CostConfig(slippage_ticks_per_side=0.0, commission_per_side=0.0, tick_size=1.0, multiplier=1.0, fx_rate=1.0)
        sim = simulate_bar_engine(
            ts=ts,
            open_=open_,
            high=high,
            low=low,
            close=close,
            signals={"target_dir": target_dir, "long_stop": long_stop},
            cost=cost,
            initial_equity=10_000.0,
            record_trades=True,
        )
        self.assertGreaterEqual(sim.trades, 1)
        self.assertTrue(any(t.get("entry_reason") == "stop_entry" for t in sim.trades_ledger))


if __name__ == "__main__":
    unittest.main()

