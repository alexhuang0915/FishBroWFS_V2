#!/usr/bin/env python3
"""
Deployment TXT MVP.

Generates three TXT files for MultiCharts consumption:
- strategy_params.txt: mapping of strategy IDs to parameter sets
- portfolio.txt: portfolio legs (symbol, timeframe, strategy)
- universe.txt: instrument specifications (tick size, multiplier, costs)

Phase 2: Minimal viable product.
"""
import sys
from pathlib import Path
from typing import Dict, Any, List

# Ensure the package root is in sys.path when running as script
if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from portfolio.spec import PortfolioSpec, PortfolioLeg


def write_deployment_txt(
    portfolio_spec: PortfolioSpec,
    universe_spec: Dict[str, Any],
    output_dir: Path,
) -> None:
    """
    Write deployment TXT files.

    Args:
        portfolio_spec: PortfolioSpec instance
        universe_spec: Dictionary mapping instrument symbol to dict with keys:
            tick_size, multiplier, commission_per_side_usd, session_profile
        output_dir: Directory where TXT files will be written
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    # 1. strategy_params.txt
    # Collect unique strategy param combos across legs
    param_sets: Dict[str, Dict[str, float]] = {}
    for leg in portfolio_spec.legs:
        key = f"{leg.strategy_id}_{leg.strategy_version}"
        # Use param hash? For now just store params
        param_sets[key] = leg.params

    with open(output_dir / "strategy_params.txt", "w", encoding="utf-8") as f:
        f.write("# strategy_id,param1=value,param2=value,...\n")
        for key, params in param_sets.items():
            param_str = ",".join(f"{k}={v}" for k, v in params.items())
            f.write(f"{key},{param_str}\n")

    # 2. portfolio.txt
    with open(output_dir / "portfolio.txt", "w", encoding="utf-8") as f:
        f.write("# leg_id,symbol,timeframe_min,strategy_id,strategy_version,enabled\n")
        for leg in portfolio_spec.legs:
            f.write(f"{leg.leg_id},{leg.symbol},{leg.timeframe_min},"
                    f"{leg.strategy_id},{leg.strategy_version},{leg.enabled}\n")

    # 3. universe.txt
    with open(output_dir / "universe.txt", "w", encoding="utf-8") as f:
        f.write("# symbol,tick_size,multiplier,commission_per_side_usd,session_profile\n")
        for symbol, spec in universe_spec.items():
            tick = spec.get("tick_size", 0.25)
            mult = spec.get("multiplier", 1.0)
            comm = spec.get("commission_per_side_usd", 0.0)
            sess = spec.get("session_profile", "GLOBEX")
            f.write(f"{symbol},{tick},{mult},{comm},{sess}\n")


def generate_example() -> None:
    """Generate example deployment TXT files for testing."""
    from portfolio.spec import PortfolioLeg, PortfolioSpec

    # Example portfolio spec
    legs = [
        PortfolioLeg(
            leg_id="mnq_60_sma",
            symbol="CME.MNQ",
            timeframe_min=60,
            session_profile="CME",
            strategy_id="sma_cross",
            strategy_version="v1",
            params={"fast_period": 10.0, "slow_period": 20.0},
            enabled=True,
        ),
        PortfolioLeg(
            leg_id="mes_60_breakout",
            symbol="CME.MES",
            timeframe_min=60,
            session_profile="CME",
            strategy_id="breakout_channel_v1",
            strategy_version="v1",
            params={"channel_period": 20, "atr_multiplier": 2.0},
            enabled=True,
        ),
    ]
    portfolio = PortfolioSpec(
        portfolio_id="example_portfolio",
        version="2026Q1",
        legs=legs,
    )

    # Example universe spec
    universe = {
        "CME.MNQ": {
            "tick_size": 0.25,
            "multiplier": 2.0,
            "commission_per_side_usd": 2.8,
            "session_profile": "CME",
        },
        "CME.MES": {
            "tick_size": 0.25,
            "multiplier": 5.0,
            "commission_per_side_usd": 2.8,
            "session_profile": "CME",
        },
        "TWF.MXF": {
            "tick_size": 1.0,
            "multiplier": 50.0,
            "commission_per_side_usd": 20.0,
            "session_profile": "TAIFEX",
        },
    }

    output_dir = Path("outputs/deployment_example")
    write_deployment_txt(portfolio, universe, output_dir)
    print(f"Example deployment TXT files written to {output_dir}")


if __name__ == "__main__":
    generate_example()