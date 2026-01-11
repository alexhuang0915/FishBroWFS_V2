"""
RUN_PORTFOLIO_ADMISSION handler for Phase4-B Portfolio Admission analysis.

Portfolio Admission pipeline:
- Consumes Phase4-A result.json files (multiple research runs)
- Performs OOS-only portfolio risk & admission analysis
- Does NOT re-run engine, re-optimize parameters, auto-optimize position sizing, or connect to live data
- Produces portfolio admission artifacts:
  - portfolio_config.json (strict schema)
  - admission_report.json (strict schema)
"""

from __future__ import annotations

import json
import logging
import math
import statistics
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import traceback

from ..job_handler import BaseJobHandler, JobContext
from contracts.research_wfs.result_schema import (
    ResearchWFSResult,
    validate_result_json,
    EquityPoint,
)
from contracts.portfolio.admission_schemas import (
    AdmissionDecision,
    AdmissionVerdict,
)

logger = logging.getLogger(__name__)


def _resample_to_daily_calendar_grid(
    equity_series: List[EquityPoint],
    forward_fill: bool = True
) -> List[EquityPoint]:
    """
    Resample equity series to daily calendar grid.
    
    Args:
        equity_series: List of EquityPoint objects with timestamps
        forward_fill: Whether to forward-fill missing days
        
    Returns:
        List of EquityPoint objects with daily frequency (calendar days)
    """
    if not equity_series:
        return []
    
    # Parse timestamps to datetime objects
    points = []
    for point in equity_series:
        try:
            dt = datetime.fromisoformat(point["t"].replace("Z", "+00:00"))
            points.append((dt, point["v"]))
        except (ValueError, AttributeError):
            continue
    
    if not points:
        return []
    
    # Sort by date
    points.sort(key=lambda x: x[0])
    
    # Determine date range
    start_date = points[0][0].date()
    end_date = points[-1][0].date()
    
    # Create daily grid
    current_date = start_date
    daily_values = {}
    
    # Map existing points to dates
    for dt, value in points:
        date_key = dt.date()
        daily_values[date_key] = value
    
    # Forward fill if requested
    if forward_fill:
        last_value = None
        current_date = start_date
        while current_date <= end_date:
            if current_date in daily_values:
                last_value = daily_values[current_date]
            elif last_value is not None:
                daily_values[current_date] = last_value
            current_date += timedelta(days=1)
    
    # Convert back to EquityPoint format
    result = []
    for date_key in sorted(daily_values.keys()):
        dt = datetime.combine(date_key, datetime.min.time(), tzinfo=timezone.utc)
        result.append(EquityPoint(t=dt.isoformat(), v=daily_values[date_key]))
    
    return result


