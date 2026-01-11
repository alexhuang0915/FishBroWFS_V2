"""
B&H (Buy & Hold) baseline computation for Research=WFS.

B&H baseline must be computed for the SAME:
- instrument
- timeframe/data
- IS and OOS ranges per season
- COST model assumptions (commission/slippage)

Definition:
- Single continuous long-only hold over each range, expressed as relative equity (starting at 0 or 1 consistently) to allow stitching.

Implementation constraints:
- If engine provides price series or equity series, compute B&H from the same underlying series.
- If engine only outputs strategy equity, implement B&H using market price returns from the dataset loader used by engine.
- If exact cost modeling for B&H is unclear, implement conservative cost application:
  - At minimum apply a single entry cost and single exit cost per range.
  - Document the assumption in config.costs or verdict.summary.

B&H series must be output in `series.stitched_bnh_equity` and aligned in time with stitched_oos_equity for overlay.
"""

from __future__ import annotations

from typing import List, Dict, Any, Tuple, Optional
from datetime import datetime
import numpy as np
from dataclasses import dataclass

from wfs.stitching import EquityPoint, StitchDiagnostic, stitch_equity_series


@dataclass
class CostModel:
    """Cost model for B&H baseline."""
    commission_per_trade: float = 0.0  # per trade commission
    slippage_ticks: float = 0.0  # slippage in ticks
    tick_value: float = 0.0  # value per tick
    multiplier: float = 1.0  # contract multiplier
    
    def total_entry_cost(self) -> float:
        """Total cost for entering a position."""
        return self.commission_per_trade + (self.slippage_ticks * self.tick_value * self.multiplier)
    
    def total_exit_cost(self) -> float:
        """Total cost for exiting a position."""
        return self.commission_per_trade + (self.slippage_ticks * self.tick_value * self.multiplier)
    
    def total_round_trip_cost(self) -> float:
        """Total cost for entering and exiting a position."""
        return self.total_entry_cost() + self.total_exit_cost()


@dataclass
class PriceSeries:
    """Price series for B&H computation."""
    timestamps: List[str]  # ISO timestamps
    close_prices: List[float]  # closing prices
    open_prices: Optional[List[float]] = None  # optional opening prices
    
    def __post_init__(self):
        if len(self.timestamps) != len(self.close_prices):
            raise ValueError("Timestamps and close_prices must have same length")
        if self.open_prices and len(self.open_prices) != len(self.close_prices):
            raise ValueError("Open_prices must have same length as close_prices")
    
    def __len__(self) -> int:
        return len(self.timestamps)
    
    def get_equity_points(self, start_value: float = 0.0) -> List[EquityPoint]:
        """
        Convert price series to equity points (relative returns).
        
        Args:
            start_value: Starting equity value (default 0.0)
        
        Returns:
            List of EquityPoint with cumulative returns
        """
        if not self.close_prices:
            return []
        
        # Calculate simple returns (close-to-close)
        returns = []
        for i in range(1, len(self.close_prices)):
            ret = (self.close_prices[i] - self.close_prices[i-1]) / self.close_prices[i-1]
            returns.append(ret)
        
        # Start with start_value, accumulate returns
        equity = [start_value]
        for ret in returns:
            equity.append(equity[-1] + ret * 100.0)  # Scale returns to percentage points
        
        # Create equity points
        points = []
        for ts, eq in zip(self.timestamps, equity):
            points.append({"t": ts, "v": eq})
        
        return points


