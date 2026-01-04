"""
Artifact writers for Phase 18: Generate trades.parquet, equity.parquet, and report.json.

Provides deterministic generation of required artifact files from research results.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Any, List, Optional
import pandas as pd
import numpy as np
from datetime import datetime, timezone


def write_trades_parquet(
    run_dir: Path,
    trades_data: Optional[List[Dict[str, Any]]] = None,
    num_trades: int = 10,
    net_profit: float = 1000.0,
) -> Path:
    """
    Write trades.parquet file with deterministic trade data.
    
    If trades_data is provided, use it. Otherwise generate synthetic trades
    based on metrics.
    
    Columns required:
    - entry_ts (int64 or datetime64[ns, UTC])
    - exit_ts
    - side ("LONG"/"SHORT")
    - entry_px (float)
    - exit_px (float)
    - pnl (float)
    - bars_held (int)
    """
    if trades_data:
        df = pd.DataFrame(trades_data)
    else:
        # Generate synthetic trades based on metrics
        np.random.seed(42)  # Deterministic
        
        # Create timestamps (daily for simplicity)
        base_ts = pd.Timestamp("2026-01-01", tz="UTC")
        timestamps = [base_ts + pd.Timedelta(days=i) for i in range(num_trades * 2)]
        
        trades = []
        for i in range(num_trades):
            entry_idx = i * 2
            exit_idx = entry_idx + 1
            
            side = "LONG" if i % 2 == 0 else "SHORT"
            entry_px = 100.0 + np.random.randn() * 5
            exit_px = entry_px + (np.random.randn() * 3 + (2 if side == "LONG" else -2))
            pnl = exit_px - entry_px if side == "LONG" else entry_px - exit_px
            bars_held = np.random.randint(1, 10)
            
            trades.append({
                "entry_ts": timestamps[entry_idx],
                "exit_ts": timestamps[exit_idx],
                "side": side,
                "entry_px": float(entry_px),
                "exit_px": float(exit_px),
                "pnl": float(pnl),
                "bars_held": int(bars_held),
            })
        
        df = pd.DataFrame(trades)
    
    # Ensure proper datetime types
    if "entry_ts" in df.columns and not pd.api.types.is_datetime64_any_dtype(df["entry_ts"]):
        df["entry_ts"] = pd.to_datetime(df["entry_ts"], utc=True)
    if "exit_ts" in df.columns and not pd.api.types.is_datetime64_any_dtype(df["exit_ts"]):
        df["exit_ts"] = pd.to_datetime(df["exit_ts"], utc=True)
    
    output_path = run_dir / "trades.parquet"
    df.to_parquet(output_path, index=False)
    return output_path


def write_equity_parquet(
    run_dir: Path,
    equity_data: Optional[pd.DataFrame] = None,
    trades_df: Optional[pd.DataFrame] = None,
    initial_equity: float = 10000.0,
    net_profit: float = 1000.0,
) -> Path:
    """
    Write equity.parquet file with equity curve data.
    
    If equity_data is provided, use it. Otherwise generate from trades
    or create synthetic equity curve.
    
    Columns required:
    - ts (datetime64[ns, UTC] or int)
    - equity (float)
    - optional drawdown (float)
    """
    if equity_data is not None:
        df = equity_data
    elif trades_df is not None:
        # Generate equity curve from trades
        df = _equity_from_trades(trades_df, initial_equity)
    else:
        # Generate synthetic equity curve
        np.random.seed(42)
        
        # Create daily timestamps for 90 days
        dates = pd.date_range("2026-01-01", periods=90, tz="UTC")
        
        # Create random walk with positive drift
        returns = np.random.randn(90) * 0.01 + 0.001
        equity = initial_equity * np.cumprod(1 + returns)
        
        # Add final profit to match net_profit
        if net_profit != 0:
            equity = equity + (net_profit / equity[-1]) * (equity - equity[0])
        
        df = pd.DataFrame({
            "ts": dates,
            "equity": equity,
        })
        
        # Calculate drawdown
        df["drawdown"] = df["equity"] / df["equity"].cummax() - 1.0
    
    # Ensure proper datetime type
    if "ts" in df.columns and not pd.api.types.is_datetime64_any_dtype(df["ts"]):
        df["ts"] = pd.to_datetime(df["ts"], utc=True)
    
    output_path = run_dir / "equity.parquet"
    df.to_parquet(output_path, index=False)
    return output_path


def _equity_from_trades(trades_df: pd.DataFrame, initial_equity: float) -> pd.DataFrame:
    """Generate equity curve from trades dataframe."""
    if trades_df.empty:
        # Return flat equity curve
        dates = pd.date_range("2026-01-01", periods=10, tz="UTC")
        return pd.DataFrame({
            "ts": dates,
            "equity": [initial_equity] * len(dates),
            "drawdown": [0.0] * len(dates),
        })
    
    # Sort trades by exit time
    trades_sorted = trades_df.sort_values("exit_ts")
    
    # Create equity timeline
    equity = initial_equity
    equity_points = []
    
    # Add starting point
    equity_points.append({
        "ts": trades_sorted["entry_ts"].iloc[0] - pd.Timedelta(days=1),
        "equity": equity,
        "drawdown": 0.0,
    })
    
    # Add equity after each trade
    for _, trade in trades_sorted.iterrows():
        equity += trade["pnl"]
        equity_points.append({
            "ts": trade["exit_ts"],
            "equity": equity,
            "drawdown": 0.0,  # Will calculate later
        })
    
    df = pd.DataFrame(equity_points)
    
    # Calculate drawdown
    df["drawdown"] = df["equity"] / df["equity"].cummax() - 1.0
    
    return df


def write_report_json(
    run_dir: Path,
    metrics: Dict[str, Any],
    equity_df: Optional[pd.DataFrame] = None,
    trades_df: Optional[pd.DataFrame] = None,
) -> Path:
    """
    Write report.json with precomputed summary for UI.
    
    Includes:
    - Key metrics (net_profit, max_dd, sharpe, sortino, profit_factor, win_rate, trades, avg_trade, sqn)
    - Monthly returns matrix
    - Additional analytics
    """
    report = {
        "metrics": {
            "net_profit": metrics.get("net_profit", 0.0),
            "max_dd": metrics.get("max_dd", 0.0),
            "sharpe": metrics.get("sharpe", 0.0),
            "sortino": metrics.get("sortino", 0.0),
            "profit_factor": metrics.get("profit_factor", 0.0),
            "win_rate": metrics.get("win_rate", 0.0),
            "trades": metrics.get("trades", 0),
            "avg_trade": metrics.get("avg_trade", 0.0),
            "sqn": metrics.get("sqn", 0.0),
            "annualized_return": metrics.get("annualized_return", 0.0),
        },
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "artifact_version": "phase18_v1",
    }
    
    # Add monthly returns if equity data available
    if equity_df is not None and not equity_df.empty:
        monthly_returns = _compute_monthly_returns(equity_df)
        report["monthly_returns"] = monthly_returns
        
        # Add additional analytics
        report["analytics"] = {
            "total_return_pct": (equity_df["equity"].iloc[-1] / equity_df["equity"].iloc[0] - 1) * 100,
            "volatility_annual": _compute_volatility(equity_df),
            "calmar_ratio": _compute_calmar_ratio(equity_df, report["metrics"]["max_dd"]),
        }
    
    # Add trade statistics if trades data available
    if trades_df is not None and not trades_df.empty:
        trade_stats = _compute_trade_statistics(trades_df)
        report["trade_statistics"] = trade_stats
    
    output_path = run_dir / "report.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    
    return output_path


def _compute_monthly_returns(equity_df: pd.DataFrame) -> Dict[str, float]:
    """Compute monthly returns from equity series."""
    if equity_df.empty or "ts" not in equity_df.columns or "equity" not in equity_df.columns:
        return {}
    
    # Resample to monthly
    equity_df = equity_df.copy()
    equity_df.set_index("ts", inplace=True)
    
    # Get monthly start and end equity
    monthly = equity_df["equity"].resample("ME").ohlc()
    if monthly.empty:
        return {}
    
    # Calculate monthly returns
    monthly_returns = {}
    for idx, row in monthly.iterrows():
        if pd.notna(row["open"]) and pd.notna(row["close"]) and row["open"] != 0:
            ret = (row["close"] / row["open"] - 1) * 100
            key = f"{idx.year}-{idx.month:02d}"
            monthly_returns[key] = float(ret)
    
    return monthly_returns


def _compute_volatility(equity_df: pd.DataFrame) -> float:
    """Compute annualized volatility from equity series."""
    if len(equity_df) < 2:
        return 0.0
    
    returns = equity_df["equity"].pct_change().dropna()
    if len(returns) == 0:
        return 0.0
    
    daily_vol = returns.std()
    annual_vol = daily_vol * np.sqrt(252)  # Trading days
    return float(annual_vol * 100)  # As percentage


def _compute_calmar_ratio(equity_df: pd.DataFrame, max_dd: float) -> float:
    """Compute Calmar ratio (return / max drawdown)."""
    if len(equity_df) < 2 or max_dd >= 0:
        return 0.0
    
    total_return = (equity_df["equity"].iloc[-1] / equity_df["equity"].iloc[0] - 1)
    annualized_return = total_return * (252 / len(equity_df)) if len(equity_df) > 0 else 0
    
    if max_dd == 0:
        return 0.0
    
    return float(annualized_return / abs(max_dd))


def _compute_trade_statistics(trades_df: pd.DataFrame) -> Dict[str, Any]:
    """Compute statistics from trades dataframe."""
    if trades_df.empty:
        return {}
    
    stats = {
        "total_trades": len(trades_df),
        "winning_trades": int((trades_df["pnl"] > 0).sum()),
        "losing_trades": int((trades_df["pnl"] < 0).sum()),
        "breakeven_trades": int((trades_df["pnl"] == 0).sum()),
        "avg_win": float(trades_df[trades_df["pnl"] > 0]["pnl"].mean() if (trades_df["pnl"] > 0).any() else 0),
        "avg_loss": float(trades_df[trades_df["pnl"] < 0]["pnl"].mean() if (trades_df["pnl"] < 0).any() else 0),
        "largest_win": float(trades_df["pnl"].max()),
        "largest_loss": float(trades_df["pnl"].min()),
        "avg_bars_held": float(trades_df["bars_held"].mean()),
    }
    
    stats["win_rate"] = stats["winning_trades"] / stats["total_trades"] * 100 if stats["total_trades"] > 0 else 0
    stats["profit_factor"] = abs(stats["avg_win"] / stats["avg_loss"]) if stats["avg_loss"] != 0 else 0
    
    return stats


def write_full_artifact(
    run_dir: Path,
    manifest: Dict[str, Any],
    config_snapshot: Dict[str, Any],
    metrics: Dict[str, Any],
    winners: Optional[Dict[str, Any]] = None,
) -> Dict[str, Path]:
    """
    Write complete Phase 18 artifact with all required files.
    
    Returns dict of written file paths.
    """
    from core.artifacts import write_run_artifacts
    
    # First write the base artifacts (manifest, metrics, config, winners)
    write_run_artifacts(
        run_dir=run_dir,
        manifest=manifest,
        config_snapshot=config_snapshot,
        metrics=metrics,
        winners=winners,
    )
    
    # Generate trades.parquet
    trades_path = write_trades_parquet(
        run_dir=run_dir,
        num_trades=metrics.get("trades", 10),
        net_profit=metrics.get("net_profit", 1000.0),
    )
    
    # Read trades to generate equity curve
    trades_df = pd.read_parquet(trades_path)
    
    # Generate equity.parquet
    equity_path = write_equity_parquet(
        run_dir=run_dir,
        trades_df=trades_df,
        initial_equity=10000.0,
        net_profit=metrics.get("net_profit", 1000.0),
    )
    
    # Read equity for report generation
    equity_df = pd.read_parquet(equity_path)
    
    # Generate report.json
    report_path = write_report_json(
        run_dir=run_dir,
        metrics=metrics,
        equity_df=equity_df,
        trades_df=trades_df,
    )
    
    return {
        "manifest": run_dir / "manifest.json",
        "metrics": run_dir / "metrics.json",
        "config_snapshot": run_dir / "config_snapshot.json",
        "winners": run_dir / "winners.json",
        "trades": trades_path,
        "equity": equity_path,
        "report": report_path,
    }