class RunPortfolioAdmissionHandler(BaseJobHandler):
    """RUN_PORTFOLIO_ADMISSION handler for executing portfolio admission analysis."""
    
    def validate_params(self, params: Dict[str, Any]) -> None:
        """Validate RUN_PORTFOLIO_ADMISSION parameters."""
        required = ["portfolio_id", "result_paths"]
        missing = [key for key in required if key not in params]
        if missing:
            raise ValueError(f"Missing required parameters: {missing}")
        
        result_paths = params.get("result_paths", [])
        if not isinstance(result_paths, list):
            raise ValueError("result_paths must be a list of paths to Phase4-A result.json files")
        
        if len(result_paths) < 1:
            raise ValueError("At least one result.json file is required for portfolio admission")
    
    def execute(self, params: Dict[str, Any], context: JobContext) -> Dict[str, Any]:
        """Execute RUN_PORTFOLIO_ADMISSION job."""
        if context.is_abort_requested():
            return {
                "ok": False,
                "job_type": "RUN_PORTFOLIO_ADMISSION",
                "aborted": True,
                "reason": "user_abort_preinvoke",
                "payload": params
            }
        
        context.heartbeat(progress=0.1, phase="validating_inputs")
        
        try:
            portfolio_id = params["portfolio_id"]
            result_paths = params["result_paths"]
            portfolio_config = params.get("portfolio_config", {})
            
            # Load Phase4-A results
            context.heartbeat(progress=0.2, phase="loading_results")
            research_results = self._load_results(result_paths)
            
            if not research_results:
                raise ValueError("No valid Phase4-A results found")
            
            # Build portfolio configuration
            context.heartbeat(progress=0.3, phase="building_config")
            portfolio_config_obj = self._build_portfolio_config(
                portfolio_id=portfolio_id,
                user_config=portfolio_config,
                research_results=research_results
            )
            
            # Run correlation analysis
            context.heartbeat(progress=0.4, phase="correlation_analysis")
            correlation_result = self._run_correlation_analysis(
                research_results=research_results,
                threshold=portfolio_config_obj.get("correlation_threshold", 0.7)
            )
            
            # Determine admitted runs with portfolio stacking
            context.heartbeat(progress=0.6, phase="determining_admission")
            admitted_run_ids, rejected_run_ids, reasons = self._determine_admission(
                research_results=research_results,
                correlation_violations=correlation_result["violations"],
                portfolio_config=portfolio_config_obj
            )
            
            # Generate admission decision
            context.heartbeat(progress=0.7, phase="generating_decision")
            admission_decision = AdmissionDecision(
                verdict=AdmissionVerdict.ADMITTED if admitted_run_ids else AdmissionVerdict.REJECTED,
                admitted_run_ids=admitted_run_ids,
                rejected_run_ids=rejected_run_ids,
                reasons=reasons,
                portfolio_id=portfolio_id,
                evaluated_at_utc=datetime.now(timezone.utc).isoformat()
            )
            
            # Compute Phase4-B.1 enhanced analytics
            context.heartbeat(progress=0.8, phase="computing_enhanced_analytics")
            enhanced_analytics = self._compute_enhanced_analytics(
                admitted_run_ids=admitted_run_ids,
                research_results=research_results,
                portfolio_config=portfolio_config_obj
            )
            
            # Write artifacts with enhanced analytics
            context.heartbeat(progress=0.9, phase="writing_artifacts")
            self._write_artifacts(
                context=context,
                portfolio_config=portfolio_config_obj,
                admission_decision=admission_decision,
                correlation_result=correlation_result,
                research_results=research_results,
                enhanced_analytics=enhanced_analytics
            )
            
            return {
                "ok": True,
                "job_type": "RUN_PORTFOLIO_ADMISSION",
                "payload": params,
                "result": {
                    "portfolio_id": portfolio_id,
                    "admitted_runs": len(admitted_run_ids),
                    "rejected_runs": len(rejected_run_ids),
                    "verdict": admission_decision.verdict.value,
                    "summary": f"Admitted {len(admitted_run_ids)} of {len(research_results)} runs"
                }
            }
            
        except Exception as e:
            logger.error(f"Failed to execute portfolio admission: {e}")
            logger.error(traceback.format_exc())
            
            error_path = Path(context.artifacts_dir) / "error.txt"
            error_path.write_text(f"{e}\n\n{traceback.format_exc()}")
            
            raise
    
    def _load_results(self, result_paths: List[str]) -> Dict[str, ResearchWFSResult]:
        """Load and validate Phase4-A result.json files."""
        results = {}
        
        for path_str in result_paths:
            path = Path(path_str)
            if not path.exists():
                logger.warning(f"Result file not found: {path}")
                continue
            
            try:
                with open(path, "r", encoding="utf-8") as f:
                    json_str = f.read()
                
                result = validate_result_json(json_str)
                job_id = result.meta.job_id
                results[job_id] = result
                logger.info(f"Loaded result for job {job_id}")
                
            except Exception as e:
                logger.error(f"Failed to load/validate result file {path}: {e}")
                continue
        
        return results
    
    def _build_portfolio_config(
        self,
        portfolio_id: str,
        user_config: Dict[str, Any],
        research_results: Dict[str, ResearchWFSResult]
    ) -> Dict[str, Any]:
        """Build portfolio configuration."""
        now = datetime.now(timezone.utc).isoformat()
        
        # Extract common currency
        currencies = set()
        for result in research_results.values():
            currency = result.config.instrument.get("currency", "USD")
            currencies.add(currency)
        
        common_currency = "USD"
        if len(currencies) == 1:
            common_currency = list(currencies)[0]
        elif "USD" in currencies:
            common_currency = "USD"
        
        # Phase4-B.1 enhanced portfolio configuration
        config = {
            "portfolio_id": portfolio_id,
            "name": user_config.get("name", f"Portfolio {portfolio_id[:8]}"),
            "description": user_config.get("description", "Automatically generated portfolio"),
            "currency": common_currency,
            "target_volatility": float(user_config.get("target_volatility", 0.15)),
            "max_drawdown_limit_pct": float(user_config.get("max_drawdown_limit_pct", 20.0)),
            "max_drawdown_limit_abs": float(user_config.get("max_drawdown_limit_abs", 10000.0)),
            "correlation_threshold": float(user_config.get("correlation_threshold", 0.7)),
            "correlation_threshold_warn": float(user_config.get("correlation_threshold_warn", 0.70)),
            "correlation_threshold_reject": float(user_config.get("correlation_threshold_reject", 0.85)),
            "min_lots_per_strategy": int(user_config.get("min_lots_per_strategy", 1)),
            "max_lots_per_strategy": int(user_config.get("max_lots_per_strategy", 10)),
            "total_capital": float(user_config.get("total_capital", 100000.0)),
            "risk_budget_per_strategy": float(user_config.get("risk_budget_per_strategy", 0.1)),
            "rolling_mdd_3m_limit": float(user_config.get("rolling_mdd_3m_limit", 12.0)),
            "rolling_mdd_6m_limit": float(user_config.get("rolling_mdd_6m_limit", 18.0)),
            "rolling_mdd_full_limit": float(user_config.get("rolling_mdd_full_limit", 25.0)),
            "noise_buffer_sharpe": float(user_config.get("noise_buffer_sharpe", 0.05)),
            "created_at": now,
            "updated_at": now,
        }
        
        return config
    
    def _run_correlation_analysis(
        self,
        research_results: Dict[str, ResearchWFSResult],
        threshold: float
    ) -> Dict[str, Any]:
        """Run correlation gate analysis on daily returns (Phase4-B.1 enhancement)."""
        run_ids = list(research_results.keys())
        violations = []
        warnings = []
        
        # Convert equity series to daily returns for each run (with calendar resampling)
        daily_returns = {}
        for run_id in run_ids:
            equity_series = research_results[run_id].series.stitched_oos_equity
            # Resample to daily calendar grid first
            daily_equity = _resample_to_daily_calendar_grid(equity_series, forward_fill=True)
            daily_returns[run_id] = self._equity_to_daily_returns(daily_equity)
        
        # Compute pairwise correlations on daily returns
        for i, run_id1 in enumerate(run_ids):
            for j, run_id2 in enumerate(run_ids):
                if i >= j:
                    continue
                
                # Compute correlation on daily returns
                correlation = self._compute_correlation_from_daily_returns(
                    daily_returns[run_id1], daily_returns[run_id2]
                )
                
                # Check for violations (absolute correlation > threshold)
                if abs(correlation) > threshold:
                    violations.append({
                        "run_id1": run_id1,
                        "run_id2": run_id2,
                        "correlation": correlation,
                        "threshold": threshold,
                        "type": "VIOLATION"
                    })
                # Check for warnings (correlation > 0.7 but <= threshold)
                elif abs(correlation) > 0.7:
                    warnings.append({
                        "run_id1": run_id1,
                        "run_id2": run_id2,
                        "correlation": correlation,
                        "threshold": 0.7,
                        "type": "WARNING"
                    })
        
        return {
            "passed": len(violations) == 0,
            "violations": violations,
            "warnings": warnings,
            "threshold": threshold,
            "total_pairs": len(run_ids) * (len(run_ids) - 1) // 2,
            "violating_pairs": len(violations),
            "warning_pairs": len(warnings)
        }
    
    def _equity_to_daily_returns(self, equity_series: List[EquityPoint]) -> List[Dict[str, float]]:
        """Convert equity series to daily returns."""
        if len(equity_series) < 2:
            return []
        
        returns = []
        sorted_series = sorted(equity_series, key=lambda x: x["t"])
        
        for i in range(1, len(sorted_series)):
            prev_value = sorted_series[i-1]["v"]
            curr_value = sorted_series[i]["v"]
            
            if prev_value != 0:
                daily_return = (curr_value - prev_value) / abs(prev_value)
            else:
                daily_return = 0.0
            
            returns.append({
                "t": sorted_series[i]["t"],
                "r": daily_return
            })
        
        return returns
    
    def _compute_correlation_from_daily_returns(
        self,
        returns1: List[Dict[str, float]],
        returns2: List[Dict[str, float]]
    ) -> float:
        """Compute Pearson correlation from daily returns."""
        # Align returns by date
        returns1_dict = {r["t"]: r["r"] for r in returns1}
        returns2_dict = {r["t"]: r["r"] for r in returns2}
        
        common_dates = set(returns1_dict.keys()) & set(returns2_dict.keys())
        if len(common_dates) < 2:
            return 0.0
        
        # Extract aligned returns
        aligned_returns1 = [returns1_dict[date] for date in sorted(common_dates)]
        aligned_returns2 = [returns2_dict[date] for date in sorted(common_dates)]
        
        # Compute Pearson correlation
        n = len(aligned_returns1)
        mean1 = sum(aligned_returns1) / n
        mean2 = sum(aligned_returns2) / n
        
        numerator = sum((r1 - mean1) * (r2 - mean2) for r1, r2 in zip(aligned_returns1, aligned_returns2))
        denominator1 = sum((r1 - mean1) ** 2 for r1 in aligned_returns1)
        denominator2 = sum((r2 - mean2) ** 2 for r2 in aligned_returns2)
        
        if denominator1 == 0 or denominator2 == 0:
            return 0.0
        
        correlation = numerator / math.sqrt(denominator1 * denominator2)
        return max(-1.0, min(1.0, correlation))
    
    def _compute_correlation(self, series1: List[EquityPoint], series2: List[EquityPoint]) -> float:
        """Compute correlation between two equity series (legacy method)."""
        # Simplified implementation - kept for backward compatibility
        if not series1 or not series2:
            return 0.0
        
        # Extract values
        values1 = [p["v"] for p in series1]
        values2 = [p["v"] for p in series2]
        
        # Use minimum length
        n = min(len(values1), len(values2))
        if n < 2:
            return 0.0
        
        values1 = values1[:n]
        values2 = values2[:n]
        
        # Compute means
        mean1 = sum(values1) / n
        mean2 = sum(values2) / n
        
        # Compute covariance and variances
        cov = sum((v1 - mean1) * (v2 - mean2) for v1, v2 in zip(values1, values2)) / n
        var1 = sum((v1 - mean1) ** 2 for v1 in values1) / n
        var2 = sum((v2 - mean2) ** 2 for v2 in values2) / n
        
        if var1 == 0 or var2 == 0:
            return 0.0
        
        correlation = cov / math.sqrt(var1 * var2)
        return max(-1.0, min(1.0, correlation))
    
    def _determine_admission(
        self,
        research_results: Dict[str, ResearchWFSResult],
        correlation_violations: List[Dict[str, Any]],
        portfolio_config: Dict[str, Any]
    ) -> Tuple[List[str], List[str], Dict[str, str]]:
        """Determine which runs should be admitted with portfolio stacking (Phase4-B.1)."""
        run_ids = list(research_results.keys())
        
        # Identify runs involved in correlation violations
        violating_runs = set()
        for violation in correlation_violations:
            violating_runs.add(violation["run_id1"])
            violating_runs.add(violation["run_id2"])
        
        # Initial filtering based on basic criteria
        candidate_run_ids = []
        initial_rejections = set()
        reasons = {}
        
        for run_id in run_ids:
            result = research_results[run_id]
            
            # Check if run has correlation violations
            if run_id in violating_runs:
                initial_rejections.add(run_id)
                reasons[run_id] = "High correlation with other runs"
                continue
            
            # Check OOS performance
            if not result.windows:
                initial_rejections.add(run_id)
                reasons[run_id] = "No window results available"
                continue
            
            # Check if any window has positive OOS net
            has_positive_oos = any(
                w.oos_metrics.get("net", 0) > 0
                for w in result.windows
            )
            
            if not has_positive_oos:
                initial_rejections.add(run_id)
                reasons[run_id] = "No positive OOS performance"
                continue
            
            # Check if strategy is tradable
            if not result.verdict.is_tradable:
                initial_rejections.add(run_id)
                reasons[run_id] = f"Strategy not tradable: {result.verdict.summary}"
                continue
            
            # All basic checks passed - add to candidates
            candidate_run_ids.append(run_id)
        
        # Apply portfolio stacking with integer lots
        admitted_run_ids = self._apply_portfolio_stacking(
            candidate_run_ids=candidate_run_ids,
            research_results=research_results,
            portfolio_config=portfolio_config
        )
        
        # Determine rejected runs
        rejected_run_ids = [rid for rid in run_ids if rid not in admitted_run_ids]
        
        # Update reasons for runs rejected by portfolio stacking
        for run_id in candidate_run_ids:
            if run_id not in admitted_run_ids and run_id not in reasons:
                reasons[run_id] = "Excluded by portfolio stacking (risk budget constraints)"
        
        return admitted_run_ids, rejected_run_ids, reasons
    
    def _apply_portfolio_stacking(
        self,
        candidate_run_ids: List[str],
        research_results: Dict[str, ResearchWFSResult],
        portfolio_config: Dict[str, Any]
    ) -> List[str]:
        """Apply portfolio stacking with integer lots allocation."""
        if not candidate_run_ids:
            return []
        
        # Extract performance metrics for candidates
        candidate_metrics = {}
        for run_id in candidate_run_ids:
            result = research_results[run_id]
            if result.windows:
                # Use OOS metrics from first window as proxy for performance
                oos_metrics = result.windows[0].oos_metrics
                candidate_metrics[run_id] = {
                    "net": oos_metrics.get("net", 0),
                    "trades": oos_metrics.get("trades", 0),
                    "sharpe_ratio": oos_metrics.get("sharpe_ratio", 0)  # if available
                }
            else:
                candidate_metrics[run_id] = {"net": 0, "trades": 0, "sharpe_ratio": 0}
        
        # Sort candidates by performance (net profit)
        sorted_candidates = sorted(
            candidate_run_ids,
            key=lambda rid: candidate_metrics[rid]["net"],
            reverse=True
        )
        
        # Apply risk budget constraints
        max_strategies = portfolio_config.get("max_lots_per_strategy", 10)
        min_strategies = portfolio_config.get("min_lots_per_strategy", 1)
        total_capital = portfolio_config.get("total_capital", 100000.0)
        risk_budget_per_strategy = portfolio_config.get("risk_budget_per_strategy", 0.1)
        
        # Calculate maximum number of strategies based on risk budget
        max_by_risk_budget = int(total_capital * risk_budget_per_strategy / 10000)  # Simplified
        
        # Determine final allocation
        max_allowed = min(max_strategies, max_by_risk_budget, len(sorted_candidates))
        max_allowed = max(min_strategies, max_allowed)
        
        # Select top performers
        admitted_run_ids = sorted_candidates[:max_allowed]
        
        # Apply integer lots (simplified - 1 lot per strategy)
        # In a real implementation, this would consider position sizing, volatility targeting, etc.
        
        return admitted_run_ids
    
    def _compute_budget_alerts(
        self,
        equity_series: List[EquityPoint],
        portfolio_config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Compute budget alerts from rolling MDD (Phase4-B.1)."""
        # Define window sizes in CALENDAR days (Phase 4-B requirement)
        window_3m = 90  # 3 months = 90 calendar days
        window_6m = 180  # 6 months = 180 calendar days
        
        # First resample to daily calendar grid
        daily_series = _resample_to_daily_calendar_grid(equity_series, forward_fill=True)
        
        # Compute rolling MDDs on daily series
        mdd_3m, start_3m, end_3m = self._compute_rolling_mdd(daily_series, window_3m)
        mdd_6m, start_6m, end_6m = self._compute_rolling_mdd(daily_series, window_6m)
        
        # Compute full period MDD
        mdd_full, start_full, end_full = self._compute_max_drawdown(daily_series)
        
        # Get limits from config
        limit_3m = portfolio_config.get("rolling_mdd_3m_limit", 12.0)
        limit_6m = portfolio_config.get("rolling_mdd_6m_limit", 18.0)
        limit_full = portfolio_config.get("rolling_mdd_full_limit", 25.0)
        
        # Determine worst period
        worst_mdd = max(mdd_3m, mdd_6m, mdd_full)
        if worst_mdd == mdd_3m:
            worst_period = "3M"
        elif worst_mdd == mdd_6m:
            worst_period = "6M"
        else:
            worst_period = "FULL"
        
        return {
            "rolling_3m": {
                "period": "3M",
                "mdd_pct": mdd_3m,
                "limit_pct": limit_3m,
                "triggered": mdd_3m > limit_3m,
                "start_date": start_3m,
                "end_date": end_3m
            },
            "rolling_6m": {
                "period": "6M",
                "mdd_pct": mdd_6m,
                "limit_pct": limit_6m,
                "triggered": mdd_6m > limit_6m,
                "start_date": start_6m,
                "end_date": end_6m
            },
            "rolling_full": {
                "period": "FULL",
                "mdd_pct": mdd_full,
                "limit_pct": limit_full,
                "triggered": mdd_full > limit_full,
                "start_date": start_full,
                "end_date": end_full
            },
            "any_triggered": (mdd_3m > limit_3m) or (mdd_6m > limit_6m) or (mdd_full > limit_full),
            "worst_period": worst_period
        }
    
    def _compute_rolling_mdd(
        self,
        equity_series: List[EquityPoint],
        window_days: int
    ) -> Tuple[float, str, str]:
        """Compute maximum drawdown within a rolling window."""
        if len(equity_series) < 2:
            return 0.0, "", ""
        
        # Sort by date
        sorted_series = sorted(equity_series, key=lambda x: x["t"])
        values = [p["v"] for p in sorted_series]
        dates = [p["t"] for p in sorted_series]
        
        max_drawdown_pct = 0.0
        worst_start_date = ""
        worst_end_date = ""
        
        for i in range(len(values)):
            peak = values[i]
            peak_date = dates[i]
            
            # Look ahead within window
            for j in range(i+1, min(i+window_days+1, len(values))):
                if values[j] > peak:
                    peak = values[j]
                    peak_date = dates[j]
                    continue
                
                drawdown = (peak - values[j]) / peak if peak != 0 else 0.0
                drawdown_pct = drawdown * 100
                
                if drawdown_pct > max_drawdown_pct:
                    max_drawdown_pct = drawdown_pct
                    worst_start_date = peak_date
                    worst_end_date = dates[j]
        
        return max_drawdown_pct, worst_start_date, worst_end_date
    
    def _compute_max_drawdown(
        self,
        equity_series: List[EquityPoint]
    ) -> Tuple[float, str, str]:
        """Compute maximum drawdown for entire series."""
        if len(equity_series) < 2:
            return 0.0, "", ""
        
        # Sort by date
        sorted_series = sorted(equity_series, key=lambda x: x["t"])
        values = [p["v"] for p in sorted_series]
        dates = [p["t"] for p in sorted_series]
        
        max_drawdown_pct = 0.0
        worst_start_date = ""
        worst_end_date = ""
        peak = values[0]
        peak_date = dates[0]
        
        for i in range(1, len(values)):
            if values[i] > peak:
                peak = values[i]
                peak_date = dates[i]
                continue
            
            drawdown = (peak - values[i]) / peak if peak != 0 else 0.0
            drawdown_pct = drawdown * 100
            
            if drawdown_pct > max_drawdown_pct:
                max_drawdown_pct = drawdown_pct
                worst_start_date = peak_date
                worst_end_date = dates[i]
        
        return max_drawdown_pct, worst_start_date, worst_end_date
    
    def _compute_marginal_contribution(
        self,
        admitted_run_ids: List[str],
        research_results: Dict[str, ResearchWFSResult],
        noise_buffer: float = 0.05
    ) -> Dict[str, Any]:
        """Compute marginal contribution analysis with noise buffer (Phase4-B.1)."""
        if not admitted_run_ids:
            return {
                "contributions": {},
                "total_sharpe": 0.0,
                "noise_buffer": noise_buffer,
                "significant_contributors": [],
                "insignificant_contributors": [],
                "diversification_benefit": 0.0,
                "gate2_status": "PASS",  # No members to reject
                "rejected_members": []
            }
        
        # Extract daily returns for admitted runs (with calendar resampling)
        daily_returns = {}
        for run_id in admitted_run_ids:
            equity_series = research_results[run_id].series.stitched_oos_equity
            # Resample to daily calendar grid first
            daily_equity = _resample_to_daily_calendar_grid(equity_series, forward_fill=True)
            returns = self._equity_to_daily_returns(daily_equity)
            # Extract just the return values
            daily_returns[run_id] = [r["r"] for r in returns]
        
        # Compute portfolio returns (simple average)
        portfolio_returns = []
        if daily_returns:
            # Align returns by index (simplified)
            min_length = min(len(returns) for returns in daily_returns.values())
            for i in range(min_length):
                port_return = sum(returns[i] for returns in daily_returns.values()) / len(daily_returns)
                portfolio_returns.append(port_return)
        
        # Compute Sharpe ratios
        portfolio_sharpe = self._compute_sharpe_ratio(portfolio_returns) if portfolio_returns else 0.0
        
        contributions = {}
        significant = []
        insignificant = []
        rejected_members = []
        
        for run_id in admitted_run_ids:
            returns = daily_returns.get(run_id, [])
            if len(returns) < 2:
                delta_sharpe = 0.0
            else:
                # Compute portfolio WITHOUT this member
                other_run_ids = [rid for rid in admitted_run_ids if rid != run_id]
                if other_run_ids:
                    # Compute portfolio returns without this member
                    other_returns = []
                    min_length_other = min(len(daily_returns.get(rid, [])) for rid in other_run_ids)
                    for i in range(min_length_other):
                        other_return = sum(daily_returns.get(rid, [])[i] for rid in other_run_ids) / len(other_run_ids)
                        other_returns.append(other_return)
                    
                    portfolio_without_sharpe = self._compute_sharpe_ratio(other_returns) if other_returns else 0.0
                    delta_sharpe = portfolio_sharpe - portfolio_without_sharpe
                else:
                    # Only one member
                    delta_sharpe = 0.0
            
            contributions[run_id] = delta_sharpe
            
            # Gate2 rules: ΔSharpe < 0 => REJECT, |ΔSharpe| < 0.05 => NO_SIGNAL, else PASS
            if delta_sharpe < 0:
                rejected_members.append(run_id)
            elif abs(delta_sharpe) < noise_buffer:
                insignificant.append(run_id)
            else:
                significant.append(run_id)
        
        # Gate2 status: REJECT if any member REJECTs
        gate2_status = "REJECT" if rejected_members else "PASS"
        
        # Compute diversification benefit (simplified)
        portfolio_vol = self._compute_volatility(portfolio_returns) if portfolio_returns else 0.0
        sum_individual_vols = sum(
            self._compute_volatility(daily_returns.get(run_id, []))
            for run_id in admitted_run_ids
        )
        
        if sum_individual_vols > 0:
            diversification_benefit = 1.0 - (portfolio_vol * len(admitted_run_ids) / sum_individual_vols)
            diversification_benefit = max(0.0, min(1.0, diversification_benefit))
        else:
            diversification_benefit = 0.0
        
        return {
            "contributions": contributions,
            "total_sharpe": portfolio_sharpe,
            "noise_buffer": noise_buffer,
            "significant_contributors": significant,
            "insignificant_contributors": insignificant,
            "diversification_benefit": diversification_benefit,
            "gate2_status": gate2_status,
            "rejected_members": rejected_members
        }
    
    def _compute_sharpe_ratio(self, returns: List[float], risk_free_rate: float = 0.02) -> float:
        """Compute annualized Sharpe ratio."""
        if not returns:
            return 0.0
        
        import statistics
        
        # Convert daily returns to annualized
        mean_return = statistics.mean(returns)
        std_return = statistics.stdev(returns) if len(returns) > 1 else 0.0
        
        if std_return == 0:
            return 0.0
        
        # Annualize (assuming 252 trading days)
        annualized_mean = mean_return * 252
        annualized_std = std_return * math.sqrt(252)
        
        sharpe = (annualized_mean - risk_free_rate) / annualized_std
        return sharpe
    
    def _compute_volatility(self, returns: List[float]) -> float:
        """Compute annualized volatility."""
        if not returns or len(returns) < 2:
            return 0.0
        
        import statistics
        std_return = statistics.stdev(returns)
        # Annualize (assuming 252 trading days)
        annualized_vol = std_return * math.sqrt(252)
        return annualized_vol
    
    def _compute_money_sense_mdd(
        self,
        max_drawdown_pct: float,
        portfolio_config: Dict[str, Any],
        research_results: Optional[Dict[str, ResearchWFSResult]] = None,
        admitted_run_ids: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Compute money-sense MDD amount display (Phase4-B.1)."""
        total_capital = portfolio_config.get("total_capital", 100000.0)
        currency = portfolio_config.get("currency", "USD")
        
        # Calculate notional baseline according to Phase 4-B spec:
        # 1) Σ lots * multiplier * contract_value (if exists)
        # 2) else initial portfolio OOS equity
        notional_baseline = total_capital  # Default to total capital
        
        if research_results and admitted_run_ids:
            # Try to compute using contract values if available
            total_notional = 0.0
            has_contract_info = False
            
            for run_id in admitted_run_ids:
                if run_id in research_results:
                    result = research_results[run_id]
                    # Get multiplier and contract value from instrument config
                    instrument = result.config.instrument
                    multiplier = 1.0
                    contract_value = 0.0
                    
                    # Safely extract values (handles MagicMock in tests)
                    try:
                        if hasattr(instrument, 'get'):
                            multiplier = instrument.get("multiplier", 1.0)
                            contract_value = instrument.get("contract_value", 0.0)
                        else:
                            # Might be a dict-like object
                            multiplier = instrument.get("multiplier", 1.0) if isinstance(instrument, dict) else 1.0
                            contract_value = instrument.get("contract_value", 0.0) if isinstance(instrument, dict) else 0.0
                    except (AttributeError, TypeError):
                        pass
                    
                    # Convert to float if possible
                    try:
                        multiplier = float(multiplier)
                    except (ValueError, TypeError):
                        multiplier = 1.0
                    
                    try:
                        contract_value = float(contract_value)
                    except (ValueError, TypeError):
                        contract_value = 0.0
                    
                    # If contract_value is not directly available, try to infer from symbol
                    if contract_value <= 0:
                        # Try to get from instrument symbol
                        symbol = ""
                        try:
                            if hasattr(instrument, 'get'):
                                symbol = instrument.get("symbol", "")
                            elif isinstance(instrument, dict):
                                symbol = instrument.get("symbol", "")
                        except (AttributeError, TypeError):
                            pass
                        
                        # Simple mapping for common futures
                        if symbol in ["MNQ", "MES", "MYM"]:
                            contract_value = 5.0  # Approximate $5 per point for micro futures
                        elif symbol in ["NQ", "ES", "YM"]:
                            contract_value = 50.0  # Approximate $50 per point for e-mini
                        else:
                            contract_value = 1.0  # Default
                    
                    # Assume 1 lot per strategy for now (simplified)
                    lots = 1
                    total_notional += lots * multiplier * contract_value
                    has_contract_info = True
            
            if has_contract_info and total_notional > 0:
                notional_baseline = total_notional
                baseline_type = "contract_value"
            else:
                # Fallback to initial portfolio OOS equity
                # Compute combined equity series
                combined_series = self._combine_equity_series(admitted_run_ids, research_results)
                if combined_series:
                    # Get initial equity value
                    sorted_series = sorted(combined_series, key=lambda x: x["t"])
                    initial_equity = sorted_series[0]["v"] if sorted_series else total_capital
                    notional_baseline = initial_equity
                baseline_type = "initial_equity"
        
        mdd_absolute = notional_baseline * (max_drawdown_pct / 100)
        capital_at_risk = mdd_absolute
        
        # Determine currency (if mixed, use "MIXED")
        currencies = set()
        if research_results and admitted_run_ids:
            for run_id in admitted_run_ids:
                if run_id in research_results:
                    result = research_results[run_id]
                    curr = result.config.instrument.get("currency", "USD")
                    currencies.add(curr)
        
        if len(currencies) > 1:
            currency = "MIXED"
        elif currencies:
            currency = list(currencies)[0]
        
        # Create human-readable string
        human_readable = f"{max_drawdown_pct:.1f}% ({currency} {mdd_absolute:,.0f} of {currency} {notional_baseline:,.0f})"
        
        return {
            "mdd_percentage": max_drawdown_pct,
            "mdd_absolute": mdd_absolute,
            "currency": currency,
            "capital_at_risk": capital_at_risk,
            "risk_adjusted_return": 0.0,  # Would need actual returns to compute
            "human_readable": human_readable,
            "notional_baseline": notional_baseline,
            "baseline_type": baseline_type
        }
    
    def _compute_enhanced_analytics(
        self,
        admitted_run_ids: List[str],
        research_results: Dict[str, ResearchWFSResult],
        portfolio_config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Compute all Phase4-B.1 enhanced analytics."""
        if not admitted_run_ids:
            # Return empty analytics if no admitted runs
            return {
                "budget_alerts": {
                    "rolling_3m": {"period": "3M", "mdd_pct": 0.0, "limit_pct": 12.0, "triggered": False, "start_date": "", "end_date": ""},
                    "rolling_6m": {"period": "6M", "mdd_pct": 0.0, "limit_pct": 18.0, "triggered": False, "start_date": "", "end_date": ""},
                    "rolling_full": {"period": "FULL", "mdd_pct": 0.0, "limit_pct": 25.0, "triggered": False, "start_date": "", "end_date": ""},
                    "any_triggered": False,
                    "worst_period": "NONE"
                },
                "marginal_contribution": {
                    "contributions": {},
                    "total_sharpe": 0.0,
                    "noise_buffer": 0.05,
                    "significant_contributors": [],
                    "insignificant_contributors": [],
                    "diversification_benefit": 0.0
                },
                "money_sense_mdd": {
                    "mdd_percentage": 0.0,
                    "mdd_absolute": 0.0,
                    "currency": portfolio_config.get("currency", "USD"),
                    "capital_at_risk": 0.0,
                    "risk_adjusted_return": 0.0,
                    "human_readable": "0.0% ($0 of $0)"
                }
            }
        
        # Compute combined equity series for admitted runs
        combined_equity = self._combine_equity_series(admitted_run_ids, research_results)
        
        # Compute budget alerts from rolling MDD
        budget_alerts = self._compute_budget_alerts(combined_equity, portfolio_config)
        
        # Compute marginal contribution analysis
        noise_buffer = portfolio_config.get("noise_buffer_sharpe", 0.05)
        marginal_contribution = self._compute_marginal_contribution(
            admitted_run_ids, research_results, noise_buffer
        )
        
        # Compute money-sense MDD with proper notional baseline
        max_drawdown_pct = budget_alerts["rolling_full"]["mdd_pct"]
        money_sense_mdd = self._compute_money_sense_mdd(
            max_drawdown_pct,
            portfolio_config,
            research_results=research_results,
            admitted_run_ids=admitted_run_ids
        )
        
        return {
            "budget_alerts": budget_alerts,
            "marginal_contribution": marginal_contribution,
            "money_sense_mdd": money_sense_mdd
        }
    
    def _combine_equity_series(
        self,
        run_ids: List[str],
        research_results: Dict[str, ResearchWFSResult]
    ) -> List[EquityPoint]:
        """Combine equity series from multiple runs (simple average)."""
        if not run_ids:
            return []
        
        # Get first series as base
        first_run_id = run_ids[0]
        first_series = research_results[first_run_id].series.stitched_oos_equity
        
        if len(run_ids) == 1:
            return first_series
        
        # Initialize combined series with timestamps from first series
        combined = []
        for point in first_series:
            combined.append({
                "t": point["t"],
                "v": point["v"]  # Will be averaged
            })
        
        # Create dicts for other series for fast lookup
        other_series_dicts = []
        for run_id in run_ids[1:]:
            series = research_results[run_id].series.stitched_oos_equity
            series_dict = {p["t"]: p["v"] for p in series}
            other_series_dicts.append(series_dict)
        
        # Sum values from all series
        for i, point in enumerate(combined):
            timestamp = point["t"]
            for series_dict in other_series_dicts:
                if timestamp in series_dict:
                    point["v"] += series_dict[timestamp]
        
        # Average the values
        num_runs = len(run_ids)
        for point in combined:
            point["v"] /= num_runs
        
        # Convert back to EquityPoint format
        return [EquityPoint(t=p["t"], v=p["v"]) for p in combined]
    
    def _write_artifacts(
        self,
        context: JobContext,
        portfolio_config: Dict[str, Any],
        admission_decision: AdmissionDecision,
        correlation_result: Dict[str, Any],
        research_results: Dict[str, ResearchWFSResult],
        enhanced_analytics: Optional[Dict[str, Any]] = None
    ) -> None:
        """Write portfolio admission artifacts with Phase4-B.1 enhancements."""
        artifacts_dir = Path(context.artifacts_dir)
        
        # Ensure we only write to canonical job artifacts directory (R1 requirement)
        # No writes to outputs/portfolios/ - only outputs/jobs/<job_id>/
        
        # 1. Write portfolio_config.json (v1.0)
        config_path = artifacts_dir / "portfolio_config.json"
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(portfolio_config, f, indent=2, ensure_ascii=False)
        
        # 2. Write admission_decision.json (legacy, kept for compatibility)
        decision_path = artifacts_dir / "admission_decision.json"
        with open(decision_path, "w", encoding="utf-8") as f:
            json.dump(admission_decision.model_dump(), f, indent=2, ensure_ascii=False)
        
        # 3. Write correlation_analysis.json (legacy, kept for compatibility)
        correlation_path = artifacts_dir / "correlation_analysis.json"
        with open(correlation_path, "w", encoding="utf-8") as f:
            json.dump(correlation_result, f, indent=2, ensure_ascii=False)
        
        # 4. Write enhanced analytics as separate files (optional, for debugging)
        # According to Phase 4-B spec, we may embed them inside admission_report.json
        # but we can also write them as separate files in the same job directory
        if enhanced_analytics:
            # Write budget_alerts.json (optional)
            budget_alerts_path = artifacts_dir / "budget_alerts.json"
            with open(budget_alerts_path, "w", encoding="utf-8") as f:
                json.dump(enhanced_analytics.get("budget_alerts", {}), f, indent=2, ensure_ascii=False)
            
            # Write marginal_contribution.json (optional)
            marginal_path = artifacts_dir / "marginal_contribution.json"
            with open(marginal_path, "w", encoding="utf-8") as f:
                json.dump(enhanced_analytics.get("marginal_contribution", {}), f, indent=2, ensure_ascii=False)
            
            # Write money_sense_mdd.json (optional)
            mdd_path = artifacts_dir / "money_sense_mdd.json"
            with open(mdd_path, "w", encoding="utf-8") as f:
                json.dump(enhanced_analytics.get("money_sense_mdd", {}), f, indent=2, ensure_ascii=False)
        
        # 5. Write comprehensive admission_report.json (v1.0 FINAL) - REQUIRED
        admission_report = self._build_admission_report(
            portfolio_config=portfolio_config,
            admission_decision=admission_decision,
            correlation_result=correlation_result,
            enhanced_analytics=enhanced_analytics
        )
        report_path = artifacts_dir / "admission_report.json"
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(admission_report, f, indent=2, ensure_ascii=False)
        
        # 6. Write summary.txt with enhanced information
        summary_path = artifacts_dir / "summary.txt"
        with open(summary_path, "w", encoding="utf-8") as f:
            f.write(f"Portfolio Admission Results (Phase4-B FINAL)\n")
            f.write(f"============================================\n")
            f.write(f"Portfolio ID: {portfolio_config['portfolio_id']}\n")
            f.write(f"Verdict: {admission_report.get('verdict', 'UNKNOWN')}\n")
            f.write(f"Admitted runs: {len(admission_decision.admitted_run_ids)}\n")
            f.write(f"Rejected runs: {len(admission_decision.rejected_run_ids)}\n")
            f.write(f"Correlation gate passed: {correlation_result['passed']}\n")
            f.write(f"Correlation violations: {correlation_result['violating_pairs']}\n")
            f.write(f"Correlation warnings: {correlation_result.get('warning_pairs', 0)}\n")
            
            # Gate statuses
            gates = admission_report.get('gates', {})
            f.write(f"\nGate Status:\n")
            f.write(f"  - Gate1 (Correlation): {gates.get('gate1', 'UNKNOWN')}\n")
            f.write(f"  - Gate2 (Marginal Contribution): {gates.get('gate2', 'UNKNOWN')}\n")
            f.write(f"  - Gate3 (Rolling MDD): {gates.get('gate3', 'UNKNOWN')}\n")
            
            if enhanced_analytics:
                budget_alerts = enhanced_analytics.get("budget_alerts", {})
                if budget_alerts.get("any_triggered", False):
                    f.write(f"\n[WARNING] BUDGET ALERTS TRIGGERED: \n")
                    for period in ["rolling_3m", "rolling_6m", "rolling_full"]:
                        alert = budget_alerts.get(period, {})
                        if alert.get("triggered", False):
                            f.write(f"  - {alert['period']}: {alert['mdd_pct']:.1f}% > {alert['limit_pct']:.1f}% limit\n")
                
                marginal = enhanced_analytics.get("marginal_contribution", {})
                if marginal.get("significant_contributors"):
                    f.write(f"\n📊 Significant contributors (|ΔSharpe| ≥ {marginal.get('noise_buffer', 0.05)}):\n")
                    for run_id in marginal["significant_contributors"]:
                        delta = marginal["contributions"].get(run_id, 0)
                        f.write(f"  - {run_id}: ΔSharpe = {delta:.3f}\n")
                
                if marginal.get("rejected_members"):
                    f.write(f"\n❌ Rejected by Gate2 (ΔSharpe < 0):\n")
                    for run_id in marginal["rejected_members"]:
                        f.write(f"  - {run_id}\n")
                
                mdd_info = enhanced_analytics.get("money_sense_mdd", {})
                if mdd_info.get("human_readable"):
                    f.write(f"\n💰 Money-sense MDD: {mdd_info['human_readable']}\n")
            
            f.write(f"\nAdmitted runs:\n")
            for run_id in admission_decision.admitted_run_ids:
                f.write(f"  - {run_id}\n")
            
            if admission_decision.reasons:
                f.write(f"\nRejection reasons:\n")
                for run_id, reason in admission_decision.reasons.items():
                    f.write(f"  - {run_id}: {reason}\n")
        
        logger.info(f"Wrote portfolio admission artifacts to {artifacts_dir}")
        logger.info(f"Canonical artifacts: portfolio_config.json (v1.0), admission_report.json (v1.0 FINAL)")
    
    def _build_admission_report(
        self,
        portfolio_config: Dict[str, Any],
        admission_decision: AdmissionDecision,
        correlation_result: Dict[str, Any],
        enhanced_analytics: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Build comprehensive admission report (Phase4-B.1 final schema)."""
        now = datetime.now(timezone.utc).isoformat()
        
        # Extract gate statuses from enhanced analytics
        gate1_status = "PASS" if correlation_result["passed"] else "REJECT"
        gate2_status = "PASS"
        gate3_status = "PASS"
        
        if enhanced_analytics:
            marginal = enhanced_analytics.get("marginal_contribution", {})
            gate2_status = marginal.get("gate2_status", "PASS")
            
            budget_alerts = enhanced_analytics.get("budget_alerts", {})
            if budget_alerts.get("any_triggered", False):
                gate3_status = "ALERT"
        
        # Determine overall verdict
        if gate1_status == "REJECT" or gate2_status == "REJECT":
            verdict = "REJECT"
        elif gate3_status == "ALERT":
            verdict = "ADMIT_WITH_CONSTRAINTS"
        else:
            verdict = "ADMIT"
        
        # Build correlation section
        correlation_matrix = {}
        # TODO: Build actual correlation matrix from correlation_result
        
        # Build portfolio series (simplified - would need actual series)
        portfolio_series = {
            "oos": [],  # Would need actual OOS equity series
            "bnh": [],  # Would need actual B&H equity series
            "underwater": []  # Would need actual underwater series
        }
        
        # Build risk metrics
        risk_metrics = {
            "full_mdd": 0.0,
            "rolling_3m": 0.0,
            "rolling_6m": 0.0,
            "ulcer": 0.0,
            "sync_dd_factor": 0.0
        }
        
        # Build performance metrics
        performance_metrics = {
            "sharpe": 0.0,
            "rf": 0.0,
            "cagr": 0.0
        }
        
        # Build marginal contribution with gate2 status
        marginal_section = {}
        if enhanced_analytics and "marginal_contribution" in enhanced_analytics:
            marginal = enhanced_analytics["marginal_contribution"]
            marginal_section = {
                "delta_sharpe": marginal.get("contributions", {}),
                "gate2_status": marginal.get("gate2_status", "PASS"),
                "rejected_members": marginal.get("rejected_members", [])
            }
        
        # Build money-sense section
        money_sense_section = {}
        if enhanced_analytics and "money_sense_mdd" in enhanced_analytics:
            mdd = enhanced_analytics["money_sense_mdd"]
            money_sense_section = {
                "currency": mdd.get("currency", "USD"),
                "notional": mdd.get("notional_baseline", 0.0),
                "mdd_amounts": {
                    "percentage": mdd.get("mdd_percentage", 0.0),
                    "absolute": mdd.get("mdd_absolute", 0.0)
                }
            }
        
        report = {
            "version": "1.0",
            "meta": {
                "portfolio_id": portfolio_config["portfolio_id"],
                "analyzed_at": now,
                "schema_version": "phase4-b.1-final"
            },
            "correlation": {
                "matrix": correlation_matrix,
                "thresholds": {
                    "warn": portfolio_config.get("correlation_threshold_warn", 0.70),
                    "reject": portfolio_config.get("correlation_threshold_reject", 0.85)
                },
                "flags": {
                    "gate1_status": gate1_status,
                    "violating_pairs": correlation_result.get("violating_pairs", 0),
                    "warning_pairs": correlation_result.get("warning_pairs", 0)
                }
            },
            "portfolio_series": portfolio_series,
            "risk": risk_metrics,
            "performance": performance_metrics,
            "marginal": marginal_section,
            "gates": {
                "gate1": gate1_status,
                "gate2": gate2_status,
                "gate3": gate3_status
            },
            "verdict": verdict,
            "money_sense": money_sense_section,
            "portfolio_config": portfolio_config,
            "admission_decision": admission_decision.model_dump(),
            "summary": {
                "total_runs": len(admission_decision.admitted_run_ids) + len(admission_decision.rejected_run_ids),
                "admitted_runs": len(admission_decision.admitted_run_ids),
                "rejected_runs": len(admission_decision.rejected_run_ids),
                "verdict": verdict,
                "correlation_gate_passed": correlation_result["passed"],
                "budget_alerts_triggered": enhanced_analytics.get("budget_alerts", {}).get("any_triggered", False) if enhanced_analytics else False
            }
        }
        
        return report


# Create handler instance
run_portfolio_admission_handler = RunPortfolioAdmissionHandler()
