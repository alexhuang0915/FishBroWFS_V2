"""
Research Service - Canonical research runner for CLI and Desktop.

Provides a unified entrypoint for research jobs that ensures:
1. Same pipeline as research_cli
2. Preflight validation of bars source
3. Proper error handling and logging
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional, Callable, Any

from control.research_runner import run_research, ResearchRunError
from control.bars_store import resampled_bars_path, load_npz
from control.build_context import BuildContext

logger = logging.getLogger(__name__)


def run_research_job(
    *,
    season: str,
    dataset_id: str,
    strategy_id: str,
    outputs_root: str = "outputs",
    mode: str = "full",
    verbose: bool = False,
    log_cb: Callable[[str], None] | None = None,
) -> dict:
    """
    Runs the canonical research pipeline and returns metrics/report dict.
    Must raise an Exception on failure.
    
    Args:
        season: Season identifier, e.g., "2026Q1"
        dataset_id: Dataset ID, e.g., "CBOT.ZN"
        strategy_id: Strategy ID, e.g., "S1"
        outputs_root: Root outputs directory
        mode: Build mode ("full" or "incremental") - only used if allow_build=True
        verbose: Enable verbose logging
        log_cb: Callback for streaming logs, accepts text string
    
    Returns:
        dict containing at least:
            success: bool
            metrics: dict including net_profit, max_dd, trades, fills_count if available
            artifacts / run directory path if the pipeline provides it
    
    Raises:
        Exception: On any failure during research execution
    """
    def _log(text: str) -> None:
        if log_cb:
            log_cb(text)
        if verbose:
            logger.info(text)
    
    _log(f"Starting research job: {strategy_id} on {dataset_id} ({season})")
    
    # Convert outputs_root to Path
    outputs_root_path = Path(outputs_root)
    
    # Preflight validation: check bars source exists
    _log("Performing preflight validation...")
    try:
        # Determine expected timeframe for the strategy
        # For now, default to 60m for S1 to match current research_cli behavior
        # TODO: Get timeframe from strategy registry or UI selection
        timeframe_min = 60  # Default for S1
        
        bars_path = resampled_bars_path(
            outputs_root_path, season, dataset_id, timeframe_min
        )
        _log(f"Checking bars source: {bars_path}")
        
        if not bars_path.exists():
            raise FileNotFoundError(
                f"Bars source not found: {bars_path}\n"
                f"Please ensure shared build has been run for season={season}, dataset={dataset_id}"
            )
        
        # Load NPZ to verify keys
        bars_data = load_npz(bars_path)
        required_keys = {"open", "high", "low", "close", "volume", "ts"}
        found_keys = set(bars_data.keys())
        missing_keys = required_keys - found_keys
        
        if missing_keys:
            raise ValueError(
                f"Bars source missing required keys: {missing_keys}\n"
                f"Found keys: {sorted(found_keys)}\n"
                f"Expected at least: {sorted(required_keys)}\n"
                f"Path: {bars_path}"
            )
        
        _log(f"Preflight passed: bars source valid with {len(bars_data)} arrays")
        
    except Exception as e:
        error_msg = f"Preflight validation failed: {e}"
        _log(f"ERROR: {error_msg}")
        raise RuntimeError(error_msg) from e
    
    # Run research pipeline (same as research_cli)
    # Note: We don't pass allow_build=True by default to match CLI behavior
    # Desktop should ensure bars are built before running research
    try:
        _log(f"Executing research pipeline for {strategy_id}...")
        
        # Call the same function that research_cli uses
        report = run_research(
            season=season,
            dataset_id=dataset_id,
            strategy_id=strategy_id,
            outputs_root=outputs_root_path,
            allow_build=False,  # Desktop should pre-build bars
            build_ctx=None,  # No build context since allow_build=False
            wfs_config=None,  # Use default WFS config
            enable_slippage_stress=False,  # Desktop doesn't need stress test
        )
        
        # Transform report to match expected output format
        result = {
            "success": True,
            "strategy_id": report["strategy_id"],
            "dataset_id": report["dataset_id"],
            "season": report["season"],
            "build_performed": report.get("build_performed", False),
            "metrics": _extract_metrics_from_report(report),
            "report": report,
        }
        
        # Add artifacts path if available
        if "wfs_summary" in report and "run_dir" in report["wfs_summary"]:
            result["artifacts_path"] = report["wfs_summary"]["run_dir"]
        
        _log(f"Research job completed successfully")
        return result
        
    except ResearchRunError as e:
        error_msg = f"Research execution failed: {e}"
        _log(f"ERROR: {error_msg}")
        raise RuntimeError(error_msg) from e
    except Exception as e:
        error_msg = f"Unexpected error during research execution: {e}"
        _log(f"ERROR: {error_msg}")
        raise RuntimeError(error_msg) from e


def _extract_metrics_from_report(report: dict) -> dict:
    """
    Extract metrics from research report.
    
    WFS summary may contain metrics like net_profit, max_dd, etc.
    This function standardizes the metrics extraction.
    """
    metrics = {}
    
    # Try to extract from wfs_summary
    wfs_summary = report.get("wfs_summary", {})
    
    # Common metric keys to look for
    metric_keys = [
        "net_profit", "max_dd", "trades", "fills_count",
        "total_pnl", "sharpe", "win_rate", "profit_factor"
    ]
    
    for key in metric_keys:
        if key in wfs_summary:
            metrics[key] = wfs_summary[key]
    
    # If no metrics found, provide defaults
    if not metrics:
        metrics = {
            "net_profit": 0.0,
            "max_dd": 0.0,
            "trades": 0,
            "fills_count": 0,
        }
    
    return metrics


def preflight_bars_source(
    season: str,
    dataset_id: str,
    timeframe_min: int,
    outputs_root: str = "outputs",
) -> dict:
    """
    Preflight validation of bars source.
    
    Args:
        season: Season identifier
        dataset_id: Dataset ID
        timeframe_min: Timeframe in minutes
        outputs_root: Root outputs directory
    
    Returns:
        dict with validation results including:
            valid: bool
            bars_path: str
            keys_found: list[str]
            keys_missing: list[str]
            error: str | None
    
    Raises:
        Exception: Only if fatal error occurs (not validation failure)
    """
    outputs_root_path = Path(outputs_root)
    
    try:
        bars_path = resampled_bars_path(
            outputs_root_path, season, dataset_id, timeframe_min
        )
        
        if not bars_path.exists():
            return {
                "valid": False,
                "bars_path": str(bars_path),
                "keys_found": [],
                "keys_missing": ["open", "high", "low", "close", "volume", "ts"],
                "error": f"File not found: {bars_path}",
            }
        
        # Load NPZ to verify keys
        bars_data = load_npz(bars_path)
        required_keys = {"open", "high", "low", "close", "volume", "ts"}
        found_keys = set(bars_data.keys())
        missing_keys = required_keys - found_keys
        
        return {
            "valid": len(missing_keys) == 0,
            "bars_path": str(bars_path),
            "keys_found": sorted(found_keys),
            "keys_missing": sorted(missing_keys),
            "error": f"Missing keys: {missing_keys}" if missing_keys else None,
            "bars_count": len(bars_data.get("close", [])),
        }
        
    except Exception as e:
        return {
            "valid": False,
            "bars_path": "",
            "keys_found": [],
            "keys_missing": ["open", "high", "low", "close", "volume", "ts"],
            "error": f"Error loading bars: {e}",
        }