"""Report builders for Phase B reporting payload v1."""

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Optional
import logging

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
    job_dir = Path("outputs/jobs") / job_id
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
    
    # Build headline metrics
    headline_metrics = StrategyHeadlineMetricsV1(
        score=metrics.get("score"),
        net_profit=metrics.get("net_profit"),
        max_drawdown=metrics.get("max_drawdown"),
        trades=metrics.get("trades"),
        win_rate=metrics.get("win_rate"),
        downstream_admissible=policy_check.get("downstream_admissible"),
    )
    
    # Build series (if equity/drawdown data exists)
    series = StrategySeriesV1(
        equity=None,  # TODO: parse equity series if available
        drawdown=None,  # TODO: parse drawdown series if available
        rolling_metric=None,
        rolling_metric_name=None,
    )
    
    # Build distributions
    distributions = StrategyDistributionsV1(
        returns_histogram=None,  # TODO: parse returns histogram if available
    )
    
    # Build tables
    trade_list = None
    trade_summary = metrics.get("trade_summary")
    
    tables = StrategyTablesV1(
        trade_list=trade_list,
        trade_summary=trade_summary,
    )
    
    # Build links
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
    job_dir = Path("outputs/jobs") / job_id
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