import unittest

import numpy as np

from core.backtest.simulator import CostConfig, simulate_bar_engine


class TestSimulatorTradeLedger(unittest.TestCase):
    def test_trade_ledger_length_matches_trades(self):
        # Build a tiny series where we flip direction once to force a round trip.
        n = 10
        ts = np.array([np.datetime64(f"2025-01-01T0{i}:00:00") for i in range(n)], dtype="datetime64[s]")
        open_ = np.linspace(100.0, 109.0, n)
        high = open_ + 1.0
        low = open_ - 1.0
        close = open_ + 0.2

        # target: long for bars 0..4, then flat.
        target_dir = np.array([1, 1, 1, 1, 1, 0, 0, 0, 0, 0], dtype=np.int64)
        signals = {"target_dir": target_dir, "long_stop": None, "short_stop": None, "exit_long_stop": None, "exit_shortx": None}

        cost = CostConfig(
            slippage_ticks_per_side=0.0,
            commission_per_side=0.0,
            tick_size=0.25,
            multiplier=1.0,
            fx_rate=1.0,
        )
        sim = simulate_bar_engine(
            ts=ts,
            open_=open_,
            high=high,
            low=low,
            close=close,
            signals=signals,
            cost=cost,
            initial_equity=10_000.0,
            record_trades=True,
        )

        self.assertEqual(sim.trades, len(sim.trades_ledger))
        if sim.trades:
            trade = sim.trades_ledger[0]
            self.assertIn("entry_t", trade)
            self.assertIn("exit_t", trade)
            self.assertIn("net_pnl", trade)

