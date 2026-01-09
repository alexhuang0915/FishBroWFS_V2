"""
RUN_PORTFOLIO_ADMISSION handler for Phase4-B Portfolio Admission analysis.

Portfolio Admission pipeline:
- Consumes Phase4-A result.json files (multiple research runs)
- Performs OOS-only portfolio risk & admission analysis
- Does NOT re-run engine, re-optimize parameters, auto-optimize position sizing, or connect to live data
- Produces portfolio admission artifacts:
  - portfolio_config.json (strict schema)
  - admission_report.json (strict schema)
- Analytical components:
  - Correlation gates (pairwise correlation thresholds)
  - Portfolio stacking (risk-budget allocation)
  - Dynamic pain index (drawdown severity metric)
  - Marginal contribution analysis (risk attribution)
  - Money-sense UI metric (dual MDD representation: percentage + absolute currency)
"""

from __future__ import annotations

import json
import logging
import time
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Set
import traceback
import statistics
from pydantic import BaseModel, ConfigDict, Field

from ..job_handler import BaseJobHandler, JobContext
from src.contracts.research_wfs.result_schema import (
    ResearchWFSResult,
    validate_result_json,
    EquityPoint,
)
from src.contracts.portfolio.admission_schemas import (
    AdmissionDecision,
    AdmissionVerdict,
)

logger = logging.getLogger(__name__)


# -----------------------------------------------------------------------------
# Portfolio Admission Result Schemas (Step 2 from spec)
# -----------------------------------------------------------------------------

class PortfolioConfigSection(BaseModel):
    """Portfolio configuration (strict schema)."""
    portfolio_id: str
    name: str
    description: str
    currency: str
    target_volatility: float  # annualized
    max_drawdown_limit_pct: float  # percentage
    max_drawdown_limit_abs: float  # absolute currency
    correlation_threshold: float  # 0.0-1.0
    min_lots_per_strategy: int
    max_lots_per_strategy: int
    total_capital: float
    risk_budget_per_strategy: float
    created_at: str  # ISO8601
    updated_at: str  # ISO8601
    
    model_config = ConfigDict(frozen=True)


class CorrelationGateResult(BaseModel):
    """Correlation gate analysis result."""
    passed: bool
    violations: List[Dict[str, Any]]  # List of violation dicts
    threshold: float
    total_pairs: int
    violating_pairs: int
    
    model_config = ConfigDict(frozen=True)


class PortfolioStackingResult(BaseModel):
    """Portfolio stacking (risk-budget allocation) result."""
    allocated_run_ids: List[str]
    allocation_weights: Dict[str, float]  # run_id -> weight (0.0-1.0)
    risk_budget_used: float
    risk_budget_total: float
    lots_per_run: Dict[str, int]  # run_id -> integer lots
    
    model_config = ConfigDict(frozen=True)


class DynamicPainIndexResult(BaseModel):
    """Dynamic pain index (drawdown severity) result."""
    pain_index: float  # 0.0-1.0
    max_drawdown_pct: float
    max_drawdown_abs: float
    underwater_days: int
    recovery_time_days: int
    severity_score: float  # 0.0-100.0
    
    model_config = ConfigDict(frozen=True)


class MarginalContributionResult(BaseModel):
    """Marginal contribution analysis (risk attribution) result."""
    contributions: Dict[str, float]  # run_id -> contribution (0.0-1.0)
    total_risk: float
    diversification_benefit: float  # 0.0-1.0
    
    model_config = ConfigDict(frozen=True)


class MoneySenseMetric(BaseModel):
    """Money-sense UI metric (dual MDD representation)."""
    mdd_percentage: float
    mdd_absolute: float
    currency: str
    capital_at_risk: float
    risk_adjusted_return: float
    
    model_config = ConfigDict(frozen=True)