def compute_bnh_equity_for_range(
    price_series: PriceSeries,
    cost_model: CostModel,
    initial_capital: float = 10000.0,
    position_size: float = 1.0  # number of contracts
) -> List[EquityPoint]:
    """
    Compute B&H equity for a single time range.
    
    Assumptions:
    - Buy at first bar's close (or open if available)
    - Hold until last bar's close
    - Apply entry cost at start, exit cost at end
    - Position size is fixed (1 contract by default)
    
    Args:
        price_series: Price series for the range
        cost_model: Cost model for commission and slippage
        initial_capital: Starting capital (for percentage calculation)
        position_size: Number of contracts to hold
    
    Returns:
        List of EquityPoint representing B&H equity over time
    """
    if len(price_series) < 2:
        # Not enough data for meaningful B&H
        return []
    
    # Determine entry and exit prices
    if price_series.open_prices:
        # Use open price for entry (more realistic for market open)
        entry_price = price_series.open_prices[0]
    else:
        # Use first close price
        entry_price = price_series.close_prices[0]
    
    exit_price = price_series.close_prices[-1]
    
    # Calculate price return
    price_return_pct = (exit_price - entry_price) / entry_price * 100.0
    
    # Calculate costs as percentage of initial capital
    total_cost = cost_model.total_round_trip_cost() * position_size
    cost_pct = (total_cost / initial_capital) * 100.0 if initial_capital > 0 else 0.0
    
    # Net return after costs
    net_return_pct = price_return_pct - cost_pct
    
    # Create equity series (linear interpolation from 0 to net_return)
    equity_points = []
    n_points = len(price_series)
    
    for i, ts in enumerate(price_series.timestamps):
        # Linear progression from 0 to net_return
        progress = i / max(1, n_points - 1)
        equity_value = net_return_pct * progress
        equity_points.append({"t": ts, "v": equity_value})
    
    return equity_points


def compute_bnh_equity_for_seasons(
    season_price_series: List[PriceSeries],
    season_labels: List[str],
    cost_model: CostModel,
    initial_capital: float = 10000.0,
    position_size: float = 1.0
) -> Tuple[List[EquityPoint], List[StitchDiagnostic]]:
    """
    Compute B&H equity for multiple seasons and stitch them together.
    
    Args:
        season_price_series: List of PriceSeries for each season
        season_labels: List of season labels (e.g., ["2020Q1", "2020Q2"])
        cost_model: Cost model for commission and slippage
        initial_capital: Starting capital
        position_size: Number of contracts to hold
    
    Returns:
        Tuple of (stitched B&H equity series, diagnostics)
    """
    # Compute B&H equity for each season
    season_equity_series = []
    
    for price_series in season_price_series:
        if len(price_series) < 2:
            # Empty or insufficient season
            season_equity_series.append([])
        else:
            equity = compute_bnh_equity_for_range(
                price_series=price_series,
                cost_model=cost_model,
                initial_capital=initial_capital,
                position_size=position_size
            )
            season_equity_series.append(equity)
    
    # Stitch the season equity series
    stitched, diagnostics = stitch_equity_series(
        by_season=season_equity_series,
        season_labels=season_labels
    )
    
    return stitched, diagnostics


def create_mock_price_series(
    season_count: int = 3,
    points_per_season: int = 20,
    base_price: float = 100.0,
    volatility: float = 0.02
) -> Tuple[List[PriceSeries], List[str]]:
    """
    Create mock price series for testing.
    
    Returns:
        Tuple of (list of PriceSeries, season_labels)
    """
    import random
    from datetime import datetime, timedelta
    
    all_series = []
    season_labels = []
    
    for season_idx in range(season_count):
        season_label = f"202{season_idx}Q{season_idx % 4 + 1}"
        season_labels.append(season_label)
        
        timestamps = []
        close_prices = []
        open_prices = []
        
        start_time = datetime(2020 + season_idx, 1, 1)
        current_price = base_price * (1.0 + season_idx * 0.1)  # Slight upward drift
        
        for point_idx in range(points_per_season):
            timestamp = start_time + timedelta(days=point_idx)
            timestamps.append(timestamp.isoformat() + "Z")
            
            # Generate random walk
            price_change = random.uniform(-volatility, volatility)
            current_price *= (1.0 + price_change)
            
            # Simulate open/close with small gap
            open_price = current_price * (1.0 + random.uniform(-0.001, 0.001))
            close_price = current_price * (1.0 + random.uniform(-0.001, 0.001))
            
            open_prices.append(open_price)
            close_prices.append(close_price)
        
        price_series = PriceSeries(
            timestamps=timestamps,
            close_prices=close_prices,
            open_prices=open_prices
        )
        all_series.append(price_series)
    
    return all_series, season_labels


# -----------------------------------------------------------------------------
# Test functions
# -----------------------------------------------------------------------------

