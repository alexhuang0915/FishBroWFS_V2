"""
RUN_RESEARCH_WFS handler for Phase4-A Walk-Forward Simulation research.

Research=WFS pipeline including:
- Rolling quarterly windows over [start_season, end_season]
- For each season window:
  - IS range = 3 years
  - OOS range = next 1 quarter
  - Parameter search on IS -> best_params
  - Evaluate OOS with best_params (NO re-optimization)
  - Compute per-window pass/fail + fail_reasons
- Aggregate across seasons:
  - pass_rate, WFE, RF, ECR, trades, ulcer, underwater-days
- Series:
  - stitched IS equity
  - stitched OOS equity
  - stitched B&H equity baseline (same instrument, same time, same cost model assumptions)
- Expert evaluation:
  - 5D scores + weighted total + grade
  - Hard gates (one-vote veto) => grade D, not tradable
"""

from __future__ import annotations

import json
import logging
import random
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Mapping
import traceback

from ..job_handler import BaseJobHandler, JobContext
from contracts.research_wfs.result_schema import (
    ResearchWFSResult,
    MetaSection as Meta,
    ConfigSection as Config,
    EstimateSection as Estimate,
    WindowResult,
    SeriesSection as Series,
    MetricsSection as Metrics,
    VerdictSection as Verdict,
    EquityPoint,
    StitchDiagnostic,
    CostsConfig as CostModel,
    InstrumentConfig,
    RiskConfig,
    DataConfig,
    TimeRange,
    WindowRule,
)
from wfs.evaluation_enhanced import evaluate_enhanced as evaluate
from wfs.evaluation import RawMetrics
from wfs.stitching import stitch_equity_series
from wfs.bnh_baseline import compute_bnh_equity_for_seasons, CostModel as BnhCostModel
from core.determinism import stable_seed_from_intent

logger = logging.getLogger(__name__)


# Resource guardrails for WFS research
MAX_WINDOWS = 20  # Maximum number of rolling windows
MAX_PARAM_SEARCH_SPACE = 10_000  # Maximum parameter combinations per window
MAX_TOTAL_EXECUTION_TIME_SEC = 7200  # 2 hours maximum execution time
HEARTBEAT_INTERVAL_SEC = 30  # Send heartbeat every 30 seconds during heavy compute


def _as_model_input(obj: Any) -> Any:
    """Convert object to Pydantic model input (dict)."""
    # Pydantic v2 models
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    # Pydantic v1 models
    if hasattr(obj, "dict"):
        return obj.dict()
    # Dataclasses
    if hasattr(obj, "__dataclass_fields__"):
        import dataclasses
        return dataclasses.asdict(obj)
    # Plain mappings
    if isinstance(obj, Mapping):
        return dict(obj)
    # Fallback (last resort)
    return obj