class AdmissionReportSection(BaseModel):
    """Complete admission report (strict schema)."""
    portfolio_id: str
    analyzed_at: str  # ISO8601
    input_run_ids: List[str]
    total_runs: int
    admitted_runs: int
    rejected_runs: int
    
    # Analytical results
    correlation_gate: CorrelationGateResult
    portfolio_stacking: PortfolioStackingResult
    dynamic_pain_index: DynamicPainIndexResult
    marginal_contribution: MarginalContributionResult
    money_sense_metric: MoneySenseMetric
    
    # Final decision
    verdict: str  # "ADMITTED", "REJECTED", "PARTIAL"
    admission_decision: Dict[str, Any]  # Serialized AdmissionDecision
    summary: str
    
    model_config = ConfigDict(frozen=True)


# -----------------------------------------------------------------------------
# Helper functions for analytical engine
# -----------------------------------------------------------------------------

def extract_oos_equity_series(result: ResearchWFSResult) -> List[EquityPoint]:
    """Extract OOS equity series from research result."""
    return result.series.stitched_oos_equity


def compute_correlation(series1: List[EquityPoint], series2: List[EquityPoint]) -> float:
    """
    Compute Pearson correlation between two equity series.
    
    Returns correlation coefficient (-1.0 to 1.0).
    For series with different timestamps, align by timestamp.
    """
    # Create dict mapping timestamp -> value for faster lookup
    series1_dict = {p["t"]: p["v"] for p in series1}
    series2_dict = {p["t"]: p["v"] for p in series2}
    
    # Find common timestamps
    common_timestamps = set(series1_dict.keys()) & set(series2_dict.keys())
    if len(common_timestamps) < 2:
        return 0.0  # Not enough data for correlation
    
    # Extract values for common timestamps
    values1 = [series1_dict[t] for t in sorted(common_timestamps)]
    values2 = [series2_dict[t] for t in sorted(common_timestamps)]
    
    # Compute Pearson correlation
    try:
        n = len(values1)
        mean1 = sum(values1) / n
        mean2 = sum(values2) / n
        
        numerator = sum((v1 - mean1) * (v2 - mean2) for v1, v2 in zip(values1, values2))
        denominator1 = sum((v1 - mean1) ** 2 for v1 in values1)
        denominator2 = sum((v2 - mean2) ** 2 for v2 in values2)
        
        if denominator1 == 0 or denominator2 == 0:
            return 0.0
            
        correlation = numerator / math.sqrt(denominator1 * denominator2)
        return max(-1.0, min(1.0, correlation))  # Clamp to [-1, 1]
    except Exception:
        return 0.0


def compute_drawdown_metrics(equity_series: List[EquityPoint]) -> Tuple[float, float, int]:
    """
    Compute drawdown metrics from equity series.
    
    Returns:
        max_drawdown_pct (float): Maximum drawdown as percentage
        max_drawdown_abs (float): Maximum drawdown in absolute terms
        underwater_days (int): Count of days with drawdown > 5%
    """
    if not equity_series:
        return 0.0, 0.0, 0
    
    # Extract equity values
    values = [p["v"] for p in equity_series]
    
    # Compute running maximum
    running_max = values[0]
    max_drawdown_abs = 0.0
    max_drawdown_pct = 0.0
    
    for value in values:
        if value > running_max:
            running_max = value
        
        drawdown_abs = running_max - value
        drawdown_pct = (drawdown_abs / running_max) * 100 if running_max != 0 else 0.0
        
        if drawdown_abs > max_drawdown_abs:
            max_drawdown_abs = drawdown_abs
            max_drawdown_pct = drawdown_pct
    
    # Simple underwater days calculation (simplified)
    underwater_days = sum(1 for v in values if v < 0.95 * max(values)) if values else 0
    
    return max_drawdown_pct, max_drawdown_abs, underwater_days


