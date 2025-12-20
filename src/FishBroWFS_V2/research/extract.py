"""Result Extractor - extract canonical metrics from artifacts.

Phase 9: Read-only extraction from existing artifacts.
No computation, only aggregation from existing data.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from FishBroWFS_V2.research.metrics import CanonicalMetrics


class ExtractionError(Exception):
    """Raised when required artifacts or fields are missing."""
    pass


def extract_canonical_metrics(run_dir: Path) -> CanonicalMetrics:
    """
    Extract canonical metrics from run artifacts.
    
    Reads artifacts from run_dir (at least one of manifest/metrics/config_snapshot/README must exist).
    Uses field mapping table to map artifact fields to CanonicalMetrics.
    
    Args:
        run_dir: Path to run directory
        
    Returns:
        CanonicalMetrics instance
        
    Raises:
        ExtractionError: If required artifacts or fields are missing
    """
    # Check at least one artifact exists
    manifest_path = run_dir / "manifest.json"
    metrics_path = run_dir / "metrics.json"
    config_path = run_dir / "config_snapshot.json"
    winners_path = run_dir / "winners.json"
    
    if not any(p.exists() for p in [manifest_path, metrics_path, config_path]):
        raise ExtractionError(f"No artifacts found in {run_dir}")
    
    # Load available artifacts
    manifest: Dict[str, Any] = {}
    metrics_data: Dict[str, Any] = {}
    config_data: Dict[str, Any] = {}
    winners: Dict[str, Any] = {}
    
    if manifest_path.exists():
        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                manifest = json.load(f)
        except json.JSONDecodeError as e:
            raise ExtractionError(f"Invalid manifest.json: {e}")
    
    if metrics_path.exists():
        try:
            with open(metrics_path, "r", encoding="utf-8") as f:
                metrics_data = json.load(f)
        except json.JSONDecodeError as e:
            raise ExtractionError(f"Invalid metrics.json: {e}")
    
    if config_path.exists():
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config_data = json.load(f)
        except json.JSONDecodeError as e:
            raise ExtractionError(f"Invalid config_snapshot.json: {e}")
    
    if winners_path.exists():
        try:
            with open(winners_path, "r", encoding="utf-8") as f:
                winners = json.load(f)
        except json.JSONDecodeError as e:
            raise ExtractionError(f"Invalid winners.json: {e}")
    
    # Field mapping table: artifact field -> CanonicalMetrics field
    # Extract identification
    run_id = manifest.get("run_id") or metrics_data.get("run_id")
    if not run_id:
        raise ExtractionError("Missing 'run_id' in artifacts")
    
    portfolio_id = manifest.get("portfolio_id") or config_data.get("portfolio_id")
    portfolio_version = manifest.get("portfolio_version") or config_data.get("portfolio_version")
    
    # Strategy info from winners.json topk (take first item if available)
    strategy_id = None
    strategy_version = None
    symbol = None
    timeframe_min = None
    
    topk = winners.get("topk", [])
    if topk and isinstance(topk, list) and len(topk) > 0:
        first_item = topk[0]
        strategy_id = first_item.get("strategy_id")
        symbol = first_item.get("symbol")
        # timeframe_min might be in config or need parsing from timeframe string
        timeframe_str = first_item.get("timeframe", "")
        if timeframe_str and timeframe_str != "UNKNOWN":
            # Try to extract minutes from timeframe (e.g., "60m" -> 60)
            try:
                if timeframe_str.endswith("m"):
                    timeframe_min = int(timeframe_str[:-1])
            except ValueError:
                pass
    
    # Extract bars (required)
    bars = manifest.get("bars") or metrics_data.get("bars") or config_data.get("bars")
    if bars is None:
        raise ExtractionError("Missing 'bars' in artifacts")
    
    # Extract dates
    start_date = manifest.get("created_at", "")
    end_date = ""  # Not available in artifacts
    
    # Extract core metrics from winners.json topk aggregation
    # Aggregate net_profit, max_dd, trades from topk
    total_net_profit = 0.0
    max_max_dd = 0.0
    total_trades = 0
    
    for item in topk:
        item_metrics = item.get("metrics", {})
        net_profit = item_metrics.get("net_profit", 0.0)
        max_dd = item_metrics.get("max_dd", 0.0)
        trades = item_metrics.get("trades", 0)
        
        total_net_profit += net_profit
        max_max_dd = min(max_max_dd, max_dd)  # max_dd is negative or 0
        total_trades += trades
    
    net_profit = total_net_profit
    max_drawdown = abs(max_max_dd)  # Convert to positive
    
    # Extract profit_factor and sharpe from metrics (if available)
    # These may not be in artifacts, so allow None
    profit_factor = metrics_data.get("profit_factor")
    sharpe = metrics_data.get("sharpe")
    
    # Calculate derived scores
    # score_net_mdd = net_profit / abs(max_drawdown)
    # If max_drawdown == 0, raise error (as per requirement)
    if max_drawdown == 0.0:
        if net_profit != 0.0:
            # Non-zero profit but zero drawdown - this is edge case
            # Per requirement: "mdd=0 → inf or raise, please define clearly"
            # We'll raise to be explicit
            raise ExtractionError(
                f"max_drawdown is 0 but net_profit is {net_profit}, "
                "cannot calculate score_net_mdd"
            )
        score_net_mdd = 0.0
    else:
        score_net_mdd = net_profit / max_drawdown
    
    # score_final = score_net_mdd * (trades ** 0.25)
    score_final = score_net_mdd * (total_trades ** 0.25) if total_trades > 0 else 0.0
    
    return CanonicalMetrics(
        run_id=run_id,
        portfolio_id=portfolio_id,
        portfolio_version=portfolio_version,
        strategy_id=strategy_id,
        strategy_version=strategy_version,
        symbol=symbol,
        timeframe_min=timeframe_min,
        net_profit=net_profit,
        max_drawdown=max_drawdown,
        profit_factor=profit_factor,
        sharpe=sharpe,
        trades=total_trades,
        score_net_mdd=score_net_mdd,
        score_final=score_final,
        bars=bars,
        start_date=start_date,
        end_date=end_date,
    )
