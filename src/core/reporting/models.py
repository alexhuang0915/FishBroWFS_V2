"""Pydantic models for Phase B reporting payload v1."""

from datetime import datetime
from typing import Any, Optional, Literal, List
from pydantic import BaseModel, Field


class TimePointV1(BaseModel):
    """A timestamp-value pair for time series data."""
    timestamp: datetime
    value: float


class HistogramV1(BaseModel):
    """Histogram representation with bin edges and counts."""
    bin_edges: List[float]
    counts: List[int]


class StrategyHeadlineMetricsV1(BaseModel):
    """Headline metrics for a strategy run."""
    score: Optional[float] = None
    net_profit: Optional[float] = None
    max_drawdown: Optional[float] = None
    trades: Optional[int] = None
    win_rate: Optional[float] = None
    downstream_admissible: Optional[bool] = None


class StrategySeriesV1(BaseModel):
    """Time series data for a strategy."""
    equity: Optional[List[TimePointV1]] = None
    drawdown: Optional[List[TimePointV1]] = None
    rolling_metric: Optional[List[TimePointV1]] = None
    rolling_metric_name: Optional[str] = None  # e.g., "rolling_sharpe"


class TradeRowV1(BaseModel):
    """Minimal trade row representation."""
    entry_time: Optional[datetime] = None
    exit_time: Optional[datetime] = None
    pnl: Optional[float] = None
    mfe: Optional[float] = None  # maximum favorable excursion
    mae: Optional[float] = None  # maximum adverse excursion


class StrategyTablesV1(BaseModel):
    """Tabular data for a strategy."""
    trade_list: Optional[List[TradeRowV1]] = None
    trade_summary: Optional[dict[str, Any]] = None  # allow existing summary dict


class StrategyDistributionsV1(BaseModel):
    """Distribution data for a strategy."""
    returns_histogram: Optional[HistogramV1] = None


class StrategyLinksV1(BaseModel):
    """Links to related resources for a strategy."""
    policy_check_url: Optional[str] = None
    stdout_tail_url: Optional[str] = None
    evidence_bundle_url: Optional[str] = None
    artifacts_index_url: Optional[str] = None


class StrategyReportV1(BaseModel):
    """Strategy report v1 payload."""
    version: Literal["1.0"] = "1.0"
    job_id: str
    strategy_name: str
    parameters: dict[str, Any]
    created_at: datetime
    finished_at: Optional[datetime] = None
    status: str  # SUCCEEDED/FAILED/REJECTED/RUNNING etc as string
    headline_metrics: StrategyHeadlineMetricsV1
    series: StrategySeriesV1
    distributions: StrategyDistributionsV1
    tables: StrategyTablesV1
    links: StrategyLinksV1


class PortfolioAdmissionSummaryV1(BaseModel):
    """Summary of portfolio admission decisions."""
    admitted_count: int
    rejected_count: int


class PortfolioCorrelationV1(BaseModel):
    """Correlation matrix and violations."""
    labels: List[str]
    matrix: List[List[float]]
    violations: Optional[List[dict[str, Any]]] = None


class PortfolioLinksV1(BaseModel):
    """Links to related resources for a portfolio."""
    admission_decision_url: Optional[str] = None
    correlation_matrix_url: Optional[str] = None
    correlation_violations_url: Optional[str] = None
    risk_budget_snapshot_url: Optional[str] = None
    evidence_bundle_url: Optional[str] = None


class PortfolioReportV1(BaseModel):
    """Portfolio report v1 payload."""
    version: Literal["1.0"] = "1.0"
    portfolio_id: str
    created_at: datetime
    parameters: Optional[dict[str, Any]] = None
    admission_summary: PortfolioAdmissionSummaryV1
    correlation: PortfolioCorrelationV1
    risk_budget_steps: Optional[List[dict[str, Any]]] = None
    admitted_strategies: Optional[List[dict[str, Any]]] = None
    rejected_strategies: Optional[List[dict[str, Any]]] = None
    governance_params_snapshot: Optional[dict[str, Any]] = None
    links: PortfolioLinksV1