def compute_pain_index(equity_series: List[EquityPoint]) -> float:
    """
    Compute dynamic pain index (0.0-1.0).
    
    Pain index measures the severity of drawdowns.
    Higher values indicate more painful equity curve.
    """
    if not equity_series:
        return 0.0
    
    values = [p["v"] for p in equity_series]
    peak = values[0]
    pain_sum = 0.0
    
    for value in values:
        if value > peak:
            peak = value
        
        if peak > 0:
            drawdown = (peak - value) / peak
            pain_sum += drawdown
    
    return pain_sum / len(values) if len(values) > 0 else 0.0


# -----------------------------------------------------------------------------
# Main handler class
# -----------------------------------------------------------------------------

class RunPortfolioAdmissionHandler(BaseJobHandler):
    """RUN_PORTFOLIO_ADMISSION handler for executing portfolio admission analysis."""
    
    def validate_params(self, params: Dict[str, Any]) -> None:
        """Validate RUN_PORTFOLIO_ADMISSION parameters."""
        # Required parameters
        required = ["portfolio_id", "result_paths"]
        missing = [key for key in required if key not in params]
        if missing:
            raise ValueError(f"Missing required parameters: {missing}")
        
        # Validate result_paths is a list
        result_paths = params.get("result_paths", [])
        if not isinstance(result_paths, list):
            raise ValueError("result_paths must be a list of paths to Phase4-A result.json files")
        
        if len(result_paths) < 1:
            raise ValueError("At least one result.json file is required for portfolio admission")
        
        # Validate portfolio configuration if provided
        portfolio_config = params.get("portfolio_config", {})
        if portfolio_config:
            required_config = ["name", "currency", "target_volatility", "max_drawdown_limit_pct"]
            missing_config = [key for key in required_config if key not in portfolio_config]
            if missing_config:
                raise ValueError(f"Missing required portfolio_config fields: {missing_config}")
    
    def execute(self, params: Dict[str, Any], context: JobContext) -> Dict[str, Any]:
        """Execute RUN_PORTFOLIO_ADMISSION job."""
        # Check for abort before starting
        if context.is_abort_requested():
            return {
                "ok": False,
                "job_type": "RUN_PORTFOLIO_ADMISSION",
                "aborted": True,
                "reason": "user_abort_preinvoke",
                "payload": params
            }
        
        # Update heartbeat
        context.heartbeat(progress=0.1, phase="validating_inputs")
        
        try:
            # Parse parameters
            portfolio_id = params["portfolio_id"]
            result_paths = params["result_paths"]
            portfolio_config = params.get("portfolio_config", {})
            
            # Load and validate Phase4-A results
            context.heartbeat(progress=0.2, phase="loading_results")
            research_results = self._load_and_validate_results(result_paths)
            
            if not research_results:
                raise ValueError("No valid Phase4-A results found")
            
            # Build portfolio configuration
            context.heartbeat(progress=0.3, phase="building_config")
            portfolio_config_obj = self._build_portfolio_config(
                portfolio_id=portfolio_id,
                user_config=portfolio_config,
                research_results=research_results
            )
            
            # Run analytical engine
            context.heartbeat(progress=0.4, phase="running_analysis")
            admission_report = self._run_analytical_engine(
                portfolio_id=portfolio_id,
                research_results=research_results,
                portfolio_config=portfolio_config_obj
            )
            
            # Generate admission decision
            context.heartbeat(progress=0.8, phase="generating_decision")
            admission_decision = self._generate_admission_decision(
                portfolio_id=portfolio_id,
                admission_report=admission_report,
                research_results=research_results
            )
            
            # Write artifacts
            context.heartbeat(progress=0.9, phase="writing_artifacts")
            self._write_artifacts(
                context=context,
                portfolio_config=portfolio_config_obj,
                admission_report=admission_report,
                admission_decision=admission_decision
            )
            
            # Return success
            return {
                "ok": True,
                "job_type": "RUN_PORTFOLIO_ADMISSION",
                "payload": params,
                "result": {
                    "portfolio_id": portfolio_id,
                    "admitted_runs": len(admission_decision.admitted_run_ids),
                    "rejected_runs": len(admission_decision.rejected_run_ids),
                    "verdict": admission_decision.verdict.value,
                    "summary": admission_report.summary
                }
            }
            
        except Exception as e:
            logger.error(f"Failed to execute portfolio admission: {e}")
            logger.error(traceback.format_exc())
            
            # Write error to artifacts
            error_path = Path(context.artifacts_dir) / "error.txt"
            error_path.write_text(f"{e}\n\n{traceback.format_exc()}")
            
            raise  # Re-raise to mark job as FAILED
    
    def _load_and_validate_results(self, result_paths: List[str]) -> Dict[str, ResearchWFSResult]:
        """Load and validate Phase4-A result.json files."""
        results = {}
        
        for path_str in result_paths:
            path = Path(path_str)
            if not path.exists():
                logger.warning(f"Result file not found: {path}")
                continue
            
            try:
                # Load and validate JSON
                with open(path, "r", encoding="utf-8") as f:
                    json_str = f.read()
                
                result = validate_result_json(json_str)
                
                # Use job_id as key
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
    ) -> PortfolioConfigSection:
        """Build portfolio configuration from user config and research results."""
        now = datetime.now(timezone.utc).isoformat()
        
        # Extract common currency from results
        currencies = set()
        for result in research_results.values():
            currency = result.config.instrument.get("currency", "USD")
            currencies.add(currency)
        
        common_currency = "USD"
        if len(currencies) == 1:
            common_currency = list(currencies)[0]
        elif "USD" in currencies:
            common_currency = "USD"
        
        # Build config dict
        config_dict = {
            "portfolio_id": portfolio_id,
            "name": user_config.get("name", f"Portfolio {portfolio_id[:8]}"),
            "description": user_config.get("description", "Automatically generated portfolio"),
            "currency": common_currency,
            "target_volatility": float(user_config.get("target_volatility", 0.15)),  # 15% annualized
            "max_drawdown_limit_pct": float(user_config.get("max_drawdown_limit_pct", 20.0)),  # 20%
            "max_drawdown_limit_abs": float(user_config.get("max_drawdown_limit_abs", 10000.0)),  # $10,000
            "correlation_threshold": float(user_config.get("correlation_threshold", 0.7)),  # 0.7
            "min_lots_per_strategy": int(user_config.get("min_lots_per_strategy", 1)),
            "max_lots_per_strategy": int(user_config.get("max_lots_per_strategy", 10)),
            "total_capital": float(user_config.get("total_capital", 100000.0)),  # $100,000
            "risk_budget_per_strategy": float(user_config.get("risk_budget_per_strategy", 0.1)),  # 10%
            "created_at": now,
            "updated_at": now,
        }
        
        return PortfolioConfigSection(**config_dict)
    
    def _run_analytical_engine(
        self,
        portfolio_id: str,
        research_results: Dict[str, ResearchWFSResult],
        portfolio_config: PortfolioConfigSection
    ) -> AdmissionReportSection:
        """Run the analytical engine (correlation, stacking, pain index, marginal contribution)."""
        run_ids = list(research_results.keys())
        
        # 1. Correlation gate analysis
        correlation_result = self._run_correlation_analysis(
            research_results=research_results,
            threshold=portfolio_config.correlation_threshold
        )
        
        # 2. Portfolio stacking (risk-budget allocation)
        stacking_result = self._run_portfolio_stacking(
            research_results=research_results,
            portfolio_config=portfolio_config,
            correlation_violations=[v["run_id1"] for v in correlation_result.violations] if correlation_result.violations else []
        )
        
        # 3. Dynamic pain index
        pain_index_result = self._run_dynamic_pain_index_analysis(
            research_results=research_results,
            allocated_run_ids=stacking_result.allocated_run_ids
        )
        
        # 4. Marginal contribution analysis
        marginal_result = self._run_marginal_contribution_analysis(
            research_results=research_results,
            allocated_run_ids=stacking_result.allocated_run_ids
        )
        
        # 5. Money-sense UI metric
        money_sense_metric = self._compute_money_sense_metric(
            research_results=research_results,
            allocated_run_ids=stacking_result.allocated_run_ids,
            portfolio_config=portfolio_config
        )

        # Build admission report
        now = datetime.now(timezone.utc).isoformat()

        # Determine verdict
        verdict = "ADMITTED"
        if len(stacking_result.allocated_run_ids) == 0:
            verdict = "REJECTED"
        elif len(stacking_result.allocated_run_ids) < len(run_ids):
            verdict = "PARTIAL"

        # Create summary
        summary_parts = []
        if correlation_result.passed:
            summary_parts.append("Correlation gate passed")
        else:
            summary_parts.append(f"Correlation gate: {correlation_result.violating_pairs} violations")

        summary_parts.append(f"Allocated {len(stacking_result.allocated_run_ids)} of {len(run_ids)} runs")
        summary_parts.append(f"Pain index: {pain_index_result.pain_index:.3f}")
        summary_parts.append(f"Diversification benefit: {marginal_result.diversification_benefit:.1%}")

        summary = "; ".join(summary_parts)

        # Create placeholder admission decision (will be filled by _generate_admission_decision)
        placeholder_decision = {
            "verdict": "ADMITTED",
            "admitted_run_ids": stacking_result.allocated_run_ids,
            "rejected_run_ids": [rid for rid in run_ids if rid not in stacking_result.allocated_run_ids],
            "reasons": {},
            "portfolio_id": portfolio_id,
            "evaluated_at_utc": now
        }

        return AdmissionReportSection(
            portfolio_id=portfolio_id,
            analyzed_at=now,
            input_run_ids=run_ids,
            total_runs=len(run_ids),
            admitted_runs=len(stacking_result.allocated_run_ids),
            rejected_runs=len(run_ids) - len(stacking_result.allocated_run_ids),
            correlation_gate=correlation_result,
            portfolio_stacking=stacking_result,
            dynamic_pain_index=pain_index_result,
            marginal_contribution=marginal_result,
            money_sense_metric=money_sense_metric,
            verdict=verdict,
            admission_decision=placeholder_decision,
            summary=summary
        )