def test_bnh_single_season() -> None:
    """Test B&H computation for a single season."""
    print("Testing B&H single season...")
    
    # Create simple price series
    timestamps = [
        "2020-01-01T00:00:00Z",
        "2020-01-02T00:00:00Z",
        "2020-01-03T00:00:00Z",
    ]
    close_prices = [100.0, 105.0, 102.0]
    open_prices = [99.5, 104.5, 101.5]
    
    price_series = PriceSeries(
        timestamps=timestamps,
        close_prices=close_prices,
        open_prices=open_prices
    )
    
    # Simple cost model
    cost_model = CostModel(
        commission_per_trade=1.0,
        slippage_ticks=0.5,
        tick_value=0.25,
        multiplier=2.0
    )
    
    # Compute B&H equity
    equity_points = compute_bnh_equity_for_range(
        price_series=price_series,
        cost_model=cost_model,
        initial_capital=10000.0,
        position_size=1.0
    )
    
    print(f"  Price series: {len(price_series)} bars")
    print(f"  Entry price (open[0]): {open_prices[0]:.2f}")
    print(f"  Exit price (close[-1]): {close_prices[-1]:.2f}")
    print(f"  Price return: {(close_prices[-1] - open_prices[0]) / open_prices[0] * 100:.2f}%")
    print(f"  Total round-trip cost: {cost_model.total_round_trip_cost():.2f}")
    print(f"  Equity points: {len(equity_points)}")
    
    # Check that equity starts near 0 and ends at net return
    if equity_points:
        print(f"  Start equity: {equity_points[0]['v']:.4f}")
        print(f"  End equity: {equity_points[-1]['v']:.4f}")
        
        # Should be approximately linear
        assert abs(equity_points[0]['v']) < 0.01  # Start near 0
        assert abs(equity_points[-1]['v'] - equity_points[0]['v']) > 0.01  # Some movement
    
    print("  ✓ Single season B&H test passed")


def test_bnh_multiple_seasons() -> None:
    """Test B&H computation and stitching for multiple seasons."""
    print("\nTesting B&H multiple seasons...")
    
    # Create mock price series
    season_series, season_labels = create_mock_price_series(
        season_count=3,
        points_per_season=10
    )
    
    # Simple cost model
    cost_model = CostModel(
        commission_per_trade=1.0,
        slippage_ticks=0.5,
        tick_value=0.25,
        multiplier=2.0
    )
    
    # Compute stitched B&H equity
    stitched, diagnostics = compute_bnh_equity_for_seasons(
        season_price_series=season_series,
        season_labels=season_labels,
        cost_model=cost_model,
        initial_capital=10000.0,
        position_size=1.0
    )
    
    print(f"  Seasons: {len(season_series)}")
    print(f"  Total stitched points: {len(stitched)}")
    print(f"  Diagnostics: {len(diagnostics)}")
    
    # Check stitching
    assert len(stitched) == sum(len(series) for series in season_series)
    assert len(diagnostics) == len(season_series)
    
    # Show diagnostics
    for diag in diagnostics:
        print(f"    Season {diag['season']}: jump_abs={diag['jump_abs']:.2f}, jump_pct={diag['jump_pct']:.2f}%")
    
    print("  ✓ Multiple seasons B&H test passed")


def test_cost_model() -> None:
    """Test cost model calculations."""
    print("\nTesting cost model...")
    
    cost_model = CostModel(
        commission_per_trade=2.5,
        slippage_ticks=1.0,
        tick_value=0.25,
        multiplier=5.0
    )
    
    entry_cost = cost_model.total_entry_cost()
    exit_cost = cost_model.total_exit_cost()
    round_trip = cost_model.total_round_trip_cost()
    
    print(f"  Commission per trade: {cost_model.commission_per_trade}")
    print(f"  Slippage ticks: {cost_model.slippage_ticks}")
    print(f"  Tick value: {cost_model.tick_value}")
    print(f"  Multiplier: {cost_model.multiplier}")
    print(f"  Entry cost: {entry_cost:.2f}")
    print(f"  Exit cost: {exit_cost:.2f}")
    print(f"  Round-trip cost: {round_trip:.2f}")
    
    # Verify calculations
    expected_slippage_cost = 1.0 * 0.25 * 5.0  # 1.25
    expected_entry = 2.5 + expected_slippage_cost  # 3.75
    expected_exit = 2.5 + expected_slippage_cost  # 3.75
    expected_round_trip = 7.5
    
    assert abs(entry_cost - expected_entry) < 0.01
    assert abs(exit_cost - expected_exit) < 0.01
    assert abs(round_trip - expected_round_trip) < 0.01
    
    print("  ✓ Cost model test passed")


if __name__ == "__main__":
    test_cost_model()
    test_bnh_single_season()
    test_bnh_multiple_seasons()
    
    print("\n✓ All B&H baseline tests completed")