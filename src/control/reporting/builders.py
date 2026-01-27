"""Report builders for Phase B reporting payload v1."""

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Optional, List
import logging
import math

from control.job_artifacts import get_job_evidence_dir

from core.reporting.models import (
    StrategyReportV1,
    StrategyHeadlineMetricsV1,
    TimePointV1,
    StrategySeriesV1,
    HistogramV1,
    StrategyDistributionsV1,
    TradeRowV1,
    StrategyTablesV1,
    StrategyLinksV1,
    PortfolioReportV1,
    PortfolioAdmissionSummaryV1,
    PortfolioCorrelationV1,
    PortfolioLinksV1,
)

logger = logging.getLogger(__name__)


def read_job_artifact(job_id: str, filename: str) -> Optional[Any]:
    """Read a job artifact JSON file."""
    job_dir = get_job_evidence_dir(job_id)
    artifact_path = job_dir / filename
    if not artifact_path.exists():
        return None
    try:
        with open(artifact_path, "r") as f:
            return json.load(f)
    except Exception as e:
        logger.warning(f"Failed to read artifact {filename} for job {job_id}: {e}")
        return None


def read_portfolio_admission_artifact(portfolio_id: str, filename: str) -> Optional[Any]:
    """Read a portfolio admission artifact JSON file."""
    admission_dir = Path("outputs/portfolios") / portfolio_id / "admission"
    artifact_path = admission_dir / filename
    if not artifact_path.exists():
        return None
    try:
        with open(artifact_path, "r") as f:
            return json.load(f)
    except Exception as e:
        logger.warning(f"Failed to read artifact {filename} for portfolio {portfolio_id}: {e}")
        return None


def _calculate_drawdown_series(equity_points: List[TimePointV1]) -> List[TimePointV1]:
    """Calculate drawdown series from equity points: (equity - peak) / peak."""
    if not equity_points:
        return []
    
    drawdown_points = []
    peak = -float('inf')
    
    for p in equity_points:
        if p.value > peak:
            peak = p.value
        
        dd = 0.0
        if peak > 0:
            dd = (p.value - peak) / peak
        
        drawdown_points.append(TimePointV1(
            timestamp=p.timestamp,
            value=float(dd)
        ))
    
    return drawdown_points


def _calculate_returns_histogram(equity_points: List[TimePointV1], bins: int = 21) -> Optional[HistogramV1]:
    """Calculate deterministic returns histogram from equity points."""
    if len(equity_points) < 2:
        return None
    
    returns = []
    for i in range(1, len(equity_points)):
        prev = equity_points[i-1].value
        curr = equity_points[i].value
        if prev != 0:
            returns.append((curr - prev) / prev)
    
    if not returns:
        return None
        
    # Fixed range for histogram: -5% to +5% per bar, or adaptive but deterministic
    # We'll use a simple fixed range for now to ensure stability
    r_min, r_max = -0.05, 0.05
    
    # Adaptive range if data exceeds fixed range
    actual_min = min(returns)
    actual_max = max(returns)
    if actual_min < r_min or actual_max > r_max:
        r_min = math.floor(actual_min * 20) / 20.0
        r_max = math.ceil(actual_max * 20) / 20.0

    step = (r_max - r_min) / bins
    edges = [r_min + i * step for i in range(bins + 1)]
    counts = [0] * bins
    
    for r in returns:
        if r < r_min:
            idx = 0
        elif r >= r_max:
            idx = bins - 1
        else:
            idx = int((r - r_min) / step)
            if idx >= bins:
                idx = bins - 1
        counts[idx] += 1
        
    return HistogramV1(bin_edges=edges, counts=counts)


def _calculate_sharpe_daily(equity_points: List[TimePointV1]) -> Optional[float]:
    """Calculate Sharpe ratio with daily frequency, risk-free = 0."""
    if len(equity_points) < 2:
        return None
    
    # Resample to daily
    daily_equity: Dict[str, float] = {}
    for p in equity_points:
        day_str = p.timestamp.date().isoformat()
        daily_equity[day_str] = p.value # Keep last value of the day
    
    days = sorted(daily_equity.keys())
    if len(days) < 2:
        return None
        
    returns = []
    for i in range(1, len(days)):
        prev = daily_equity[days[i-1]]
        curr = daily_equity[days[i]]
        if prev != 0:
            returns.append((curr - prev) / prev)
            
    if not returns:
        return 0.0
        
    import numpy as np
    mean_r = np.mean(returns)
    std_r = np.std(returns)
    
    if std_r == 0:
        return 0.0
        
    # Annualize (sqrt(252))
    return float(mean_r / std_r * math.sqrt(252))


def _calculate_profit_factor(trades: List[TradeRowV1]) -> Optional[float]:
    """Calculate Profit Factor: Sum(Gains) / Sum(Abs(Losses))."""
    gains = sum(t.pnl for t in trades if t.pnl is not None and t.pnl > 0)
    losses = sum(abs(t.pnl) for t in trades if t.pnl is not None and t.pnl < 0)
    
    if losses == 0:
        return 100.0 if gains > 0 else 0.0 # Cap pf at 100 if no losses
    return float(gains / losses)