def _run_correlation_analysis(
    self,
    research_results: Dict[str, ResearchWFSResult],
    threshold: float
) -> CorrelationGateResult:
    """Run correlation gate analysis."""
    run_ids = list(research_results.keys())
    violations = []
    total_pairs = 0
    violating_pairs = 0
    
    # Compute pairwise correlations
    for i, run_id1 in enumerate(run_ids):
        for j, run_id2 in enumerate(run_ids):
            if i >= j:  # Skip self and duplicate pairs
                continue
            
            total_pairs += 1
            
            # Extract OOS equity series
            series1 = extract_oos_equity_series(research_results[run_id1])
            series2 = extract_oos_equity_series(research_results[run_id2])
            
            # Compute correlation
            correlation = compute_correlation(series1, series2)
            
            # Check if correlation exceeds threshold (absolute value)
            if abs(correlation) > threshold:
                violating_pairs += 1
                violations.append({
                    "run_id1": run_id1,
                    "run_id2": run_id2,
                    "correlation": correlation,
                    "threshold": threshold
                })
    
    passed = violating_pairs == 0
    
    return CorrelationGateResult(
        passed=passed,
        violations=violations,
        threshold=threshold,
        total_pairs=total_pairs,
        violating_pairs=violating_pairs
    )

def _run_portfolio_stacking(
    self,
    research_results: Dict[str, ResearchWFSResult],
    portfolio_config: PortfolioConfigSection,
    correlation_violations: List[str]
) -> PortfolioStackingResult:
    """Run portfolio stacking (risk-budget allocation)."""
    run_ids = list(research_results.keys())
    
    # Filter out runs with correlation violations
    # Simple heuristic: exclude runs involved in high correlations
    excluded_runs = set()
    for run_id in run_ids:
        if run_id in correlation_violations:
            excluded_runs.add(run_id)
    
    # Also exclude runs with poor performance (OOS net <= 0)
    for run_id, result in research_results.items():
        oos_metrics = result.windows[0].oos_metrics if result.windows else {}
        oos_net = oos_metrics.get("net", 0)
        if oos_net <= 0:
            excluded_runs.add(run_id)
    
    # Determine allocated runs
    allocated_run_ids = [rid for rid in run_ids if rid not in excluded_runs]
    
    # Simple equal-weight allocation
    allocation_weights = {}
    if allocated_run_ids:
        weight = 1.0 / len(allocated_run_ids)
        for run_id in allocated_run_ids:
            allocation_weights[run_id] = weight
    
    # Determine lots per run (simplified)
    lots_per_run = {}
    for run_id in allocated_run_ids:
        # Simple heuristic: 1 lot per strategy up to max
        lots = min(portfolio_config.max_lots_per_strategy, 
                  max(portfolio_config.min_lots_per_strategy, 1))
        lots_per_run[run_id] = lots
    
    # Calculate risk budget usage
    risk_budget_used = len(allocated_run_ids) * portfolio_config.risk_budget_per_strategy
    risk_budget_total = portfolio_config.total_capital * portfolio_config.target_volatility
    
    return PortfolioStackingResult(
        allocated_run_ids=allocated_run_ids,
        allocation_weights=allocation_weights,
        risk_budget_used=risk_budget_used,
        risk_budget_total=risk_budget_total,
        lots_per_run=lots_per_run
    )

