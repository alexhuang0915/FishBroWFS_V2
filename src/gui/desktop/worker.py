"""
Desktop worker for backtest execution in a separate thread.
"""

import logging
import traceback
import os
from pathlib import Path
from typing import Dict, Any, Optional

from PySide6.QtCore import QObject, Signal

from control.research_service import run_research_job, preflight_bars_source
from strategy.registry import load_builtin_strategies

logger = logging.getLogger(__name__)




class BacktestWorker(QObject):
    """Worker for executing a single backtest job."""
    
    # Signals
    log_signal = Signal(str)
    progress_signal = Signal(int)  # 0-100
    finished_signal = Signal(dict)  # payload contract
    failed_signal = Signal(str)    # error string
    
    def __init__(self, strategy: str, primary_market: str, timeframe: int, context_feeds: Optional[list] = None):
        super().__init__()
        self.strategy = strategy
        self.primary_market = primary_market  # Maps to dataset_id
        self.timeframe = timeframe
        self.context_feeds = context_feeds or []
        self.job_id: Optional[str] = None
        self._stop_requested = False
    
    def run(self):
        """Main execution method to be run in a QThread."""
        try:
            self.log_signal.emit(f"Starting backtest: {self.strategy}, {self.primary_market}, {self.timeframe}m")
            if self.context_feeds:
                self.log_signal.emit(f"Context feeds: {self.context_feeds}")
            
            # Ensure strategies are loaded
            try:
                load_builtin_strategies()
            except ValueError as e:
                if "already registered" not in str(e):
                    raise
            
            # Determine season (currently hardcoded to match research_cli)
            # TODO: Make season configurable in UI
            season = "2026Q1"
            
            # Preflight validation
            self.log_signal.emit("Performing preflight validation...")
            preflight_result = preflight_bars_source(
                season=season,
                dataset_id=self.primary_market,  # Map primary_market to dataset_id
                timeframe_min=self.timeframe,
                outputs_root="outputs",
            )
            
            if not preflight_result["valid"]:
                error_msg = (
                    f"Preflight validation failed:\n"
                    f"  Bars path: {preflight_result['bars_path']}\n"
                    f"  Error: {preflight_result['error']}\n"
                    f"  Missing keys: {preflight_result['keys_missing']}"
                )
                self.log_signal.emit(f"ERROR: {error_msg}")
                raise RuntimeError(error_msg)
            
            self.log_signal.emit(f"Preflight passed: bars source valid at {preflight_result['bars_path']}")
            self.log_signal.emit(f"Found keys: {preflight_result['keys_found']}")
            
            # Run the canonical research job
            self.log_signal.emit("Executing research pipeline...")
            self.progress_signal.emit(10)  # Indeterminate progress start
            
            result = run_research_job(
                season=season,
                dataset_id=self.primary_market,  # Map primary_market to dataset_id
                strategy_id=self.strategy,
                outputs_root="outputs",
                mode="full",
                verbose=True,
                log_cb=lambda text: self.log_signal.emit(text),
            )
            
            self.progress_signal.emit(100)
            self.log_signal.emit("Research job completed successfully")
            
            # Extract and emit results
            final_result = self._extract_results(result)
            self.finished_signal.emit(final_result)
                
        except Exception as e:
            error_msg = f"{type(e).__name__}: {str(e)}"
            self.log_signal.emit(f"Error: {error_msg}")
            self.log_signal.emit(traceback.format_exc())
            self.failed_signal.emit(error_msg)
    
    def _extract_results(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """Extract results from research job result and create canonical run."""
        metrics = result.get("metrics", {})
        report = result.get("report", {})
        
        # Extract key metrics
        pnl = metrics.get("net_profit", 0.0)
        maxdd = metrics.get("max_dd", 0.0)
        trades = metrics.get("trades", 0)
        fills_count = metrics.get("fills_count", 0)
        
        # Extract artifact path if available
        artifact_path = result.get("artifacts_path", "")
        if not artifact_path and "wfs_summary" in report:
            artifact_path = report["wfs_summary"].get("run_dir", "")
        
        # Create canonical run artifact
        run_id = report.get("run_id", "")
        if not run_id:
            # Generate a run_id if not provided
            import hashlib
            from datetime import datetime
            timestamp = datetime.now().isoformat()
            run_id = f"run_{hashlib.sha1(timestamp.encode()).hexdigest()[:8]}"
        
        
        return {
            "success": True,
            "pnl": float(pnl),
            "maxdd": float(maxdd),
            "trades": int(trades),
            "fills_count": int(fills_count),
            "artifact_path": artifact_path,
            "run_id": run_id,
            "strategy_id": result.get("strategy_id", self.strategy),
            "dataset_id": result.get("dataset_id", self.primary_market),
            "primary_market": self.primary_market,
            "context_feeds": self.context_feeds,
            "season": result.get("season", "2026Q1"),
            "metrics": metrics,
        }
    
    def stop(self):
        """Request stop of the worker."""
        self._stop_requested = True


class BuildWorker(QObject):
    """Worker for building bars/features cache with Data2 dependency enforcement."""
    
    # Signals
    log_signal = Signal(str)
    progress_signal = Signal(int)  # 0-100
    finished_signal = Signal(dict)  # payload contract
    failed_signal = Signal(str)    # error string
    
    def __init__(self, dataset: str, txt_path: Path, build_bars: bool, build_features: bool,
                 mode: str = "FULL", context_feeds: Optional[list] = None):
        super().__init__()
        self.dataset = dataset
        self.txt_path = txt_path
        self.build_bars = build_bars
        self.build_features = build_features
        self.mode = mode
        self.context_feeds = context_feeds or []
        self._stop_requested = False
    
    def run(self):
        """Main execution method to be run in a QThread."""
        try:
            from control.prepare_orchestration import prepare_with_data2_enforcement
            from datetime import datetime
            
            self.log_signal.emit(f"Starting {self.mode} build for dataset {self.dataset}")
            self.log_signal.emit(f"TXT path: {self.txt_path}")
            self.log_signal.emit(f"Build bars: {self.build_bars}, Build features: {self.build_features}")
            
            if self.context_feeds:
                self.log_signal.emit(f"Data2 feeds to prepare: {self.context_feeds}")
            
            # Determine season (use current quarter as placeholder)
            # In a real implementation, we might get this from config
            season = "2026Q1"
            
            # Call the prepare orchestration function with Data2 enforcement
            self.log_signal.emit(f"Calling prepare_with_data2_enforcement with mode={self.mode}...")
            self.progress_signal.emit(10)
            
            # Load allowed timeframes from registry
            from src.config.registry.timeframes import load_timeframes
            timeframe_registry = load_timeframes()
            allowed_timeframes = timeframe_registry.allowed_timeframes
            
            result = prepare_with_data2_enforcement(
                season=season,
                data1_dataset_id=self.dataset,
                data1_txt_path=self.txt_path,
                data2_feeds=self.context_feeds,
                outputs_root=Path("outputs"),
                mode=self.mode,
                build_bars=self.build_bars,
                build_features=self.build_features,
                tfs=allowed_timeframes,
            )
            
            if not result["success"]:
                error_msg = result.get("error", "Unknown error in prepare orchestration")
                raise RuntimeError(error_msg)
            
            self.progress_signal.emit(100)
            self.log_signal.emit(f"Prepare completed successfully")
            
            # Log Data2 preparation results
            if self.context_feeds:
                self.log_signal.emit(f"Data2 preparation summary:")
                for feed_id in self.context_feeds:
                    if feed_id in result.get("data2_reports", {}):
                        self.log_signal.emit(f"  {feed_id}: auto-built")
                    else:
                        self.log_signal.emit(f"  {feed_id}: already prepared")
            
            # Emit finished signal with payload
            payload = {
                "success": True,
                "dataset": self.dataset,
                "mode": self.mode,
                "build_bars": self.build_bars,
                "build_features": self.build_features,
                "context_feeds": self.context_feeds,
                "result": result,
                "no_change": result.get("no_change", True),
            }
            self.finished_signal.emit(payload)
            
        except Exception as e:
            error_msg = f"{type(e).__name__}: {str(e)}"
            self.log_signal.emit(f"Build error: {error_msg}")
            import traceback
            self.log_signal.emit(traceback.format_exc())
            self.failed_signal.emit(error_msg)
    
    def stop(self):
        """Request stop of the worker."""
        self._stop_requested = True


class ArtifactWorker(QObject):
    """Worker for building artifacts (Admission/Compile)."""
    
    # Signals
    log_signal = Signal(str)
    progress_signal = Signal(int)  # 0-100
    finished_signal = Signal(dict)  # payload contract
    failed_signal = Signal(str)    # error string
    
    def __init__(self, strategy: str, dataset: str, season: str, research_result: dict):
        super().__init__()
        self.strategy = strategy
        self.dataset = dataset
        self.season = season
        self.research_result = research_result
        self._stop_requested = False
    
    def run(self):
        """Main execution method to be run in a QThread."""
        try:
            self.log_signal.emit(f"Starting artifact build for {self.strategy} on {self.dataset} ({self.season})")
            
            # Import artifact creation functions
            from core.run_id import make_run_id
            from core.paths import ensure_run_dir
            from core.artifacts import write_run_artifacts
            from core.audit_schema import AuditSchema
            from core.config_snapshot import make_config_snapshot
            from datetime import datetime, timezone
            
            # Generate run_id
            run_id = make_run_id(prefix=f"artifact_{self.strategy}")
            self.log_signal.emit(f"Generated run_id: {run_id}")
            
            # Create run directory
            outputs_root = Path("outputs")
            run_dir = ensure_run_dir(outputs_root, self.season, run_id)
            self.log_signal.emit(f"Created run directory: {run_dir}")
            
            # Build config snapshot from research result
            config_snapshot = {
                "strategy_id": self.strategy,
                "dataset_id": self.dataset,
                "season": self.season,
                "research_result": self.research_result,
                "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            }
            
            # Build manifest (AuditSchema)
            from core.config_hash import stable_config_hash
            config_hash = stable_config_hash(config_snapshot)
            
            audit = AuditSchema(
                run_id=run_id,
                created_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                git_sha="desktop-build",
                dirty_repo=False,
                param_subsample_rate=1.0,  # Default for research
                config_hash=config_hash,
                season=self.season,
                dataset_id=self.dataset,
                bars=0,  # Placeholder
                params_total=0,  # Placeholder
                params_effective=0,  # Placeholder
                artifact_version="v1",
            )
            
            # Build metrics from research result
            metrics = {
                "net_profit": self.research_result.get("pnl", 0),
                "max_dd": self.research_result.get("maxdd", 0),
                "trades": self.research_result.get("trades", 0),
                "fills_count": self.research_result.get("fills_count", 0),
                "stage_name": "research",
                "param_subsample_rate": 1.0,
                "params_effective": 0,
                "params_total": 0,
                "bars": 0,
            }
            
            # Write full Phase 18 artifacts
            self.log_signal.emit("Writing Phase 18 artifacts (trades, equity, report)...")
            
            # First write base artifacts
            from core.artifacts import write_run_artifacts
            write_run_artifacts(
                run_dir=run_dir,
                manifest=audit.to_dict(),
                config_snapshot=config_snapshot,
                metrics=metrics,
                winners=None,
            )
            
            # Then write Phase 18 required files
            try:
                from core.artifact_writers import write_full_artifact
                written_files = write_full_artifact(
                    run_dir=run_dir,
                    manifest=audit.to_dict(),
                    config_snapshot=config_snapshot,
                    metrics=metrics,
                    winners=None,
                )
                self.log_signal.emit(f"Generated full artifact: {list(written_files.keys())}")
            except Exception as e:
                self.log_signal.emit(f"WARNING: Failed to write Phase 18 files: {e}")
                self.log_signal.emit("Artifact will be incomplete (missing trades/equity/report)")
            
            self.progress_signal.emit(100)
            self.log_signal.emit(f"Artifact build completed successfully")
            
            # Emit finished signal with payload
            payload = {
                "success": True,
                "run_id": run_id,
                "run_dir": str(run_dir),
                "season": self.season,
                "strategy": self.strategy,
                "dataset": self.dataset,
            }
            self.finished_signal.emit(payload)
            
        except Exception as e:
            error_msg = f"{type(e).__name__}: {str(e)}"
            self.log_signal.emit(f"Artifact build error: {error_msg}")
            import traceback
            self.log_signal.emit(traceback.format_exc())
            self.failed_signal.emit(error_msg)
    
    def stop(self):
        """Request stop of the worker."""
        self._stop_requested = True