def _calculate_calmar(equity_points: List[TimePointV1], max_drawdown: float) -> Optional[float]:
    """Calculate Calmar ratio: Annualized Return / Max Drawdown."""
    if not equity_points:
        return 0.0
        
    start_val = equity_points[0].value
    end_val = equity_points[-1].value
    
    if start_val == 0:
        return 0.0
        
    total_return = (end_val - start_val) / start_val
    
    duration_days = (equity_points[-1].timestamp - equity_points[0].timestamp).days
    if duration_days <= 0:
        return 0.0
        
    # Annualize return
    ann_return = (1 + total_return) ** (365.25 / duration_days) - 1
    
    # Use a floor for drawdown to avoid division by zero
    effective_dd = max(abs(max_drawdown), 1e-6)
    
    return float(ann_return / effective_dd)


def build_strategy_report_v1(job_id: str) -> StrategyReportV1:
    """
    Build a StrategyReportV1 from existing evidence artifacts.
    
    This reads existing evidence files and constructs the report model,
    filling with None for missing fields.
    """
    # Read available artifacts
    manifest = read_job_artifact(job_id, "manifest.json") or {}
    policy_check = read_job_artifact(job_id, "policy_check.json") or {}
    metrics = read_job_artifact(job_id, "metrics.json") or {}
    runtime_metrics = read_job_artifact(job_id, "runtime_metrics.json") or {}
    
    # Extract basic info
    strategy_name = manifest.get("strategy_id", "unknown")
    parameters = manifest.get("parameters", {})
    
    # Determine status from policy_check or manifest
    status = "UNKNOWN"
    if policy_check.get("result") == "REJECTED":
        status = "REJECTED"
    elif metrics.get("status"):
        status = metrics.get("status", "UNKNOWN")
    elif runtime_metrics.get("status"):
        status = runtime_metrics.get("status", "UNKNOWN")
    
    # Extract timestamps
    created_at = datetime.now()
    if "created_at" in manifest:
        try:
            created_at = datetime.fromisoformat(manifest["created_at"].replace("Z", "+00:00"))
        except Exception:
            pass
    
    finished_at = None
    if "finished_at" in manifest:
        try:
            finished_at = datetime.fromisoformat(manifest["finished_at"].replace("Z", "+00:00"))
        except Exception:
            pass
    
    # Try to load domain result
    wfs_result = read_job_artifact(job_id, "wfs_result.json") or {}
    
    # 1. Build tables and extract trade rows for Profit Factor
    trade_rows = []
    for win in wfs_result.get("windows", []):
        for t in win.get("oos_trades", []):
            try:
                row = TradeRowV1(
                    entry_time=datetime.fromisoformat(t["entry_t"].replace("Z", "+00:00")),
                    exit_time=datetime.fromisoformat(t["exit_t"].replace("Z", "+00:00")),
                    pnl=float(t["net_pnl"]),
                    mfe=float(t.get("mfe", 0.0)),
                    mae=float(t.get("mae", 0.0)),
                )
                trade_rows.append(row)
            except Exception:
                continue
    
    # 2. Build series (if equity/drawdown data exists)
    equity_points = []
    wfs_series = wfs_result.get("series", {})
    # Use stitched_oos_equity if available, else stitched_is_equity
    raw_points = wfs_series.get("stitched_oos_equity") or wfs_series.get("stitched_is_equity") or []
    for p in raw_points:
        try:
            # Use 't' and 'v' from ResearchWFSResult
            equity_points.append(TimePointV1(
                timestamp=datetime.fromisoformat(p["t"].replace("Z", "+00:00")),
                value=float(p["v"])
            ))
        except Exception:
            continue

    # 3. Headline Metrics Calculation
    raw = wfs_result.get("metrics", {}).get("raw", {}) or metrics.get("raw", {})
    verdict = wfs_result.get("verdict") or policy_check
    
    max_dd = raw.get("max_drawdown")
    if max_dd is None and equity_points:
        dd_series = _calculate_drawdown_series(equity_points)
        if dd_series:
            max_dd = min(p.value for p in dd_series)
            
    headline_metrics = StrategyHeadlineMetricsV1(
        score=wfs_result.get("metrics", {}).get("scores", {}).get("total_weighted"),
        net_profit=raw.get("net_profit"),
        max_drawdown=max_dd,
        trades=raw.get("trades"),
        win_rate=raw.get("win_rate"),
        profit_factor=_calculate_profit_factor(trade_rows) if trade_rows else raw.get("profit_factor"),
        sharpe=_calculate_sharpe_daily(equity_points) if equity_points else None,
        calmar=_calculate_calmar(equity_points, max_dd) if equity_points and max_dd is not None else None,
        downstream_admissible=verdict.get("is_tradable") or verdict.get("downstream_admissible"),
    )

    series = StrategySeriesV1(
        equity=equity_points if equity_points else None,
        drawdown=_calculate_drawdown_series(equity_points) if equity_points else None,
        rolling_metric=None,
        rolling_metric_name=None,
    )
    
    # 4. Build distributions
    distributions = StrategyDistributionsV1(
        returns_histogram=_calculate_returns_histogram(equity_points) if equity_points else None,
    )
    
    # 5. Build tables
    tables = StrategyTablesV1(
        trade_list=trade_rows if trade_rows else None,
        trade_summary=metrics.get("trade_summary"),
    )
    
    # 6. Build links
    links = StrategyLinksV1(
        policy_check_url=f"/api/v1/jobs/{job_id}/artifacts/policy_check.json" if policy_check else None,
        stdout_tail_url=f"/api/v1/jobs/{job_id}/logs/stdout_tail",
        evidence_bundle_url=f"/api/v1/jobs/{job_id}/reveal_evidence_path",
        artifacts_index_url=f"/api/v1/jobs/{job_id}/artifacts",
    )
    
    return StrategyReportV1(
        version="1.0",
        job_id=job_id,
        strategy_name=strategy_name,
        parameters=parameters,
        created_at=created_at,
        finished_at=finished_at,
        status=status,
        headline_metrics=headline_metrics,
        series=series,
        distributions=distributions,
        tables=tables,
        links=links,
    )