def _run_dynamic_pain_index_analysis(
    self,
    research_results: Dict[str, ResearchWFSResult],
    allocated_run_ids: List[str]
) -> DynamicPainIndexResult:
    """Run dynamic pain index analysis."""
    if not allocated_run_ids:
        return DynamicPainIndexResult(
            pain_index=0.0,
            max_drawdown_pct=0.0,
            max_drawdown_abs=0.0,
            underwater_days=0,
            recovery_time_days=0,
            severity_score=0.0
        )
    
    # Combine equity series of allocated runs (simple average)
    combined_series = []
    first_run_id = allocated_run_ids[0]
    first_series = extract_oos_equity_series(research_results[first_run_id])
    
    # Initialize with timestamps from first series
    for point in first_series:
        combined_series.append({
            "t": point["t"],
            "v": point["v"]  # Will be averaged
        })
    
    # Average across all allocated runs
    for run_id in allocated_run_ids[1:]:
        series = extract_oos_equity_series(research_results[run_id])
        series_dict = {p["t"]: p["v"] for p in series}
        
        for i, point in enumerate(combined_series):
            timestamp = point["t"]
            if timestamp in series_dict:
                combined_series[i]["v"] += series_dict[timestamp]
    
    # Divide by number of runs to get average
    num_runs = len(allocated_run_ids)
    for point in combined_series:
        point["v"] /= num_runs
    
    # Convert to EquityPoint format
    equity_points = [EquityPoint(t=p["t"], v=p["v"]) for p in combined_series]
    
    # Compute metrics
    max_drawdown_pct, max_drawdown_abs, underwater_days = compute_drawdown_metrics(equity_points)
    pain_index = compute_pain_index(equity_points)
    
    # Simple severity score (0-100, lower is better)
    severity_score = min(100.0, pain_index * 100 + max_drawdown_pct)
    
    # Estimate recovery time (simplified)
    recovery_time_days = min(365, int(underwater_days * 1.5))
    
    return DynamicPainIndexResult(
        pain_index=pain_index,
        max_drawdown_pct=max_drawdown_pct,
        max_drawdown_abs=max_drawdown_abs,
        underwater_days=underwater_days,
        recovery_time_days=recovery_time_days,
        severity_score=severity_score
    )