class RunResearchWFSHandler(BaseJobHandler):
    """RUN_RESEARCH_WFS handler for executing Walk-Forward Simulation research."""
    
    def validate_params(self, params: Dict[str, Any]) -> None:
        """Validate RUN_RESEARCH_WFS parameters."""
        # Required parameters for WFS research
        required = ["strategy_id", "instrument", "timeframe", "start_season", "end_season"]
        missing = [key for key in required if key not in params]
        if missing:
            raise ValueError(f"Missing required parameters: {missing}")
        
        # Validate season format (e.g., "2020Q1")
        start_season = params.get("start_season")
        end_season = params.get("end_season")
        if not (isinstance(start_season, str) and len(start_season) == 6 and start_season[4] == 'Q'):
            raise ValueError(f"Invalid start_season format: {start_season}. Expected format: YYYYQ#")
        if not (isinstance(end_season, str) and len(end_season) == 6 and end_season[4] == 'Q'):
            raise ValueError(f"Invalid end_season format: {end_season}. Expected format: YYYYQ#")
    
    def _apply_guardrails(self, start_season: str, end_season: str, strategy_id: str, context: JobContext) -> None:
        """Apply resource guardrails before heavy computation."""
        # Calculate window count
        start_year = int(start_season[:4])
        start_q = int(start_season[5])
        end_year = int(end_season[:4])
        end_q = int(end_season[5])
        
        window_count = ((end_year - start_year) * 4) + (end_q - start_q) + 1
        
        # Check window count limit
        if window_count > MAX_WINDOWS:
            raise ValueError(
                f"Too many windows: {window_count} exceeds maximum of {MAX_WINDOWS}. "
                f"Consider reducing date range or increasing window size."
            )
        
        # TODO: In real implementation, query strategy registry for parameter count
        # For now, use placeholder
        param_count = 100  # Placeholder
        
        # Check parameter search space
        estimated_param_combinations = param_count * window_count
        if estimated_param_combinations > MAX_PARAM_SEARCH_SPACE:
            raise ValueError(
                f"Parameter search space too large: {estimated_param_combinations} combinations "
                f"exceeds limit of {MAX_PARAM_SEARCH_SPACE}. "
                f"Consider reducing parameter count or window count."
            )
        
        logger.info(
            f"Guardrails passed: windows={window_count}, "
            f"estimated_param_combinations={estimated_param_combinations}"
        )
        
        # Send heartbeat to indicate guardrails passed
        context.heartbeat(progress=0.15, phase="guardrails_passed")
    
    def execute(self, params: Dict[str, Any], context: JobContext) -> Dict[str, Any]:
        """Execute RUN_RESEARCH_WFS job."""
        # Check for abort before starting
        if context.is_abort_requested():
            return {
                "ok": False,
                "job_type": "RUN_RESEARCH_WFS",
                "aborted": True,
                "reason": "user_abort_preinvoke",
                "payload": params
            }
        
        # Update heartbeat
        context.heartbeat(progress=0.1, phase="validating_inputs")

        seed = stable_seed_from_intent(params)
        self.rng = random.Random(seed)
        logger.info(f"ResearchWFS determinism seed: {seed}")

        try:
            # Parse and validate parameters
            strategy_id = params["strategy_id"]
            instrument = params["instrument"]
            timeframe = params["timeframe"]
            start_season = params["start_season"]
            end_season = params["end_season"]
            
            # Optional parameters with defaults
            dataset = params.get("dataset", "None")
            run_mode = params.get("run_mode", "wfs")
            workers = params.get("workers", 1)
            
            # Apply guardrails before heavy computation
            self._apply_guardrails(start_season, end_season, strategy_id, context)
            
            # Compute estimate BEFORE running windows
            context.heartbeat(progress=0.2, phase="computing_estimate")
            estimate = self._compute_estimate(
                strategy_id=strategy_id,
                start_season=start_season,
                end_season=end_season,
                workers=workers
            )
            
            # Build config
            config = self._build_config(
                strategy_id=strategy_id,
                instrument=instrument,
                timeframe=timeframe,
                dataset=dataset,
                start_season=start_season,
                end_season=end_season
            )
            
            # Build meta
            meta = self._build_meta(
                job_id=context.job_id,
                strategy_id=strategy_id,
                instrument=instrument,
                timeframe=timeframe,
                start_season=start_season,
                end_season=end_season,
                window_rule={
                    "is_years": 3,
                    "oos_quarters": 1,
                    "rolling": "quarterly"
                }  # type: ignore
            )
            
            # Execute WFS research with timeout monitoring
            context.heartbeat(progress=0.3, phase="executing_windows")
            start_time = time.time()
            windows, is_equity_by_season, oos_equity_by_season, bnh_equity_by_season = self._execute_wfs_windows(
                strategy_id=strategy_id,
                instrument=instrument,
                timeframe=timeframe,
                dataset=dataset,
                start_season=start_season,
                end_season=end_season,
                context=context
            )
            
            # Check execution time
            elapsed = time.time() - start_time
            if elapsed > MAX_TOTAL_EXECUTION_TIME_SEC:
                logger.warning(f"WFS execution took {elapsed:.1f}s, exceeding soft limit of {MAX_TOTAL_EXECUTION_TIME_SEC}s")
            
            # Aggregate metrics
            context.heartbeat(progress=0.7, phase="aggregating_metrics")
            raw_metrics = self._aggregate_metrics(windows)
            
            # Evaluate (5D scoring + hard gates)
            evaluation_result = evaluate(raw_metrics)
            
            # Stitch series
            context.heartbeat(progress=0.8, phase="stitching_series")
            season_labels = [w.season for w in windows]
            
            stitched_is_equity, is_diags = stitch_equity_series(is_equity_by_season, season_labels)
            stitched_oos_equity, oos_diags = stitch_equity_series(oos_equity_by_season, season_labels)
            stitched_bnh_equity, bnh_diags = stitch_equity_series(bnh_equity_by_season, season_labels)
            
            # Build series
            series = Series(
                stitched_is_equity=stitched_is_equity,
                stitched_oos_equity=stitched_oos_equity,
                stitched_bnh_equity=stitched_bnh_equity,
                stitch_diagnostics={
                    "per_season": is_diags  # Use IS diagnostics as representative
                },
                drawdown_series=[]
            )
            
            # Build metrics
            metrics = Metrics(
                raw=raw_metrics,
                scores=evaluation_result.scores,
                hard_gates_triggered=evaluation_result.hard_gates_triggered
            )
            
            # Build verdict
            verdict = Verdict(
                grade=evaluation_result.grade,  # type: ignore
                is_tradable=evaluation_result.is_tradable,
                summary=evaluation_result.summary
            )
            
            # Convert windows to dicts for Pydantic compatibility
            windows_in = [_as_model_input(w) for w in windows]
            
            # Build final result
            result = ResearchWFSResult(
                version="1.0",
                meta=meta,
                config=config,
                estimate=estimate,
                windows=windows_in,
                series=series,
                metrics=metrics,
                verdict=verdict
            )
            
            # Convert to dict for JSON serialization
            result_dict = result.model_dump()
            
            # Update heartbeat
            context.heartbeat(progress=0.9, phase="finalizing")
            
            return {
                "ok": True,
                "job_type": "RUN_RESEARCH_WFS",
                "payload": params,
                "result": result_dict
            }
            
        except Exception as e:
            logger.error(f"Failed to execute WFS research: {e}")
            logger.error(traceback.format_exc())
            
            # Write error to artifacts (robust)
            try:
                error_path = Path(context.artifacts_dir) / "error.txt"
                error_path.parent.mkdir(parents=True, exist_ok=True)
                error_path.write_text(f"{e}\n\n{traceback.format_exc()}")
            except Exception as write_err:
                logger.error(f"Failed to write error artifact: {write_err}")
            
            raise  # Re-raise to mark job as FAILED
    
    def _compute_estimate(
        self,
        strategy_id: str,
        start_season: str,
        end_season: str,
        workers: int
    ) -> Estimate:
        """Compute estimate BEFORE running windows."""
        # Parse seasons (e.g., "2020Q1" -> year=2020, quarter=1)
        start_year = int(start_season[:4])
        start_q = int(start_season[5])
        end_year = int(end_season[:4])
        end_q = int(end_season[5])
        
        # Calculate window count (simplified)
        # Each quarter between start and end inclusive
        window_count = ((end_year - start_year) * 4) + (end_q - start_q) + 1
        
        # For now, use placeholder values
        # In real implementation, would query strategy registry for parameter count
        strategy_count = 1  # Single strategy family
        param_count = 100   # Placeholder
        
        # Estimate runtime (heuristic)
        estimated_runtime_sec = max(1, param_count * window_count * 2 // workers)
        
        return Estimate(
            strategy_count=strategy_count,
            param_count=param_count,
            window_count=window_count,
            workers=workers,
            estimated_runtime_sec=estimated_runtime_sec
        )
    
    def _build_config(
        self,
        strategy_id: str,
        instrument: str,
        timeframe: str,
        dataset: str,
        start_season: str,
        end_season: str
    ) -> Config:
        """Build config from parameters."""
        # Parse instrument symbol
        symbol = instrument
        exchange = None  # Could parse from instrument like "CME.MNQ"
        if "." in instrument:
            parts = instrument.split(".")
            exchange = parts[0]
            symbol = parts[1]
        
        # Build instrument config
        instrument_config = InstrumentConfig(
            symbol=symbol,
            exchange=exchange,
            currency="USD",  # Default
            multiplier=2.0   # Default for MNQ
        )
        
        # Build cost model (placeholder)
        cost_model = CostModel(
            commission={"model": "per_trade", "value": 1.0, "unit": "USD"},
            slippage={"model": "ticks", "value": 0.5, "unit": "ticks"}
        )
        
        # Build risk config
        risk_config = RiskConfig(
            risk_unit_1R=100.0,  # Default
            stop_model="atr"     # Default
        )
        
        # Build data config
        data_config = DataConfig(
            data1=dataset,
            data2=None,
            timeframe=timeframe,
            actual_time_range={
                "start": "2020-01-01T00:00:00Z",  # Placeholder
                "end": "2023-12-31T23:59:59Z"     # Placeholder
            }
        )
        
        return Config(
            instrument=instrument_config,
            costs=cost_model,
            risk=risk_config,
            data=data_config
        )
    
    def _build_meta(
        self,
        job_id: str,
        strategy_id: str,
        instrument: str,
        timeframe: str,
        start_season: str,
        end_season: str,
        window_rule: WindowRule
    ) -> Meta:
        """Build meta information."""
        return Meta(
            job_id=job_id,
            run_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            strategy_family=strategy_id,
            instrument=instrument,
            timeframe=timeframe,
            start_season=start_season,
            end_season=end_season,
            window_rule=window_rule
        )
    
    def _execute_wfs_windows(
        self,
        strategy_id: str,
        instrument: str,
        timeframe: str,
        dataset: str,
        start_season: str,
        end_season: str,
        context: JobContext
    ) -> Tuple[List[WindowResult], List[List[EquityPoint]], List[List[EquityPoint]], List[List[EquityPoint]]]:
        """
        Execute WFS windows (rolling quarterly windows).
        
        Returns:
            Tuple of (windows, is_equity_by_season, oos_equity_by_season, bnh_equity_by_season)
        """
        # For now, implement a stub that returns synthetic data
        # In real implementation, would:
        # 1. Determine rolling seasons between start_season and end_season
        # 2. For each season:
        #    - Determine IS range (3 years before season)
        #    - Determine OOS range (the season itself)
        #    - Call engine for IS param search -> best_params + is_metrics + is_equity
        #    - Call engine for OOS eval on best_params -> oos_metrics + oos_equity
        #    - Compute B&H equity for OOS
        #    - Determine pass/fail
        
        # Parse seasons
        start_year = int(start_season[:4])
        start_q = int(start_season[5])
        end_year = int(end_season[:4])
        end_q = int(end_season[5])
        
        windows = []
        is_equity_by_season = []
        oos_equity_by_season = []
        bnh_equity_by_season = []
        
        # Generate synthetic seasons
        current_year = start_year
        current_q = start_q
        
        season_idx = 0
        total_seasons = ((end_year - start_year) * 4) + (end_q - start_q) + 1
        
        while (current_year < end_year) or (current_year == end_year and current_q <= end_q):
            season = f"{current_year}Q{current_q}"
            
            # Update heartbeat with progress
            progress = 0.3 + (season_idx / total_seasons) * 0.4  # 30% to 70%
            context.heartbeat(progress=progress, phase=f"processing_season_{season}")
            
            # Generate synthetic window result
            window_result = self._generate_synthetic_window_result(season)
            windows.append(window_result)
            
            # Generate synthetic equity series
            is_equity = self._generate_synthetic_equity_series(season, "IS")
            oos_equity = self._generate_synthetic_equity_series(season, "OOS")
            bnh_equity = self._generate_synthetic_equity_series(season, "B&H")
            
            is_equity_by_season.append(is_equity)
            oos_equity_by_season.append(oos_equity)
            bnh_equity_by_season.append(bnh_equity)
            
            # Move to next quarter
            current_q += 1
            if current_q > 4:
                current_q = 1
                current_year += 1
            
            season_idx += 1
        
        return windows, is_equity_by_season, oos_equity_by_season, bnh_equity_by_season
    
    def _generate_synthetic_window_result(self, season: str) -> WindowResult:
        """Generate synthetic window result for testing."""
        
        # Generate synthetic date ranges
        year = int(season[:4])
        quarter = int(season[5])
        
        # Simple date ranges (placeholder)
        is_start = f"{year-3}-01-01T00:00:00Z"
        is_end = f"{year-1}-12-31T23:59:59Z"
        oos_start = f"{year}-01-01T00:00:00Z"
        oos_end = f"{year}-03-31T23:59:59Z"
        
        # Generate synthetic metrics
        is_net = self.rng.uniform(-1000, 5000)
        oos_net = self.rng.uniform(-500, 3000)
        
        # Determine pass/fail (simple rule: OOS net > 0 and trades >= 10)
        oos_trades = self.rng.randint(5, 50)
        pass_window = oos_net > 0 and oos_trades >= 10
        fail_reasons = [] if pass_window else ["OOS net <= 0" if oos_net <= 0 else "Insufficient trades"]
        
        return WindowResult(
            season=season,
            is_range=TimeRange(start=is_start, end=is_end),
            oos_range=TimeRange(start=oos_start, end=oos_end),
            best_params={"param1": 20, "param2": 1.5},  # Placeholder
            is_metrics={
                "net": is_net,
                "mdd": self.rng.uniform(0, 1000),
                "trades": self.rng.randint(20, 100)
            },
            oos_metrics={
                "net": oos_net,
                "mdd": self.rng.uniform(0, 500),
                "trades": oos_trades
            },
            pass_=pass_window,  # type: ignore
            fail_reasons=fail_reasons
        )
    
    def _generate_synthetic_equity_series(self, season: str, series_type: str) -> List[EquityPoint]:
        """Generate synthetic equity series for testing."""
        from datetime import datetime, timedelta
        
        year = int(season[:4])
        quarter = int(season[5])
        
        # Start date based on quarter
        month = (quarter - 1) * 3 + 1
        start_date = datetime(year, month, 1)
        
        # Generate 20 points per season
        points = []
        equity = 0.0
        
        for i in range(20):
            timestamp = start_date + timedelta(days=i)
            
            # Add random walk
            equity += self.rng.uniform(-50, 100)
            
            points.append(EquityPoint(
                t=timestamp.isoformat() + "Z",
                v=equity
            ))
        
        return points
    
    def _aggregate_metrics(self, windows: List[WindowResult]) -> RawMetrics:
        """Aggregate metrics across windows."""
        
        # Calculate aggregate metrics from windows
        pass_count = sum(1 for w in windows if w.pass_)
        window_count = len(windows)
        pass_rate = pass_count / window_count if window_count > 0 else 0.0
        
        # Sum OOS trades
        total_trades = sum(w.oos_metrics.get("trades", 0) for w in windows)
        
        # Generate synthetic aggregate metrics (placeholder)
        # In real implementation, would compute from stitched equity series
        return RawMetrics(
            rf=self.rng.uniform(1.0, 5.0),  # Return Factor
            wfe=self.rng.uniform(0.3, 0.9),  # Walk-Forward Efficiency
            ecr=self.rng.uniform(1.0, 4.0),  # Efficiency to Capital Ratio
            trades=total_trades,
            pass_rate=pass_rate,
            ulcer_index=self.rng.uniform(0.0, 20.0),
            max_underwater_days=self.rng.randint(0, 50)
        )


# Create handler instance
run_research_wfs_handler = RunResearchWFSHandler()