def build_portfolio_report_v1(portfolio_id: str) -> PortfolioReportV1:
    """
    Build a PortfolioReportV1 from existing evidence artifacts.
    
    This reads Phase E evidence JSONs and constructs the report model.
    """
    # Read available artifacts
    admission_decision = read_portfolio_admission_artifact(portfolio_id, "admission_decision.json") or {}
    correlation_matrix = read_portfolio_admission_artifact(portfolio_id, "correlation_matrix.json") or {}
    correlation_violations = read_portfolio_admission_artifact(portfolio_id, "correlation_violations.json")
    risk_budget_snapshot = read_portfolio_admission_artifact(portfolio_id, "risk_budget_snapshot.json")
    governance_params_snapshot = read_portfolio_admission_artifact(portfolio_id, "governance_params_snapshot.json")
    
    # Extract basic info
    created_at = datetime.now()
    if "created_at" in admission_decision:
        try:
            created_at = datetime.fromisoformat(admission_decision["created_at"].replace("Z", "+00:00"))
        except Exception:
            pass
    
    # Build admission summary
    admitted_count = len(admission_decision.get("admitted_strategies", []))
    rejected_count = len(admission_decision.get("rejected_strategies", []))
    
    admission_summary = PortfolioAdmissionSummaryV1(
        admitted_count=admitted_count,
        rejected_count=rejected_count,
    )
    
    # Build correlation
    labels = correlation_matrix.get("labels", [])
    matrix = correlation_matrix.get("matrix", [])
    
    correlation = PortfolioCorrelationV1(
        labels=labels,
        matrix=matrix,
        violations=correlation_violations,
    )
    
    # Build links
    links = PortfolioLinksV1(
        admission_decision_url=f"/api/v1/portfolios/{portfolio_id}/admission/decision" if admission_decision else None,
        correlation_matrix_url=f"/api/v1/portfolios/{portfolio_id}/admission/correlation_matrix" if correlation_matrix else None,
        correlation_violations_url=f"/api/v1/portfolios/{portfolio_id}/admission/correlation_violations" if correlation_violations else None,
        risk_budget_snapshot_url=f"/api/v1/portfolios/{portfolio_id}/admission/risk_budget_snapshot" if risk_budget_snapshot else None,
        evidence_bundle_url=f"/api/v1/portfolios/{portfolio_id}/admission",
    )
    
    return PortfolioReportV1(
        version="1.0",
        portfolio_id=portfolio_id,
        created_at=created_at,
        parameters=admission_decision.get("parameters"),
        admission_summary=admission_summary,
        correlation=correlation,
        risk_budget_steps=risk_budget_snapshot,
        admitted_strategies=admission_decision.get("admitted_strategies"),
        rejected_strategies=admission_decision.get("rejected_strategies"),
        governance_params_snapshot=governance_params_snapshot,
        links=links,
    )


def write_job_report(job_id: str, model: StrategyReportV1) -> None:
    """Write a strategy report to the job evidence directory."""
    job_dir = get_job_evidence_dir(job_id)
    job_dir.mkdir(parents=True, exist_ok=True)
    
    report_path = job_dir / "strategy_report_v1.json"
    with open(report_path, "w") as f:
        # Use model_dump with sorted keys for deterministic output
        json.dump(model.model_dump(mode="json", exclude_none=True), f, indent=2, sort_keys=True)
    
    logger.info(f"Written strategy report v1 to {report_path}")


def write_portfolio_report(portfolio_id: str, model: PortfolioReportV1) -> None:
    """Write a portfolio report to the portfolio admission directory."""
    admission_dir = Path("outputs/portfolios") / portfolio_id / "admission"
    admission_dir.mkdir(parents=True, exist_ok=True)
    
    report_path = admission_dir / "portfolio_report_v1.json"
    with open(report_path, "w") as f:
        # Use model_dump with sorted keys for deterministic output
        json.dump(model.model_dump(mode="json", exclude_none=True), f, indent=2, sort_keys=True)
    
    logger.info(f"Written portfolio report v1 to {report_path}")