def _run_marginal_contribution_analysis(
    self,
    research_results: Dict[str, ResearchWFSResult],
    allocated_run_ids: List[str]
) -> MarginalContributionResult:
    """Run marginal contribution analysis (risk attribution)."""
    if not allocated_run_ids:
        return MarginalContributionResult(
            contributions={},
            total_risk=0.0,
            diversification_benefit=0.0
        )
    
    # Simple risk contribution based on volatility
    contributions = {}
    volatilities = {}
    
    for run_id in allocated_run_ids:
        series = extract_oos_equity_series(research_results[run_id])
        values = [p["v"] for p in series]
        
        if len(values) < 2:
            volatility = 0.0
        else:
            # Compute standard deviation of returns
            returns = []
            for i in range(1, len(values)):
                if values[i-1] != 0:
                    ret = (values[i] - values[i-1]) / abs(values[i-1])
                    returns.append(ret)
            
            if returns:
                volatility = statistics.stdev(returns) if len(returns) > 1 else 0.0
            else:
                volatility = 0.0
        
        volatilities[run_id] = volatility
    
    # Total portfolio volatility (simplified as average)
    total_volatility = sum(volatilities.values()) / len(volatilities) if volatilities else 0.0
    
    # Contribution as proportion of total volatility
    for run_id, vol in volatilities.items():
        if total_volatility > 0:
            contribution = vol / total_volatility / len(volatilities)
        else:
            contribution = 1.0 / len(volatilities) if volatilities else 0.0
        contributions[run_id] = contribution
    
    # Diversification benefit (simplified)
    # 1 - (portfolio_vol / sum(individual_vols))
    sum_individual_vols = sum(volatilities.values())
    if sum_individual_vols > 0:
        diversification_benefit = 1.0 - (total_volatility * len(volatilities) / sum_individual_vols)
        diversification_benefit = max(0.0, min(1.0, diversification_benefit))
    else:
        diversification_benefit = 0.0
    
    return MarginalContributionResult(
        contributions=contributions,
        total_risk=total_volatility,
        diversification_benefit=diversification_benefit
    )

def _compute_money_sense_metric(
    self,
    research_results: Dict[str, ResearchWFSResult],
    allocated_run_ids: List[str],
    portfolio_config: PortfolioConfigSection
) -> MoneySenseMetric:
    """Compute money-sense UI metric (dual MDD representation)."""
    if not allocated_run_ids:
        return MoneySenseMetric(
            mdd_percentage=0.0,
            mdd_absolute=0.0,
            currency=portfolio_config.currency,
            capital_at_risk=0.0,
            risk_adjusted_return=0.0
        )
    
    # Get combined equity series
    combined_series = []
    first_run_id = allocated_run_ids[0]
    first_series = extract_oos_equity_series(research_results[first_run_id])
    
    for point in first_series:
        combined_series.append({
            "t": point["t"],
            "v": point["v"]
        })
    
    for run_id in allocated_run_ids[1:]:
        series = extract_oos_equity_series(research_results[run_id])
        series_dict = {p["t"]: p["v"] for p in series}
        
        for i, point in enumerate(combined_series):
            timestamp = point["t"]
            if timestamp in series_dict:
                combined_series[i]["v"] += series_dict[timestamp]
    
    num_runs = len(allocated_run_ids)
    for point in combined_series:
        point["v"] /= num_runs
    
    equity_points = [EquityPoint(t=p["t"], v=p["v"]) for p in combined_series]
    
    # Compute drawdown metrics
    max_drawdown_pct, max_drawdown_abs, _ = compute_drawdown_metrics(equity_points)
    
    # Capital at risk (simplified)
    capital_at_risk = portfolio_config.total_capital * (max_drawdown_pct / 100)
    
    # Risk-adjusted return (simplified Sharpe-like ratio)
    values = [p["v"] for p in equity_points]
    if len(values) > 1:
        total_return = (values[-1] - values[0]) / abs(values[0]) if values[0] != 0 else 0.0
        risk_adjusted_return = total_return / max_drawdown_pct if max_drawdown_pct > 0 else 0.0
    else:
        risk_adjusted_return = 0.0
    
    return MoneySenseMetric(
        mdd_percentage=max_drawdown_pct,
        mdd_absolute=max_drawdown_abs,
        currency=portfolio_config.currency,
        capital_at_risk=capital_at_risk,
        risk_adjusted_return=risk_adjusted_return
    )

def _generate_admission_decision(
    self,
    portfolio_id: str,
    admission_report: AdmissionReportSection,
    research_results: Dict[str, ResearchWFSResult]
) -> AdmissionDecision:
    """Generate formal admission decision."""
    now = datetime.now(timezone.utc).isoformat()
    
    # Determine verdict based on admission report
    if admission_report.verdict == "REJECTED":
        verdict = AdmissionVerdict.REJECTED
    else:
        verdict = AdmissionVerdict.ADMITTED
    
    # Build reasons for rejected runs
    reasons = {}
    allocated_set = set(admission_report.portfolio_stacking.allocated_run_ids)
    
    for run_id in research_results.keys():
        if run_id not in allocated_set:
            # Determine reason for rejection
            result = research_results[run_id]
            oos_metrics = result.windows[0].oos_metrics if result.windows else {}
            oos_net = oos_metrics.get("net", 0)
            
            if oos_net <= 0:
                reasons[run_id] = "OOS net profit <= 0"
            else:
                reasons[run_id] = "Excluded due to correlation violations or risk budget constraints"
    
    return AdmissionDecision(
        verdict=verdict,
        admitted_run_ids=admission_report.portfolio_stacking.allocated_run_ids,
        rejected_run_ids=[rid for rid in research_results.keys() 
                        if rid not in admission_report.portfolio_stacking.allocated_run_ids],
        reasons=reasons,
        portfolio_id=portfolio_id,
        evaluated_at_utc=now
    )

def _write_artifacts(
    self,
    context: JobContext,
    portfolio_config: PortfolioConfigSection,
    admission_report: AdmissionReportSection,
    admission_decision: AdmissionDecision
) -> None:
    """Write portfolio admission artifacts."""
    artifacts_dir = Path(context.artifacts_dir)
    
    # 1. Write portfolio_config.json
    config_path = artifacts_dir / "portfolio_config.json"
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(portfolio_config.model_dump(), f, indent=2, ensure_ascii=False)
    
    # 2. Write admission_report.json
    report_path = artifacts_dir / "admission_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(admission_report.model_dump(), f, indent=2, ensure_ascii=False)
    
    # 3. Write admission_decision.json (using the schema from contracts)
    decision_path = artifacts_dir / "admission_decision.json"
    with open(decision_path, "w", encoding="utf-8") as f:
        json.dump(admission_decision.model_dump(), f, indent=2, ensure_ascii=False)
    
    # 4. Write summary.txt
    summary_path = artifacts_dir / "summary.txt"
    with open(summary_path, "w", encoding="utf-8") as f:
        f.write(f"Portfolio Admission Results\n")
        f.write(f"==========================\n")
        f.write(f"Portfolio ID: {portfolio_config.portfolio_id}\n")
        f.write(f"Verdict: {admission_decision.verdict.value}\n")
        f.write(f"Admitted runs: {len(admission_decision.admitted_run_ids)}\n")
        f.write(f"Rejected runs: {len(admission_decision.rejected_run_ids)}\n")
        f.write(f"\nSummary: {admission_report.summary}\n")
    
    logger.info(f"Wrote portfolio admission artifacts to {artifacts_dir}")


# Create handler instance
run_portfolio_admission_handler = RunPortfolioAdmissionHandler()