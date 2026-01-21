"""Unit tests for reporting Pydantic models validation."""

import pytest
from datetime import datetime, timezone
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


def test_strategy_headline_metrics_v1_minimal():
    """StrategyHeadlineMetricsV1 can be constructed with all optional fields."""
    m = StrategyHeadlineMetricsV1()
    assert m.score is None
    assert m.net_profit is None
    assert m.max_drawdown is None
    assert m.trades is None
    assert m.win_rate is None
    assert m.downstream_admissible is None


def test_strategy_headline_metrics_v1_full():
    """StrategyHeadlineMetricsV1 with all fields."""
    m = StrategyHeadlineMetricsV1(
        score=0.85,
        net_profit=1234.56,
        max_drawdown=-0.12,
        trades=42,
        win_rate=0.65,
        downstream_admissible=True,
    )
    assert m.score == 0.85
    assert m.net_profit == 1234.56
    assert m.max_drawdown == -0.12
    assert m.trades == 42
    assert m.win_rate == 0.65
    assert m.downstream_admissible is True


def test_time_point_v1():
    """TimePointV1 requires timestamp and value."""
    tp = TimePointV1(
        timestamp=datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
        value=100.0,
    )
    assert tp.timestamp.year == 2025
    assert tp.value == 100.0


def test_strategy_series_v1():
    """StrategySeriesV1 can have optional series."""
    series = StrategySeriesV1(
        equity=[
            TimePointV1(timestamp=datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc), value=100.0),
            TimePointV1(timestamp=datetime(2025, 1, 1, 13, 0, 0, tzinfo=timezone.utc), value=105.0),
        ],
        drawdown=None,
        rolling_metric=None,
        rolling_metric_name="rolling_sharpe",
    )
    assert len(series.equity) == 2
    assert series.drawdown is None
    assert series.rolling_metric is None
    assert series.rolling_metric_name == "rolling_sharpe"


def test_histogram_v1():
    """HistogramV1 requires bin_edges and counts."""
    hist = HistogramV1(
        bin_edges=[0.0, 1.0, 2.0, 3.0],
        counts=[5, 10, 7],
    )
    assert hist.bin_edges == [0.0, 1.0, 2.0, 3.0]
    assert hist.counts == [5, 10, 7]


def test_strategy_distributions_v1():
    """StrategyDistributionsV1 can have optional histogram."""
    dist = StrategyDistributionsV1(
        returns_histogram=HistogramV1(
            bin_edges=[-0.1, 0.0, 0.1],
            counts=[3, 8],
        )
    )
    assert dist.returns_histogram is not None
    assert dist.returns_histogram.bin_edges == [-0.1, 0.0, 0.1]


def test_trade_row_v1():
    """TradeRowV1 fields are optional."""
    trade = TradeRowV1(
        entry_time=datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
        exit_time=datetime(2025, 1, 1, 13, 0, 0, tzinfo=timezone.utc),
        pnl=50.0,
        mfe=60.0,
        mae=-10.0,
    )
    assert trade.entry_time.year == 2025
    assert trade.exit_time.hour == 13
    assert trade.pnl == 50.0
    assert trade.mfe == 60.0
    assert trade.mae == -10.0


def test_strategy_tables_v1():
    """StrategyTablesV1 can have optional trade list and summary."""
    tables = StrategyTablesV1(
        trade_list=[
            TradeRowV1(entry_time=datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc), pnl=10.0),
        ],
        trade_summary={"total_trades": 1, "winning_trades": 1},
    )
    assert len(tables.trade_list) == 1
    assert tables.trade_summary["total_trades"] == 1


def test_strategy_links_v1():
    """StrategyLinksV1 fields are optional."""
    links = StrategyLinksV1(
        policy_check_url="/api/v1/jobs/job123/artifacts/policy_check.json",
        stdout_tail_url="/api/v1/jobs/job123/logs/stdout_tail",
        evidence_bundle_url="/api/v1/jobs/job123/artifacts",
        artifacts_index_url="/api/v1/jobs/job123/artifacts",
    )
    assert links.policy_check_url is not None
    assert links.stdout_tail_url is not None


def test_strategy_report_v1_minimal():
    """StrategyReportV1 minimal construction."""
    report = StrategyReportV1(
        version="1.0",
        job_id="job123",
        strategy_name="s1_v1",
        parameters={"param1": "value1"},
        created_at=datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
        finished_at=None,
        status="SUCCEEDED",
        headline_metrics=StrategyHeadlineMetricsV1(),
        series=StrategySeriesV1(),
        distributions=StrategyDistributionsV1(),
        tables=StrategyTablesV1(),
        links=StrategyLinksV1(),
    )
    assert report.version == "1.0"
    assert report.job_id == "job123"
    assert report.strategy_name == "s1_v1"
    assert report.status == "SUCCEEDED"
    assert report.headline_metrics is not None
    assert report.series is not None
    assert report.distributions is not None
    assert report.tables is not None
    assert report.links is not None


def test_strategy_report_v1_full():
    """StrategyReportV1 with all fields populated."""
    report = StrategyReportV1(
        version="1.0",
        job_id="job123",
        strategy_name="s1_v1",
        parameters={"param1": "value1"},
        created_at=datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
        finished_at=datetime(2025, 1, 1, 13, 0, 0, tzinfo=timezone.utc),
        status="SUCCEEDED",
        headline_metrics=StrategyHeadlineMetricsV1(
            score=0.85,
            net_profit=1234.56,
            max_drawdown=-0.12,
            trades=42,
            win_rate=0.65,
            downstream_admissible=True,
        ),
        series=StrategySeriesV1(
            equity=[
                TimePointV1(timestamp=datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc), value=100.0),
            ],
            drawdown=None,
            rolling_metric=None,
            rolling_metric_name="rolling_sharpe",
        ),
        distributions=StrategyDistributionsV1(
            returns_histogram=HistogramV1(
                bin_edges=[-0.1, 0.0, 0.1],
                counts=[3, 8],
            )
        ),
        tables=StrategyTablesV1(
            trade_list=[
                TradeRowV1(entry_time=datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc), pnl=10.0),
            ],
            trade_summary={"total_trades": 1},
        ),
        links=StrategyLinksV1(
            policy_check_url="/api/v1/jobs/job123/artifacts/policy_check.json",
            stdout_tail_url="/api/v1/jobs/job123/logs/stdout_tail",
            evidence_bundle_url="/api/v1/jobs/job123/artifacts",
            artifacts_index_url="/api/v1/jobs/job123/artifacts",
        ),
    )
    assert report.finished_at is not None
    assert report.headline_metrics.score == 0.85
    assert len(report.series.equity) == 1
    assert report.distributions.returns_histogram is not None
    assert len(report.tables.trade_list) == 1


def test_portfolio_admission_summary_v1():
    """PortfolioAdmissionSummaryV1 requires admitted_count and rejected_count."""
    summary = PortfolioAdmissionSummaryV1(
        admitted_count=5,
        rejected_count=2,
    )
    assert summary.admitted_count == 5
    assert summary.rejected_count == 2


def test_portfolio_correlation_v1():
    """PortfolioCorrelationV1 requires labels and matrix."""
    corr = PortfolioCorrelationV1(
        labels=["strategy_a", "strategy_b", "strategy_c"],
        matrix=[
            [1.0, 0.2, 0.1],
            [0.2, 1.0, 0.3],
            [0.1, 0.3, 1.0],
        ],
        violations=None,
    )
    assert len(corr.labels) == 3
    assert len(corr.matrix) == 3
    assert corr.matrix[0][0] == 1.0
    assert corr.violations is None


def test_portfolio_links_v1():
    """PortfolioLinksV1 fields are optional."""
    links = PortfolioLinksV1(
        admission_decision_url="/api/v1/portfolios/port123/admission/decision.json",
        correlation_matrix_url="/api/v1/portfolios/port123/admission/correlation_matrix.json",
        correlation_violations_url="/api/v1/portfolios/port123/admission/correlation_violations.json",
        risk_budget_snapshot_url="/api/v1/portfolios/port123/admission/risk_budget_snapshot.json",
        evidence_bundle_url="/api/v1/portfolios/port123/admission",
    )
    assert links.admission_decision_url is not None
    assert links.correlation_matrix_url is not None


def test_portfolio_report_v1_minimal():
    """PortfolioReportV1 minimal construction."""
    report = PortfolioReportV1(
        version="1.0",
        portfolio_id="port123",
        created_at=datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
        parameters=None,
        admission_summary=PortfolioAdmissionSummaryV1(admitted_count=0, rejected_count=0),
        correlation=PortfolioCorrelationV1(labels=[], matrix=[]),
        risk_budget_steps=None,
        admitted_strategies=None,
        rejected_strategies=None,
        governance_params_snapshot=None,
        links=PortfolioLinksV1(),
    )
    assert report.version == "1.0"
    assert report.portfolio_id == "port123"
    assert report.admission_summary.admitted_count == 0
    assert report.correlation.labels == []
    assert report.correlation.matrix == []


def test_portfolio_report_v1_full():
    """PortfolioReportV1 with all fields populated."""
    report = PortfolioReportV1(
        version="1.0",
        portfolio_id="port123",
        created_at=datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
        parameters={"max_correlation": 0.5, "risk_budget": 0.1},
        admission_summary=PortfolioAdmissionSummaryV1(admitted_count=5, rejected_count=2),
        correlation=PortfolioCorrelationV1(
            labels=["strategy_a", "strategy_b", "strategy_c"],
            matrix=[
                [1.0, 0.2, 0.1],
                [0.2, 1.0, 0.3],
                [0.1, 0.3, 1.0],
            ],
            violations=[{"pair": ["a", "b"], "value": 0.6, "threshold": 0.5}],
        ),
        risk_budget_steps=[
            {"step": 1, "budget": 0.1},
            {"step": 2, "budget": 0.2},
        ],
        admitted_strategies=[
            {"strategy_id": "s1_v1", "weight": 0.3},
            {"strategy_id": "s2_v1", "weight": 0.7},
        ],
        rejected_strategies=[
            {"strategy_id": "s3_v1", "reason": "correlation violation"},
        ],
        governance_params_snapshot={"max_correlation": 0.5, "min_score": 0.0},
        links=PortfolioLinksV1(
            admission_decision_url="/api/v1/portfolios/port123/admission/decision.json",
            correlation_matrix_url="/api/v1/portfolios/port123/admission/correlation_matrix.json",
            correlation_violations_url="/api/v1/portfolios/port123/admission/correlation_violations.json",
            risk_budget_snapshot_url="/api/v1/portfolios/port123/admission/risk_budget_snapshot.json",
            evidence_bundle_url="/api/v1/portfolios/port123/admission",
        ),
    )
    assert report.parameters["max_correlation"] == 0.5
    assert report.admission_summary.admitted_count == 5
    assert len(report.correlation.labels) == 3
    assert len(report.risk_budget_steps) == 2
    assert len(report.admitted_strategies) == 2
    assert len(report.rejected_strategies) == 1
    assert report.governance_params_snapshot is not None
    assert report.links.admission_decision_url is not None


def test_strategy_report_v1_version_literal():
    """StrategyReportV1 version must be "1.0"."""
    # Valid version
    report = StrategyReportV1(
        version="1.0",
        job_id="job123",
        strategy_name="s1_v1",
        parameters={},
        created_at=datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
        finished_at=None,
        status="SUCCEEDED",
        headline_metrics=StrategyHeadlineMetricsV1(),
        series=StrategySeriesV1(),
        distributions=StrategyDistributionsV1(),
        tables=StrategyTablesV1(),
        links=StrategyLinksV1(),
    )
    assert report.version == "1.0"
    
    # Invalid version should raise validation error
    with pytest.raises(ValueError):
        StrategyReportV1(
            version="2.0",  # wrong version
            job_id="job123",
            strategy_name="s1_v1",
            parameters={},
            created_at=datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
            finished_at=None,
            status="SUCCEEDED",
            headline_metrics=StrategyHeadlineMetricsV1(),
            series=StrategySeriesV1(),
            distributions=StrategyDistributionsV1(),
            tables=StrategyTablesV1(),
            links=StrategyLinksV1(),
        )


def test_portfolio_report_v1_version_literal():
    """PortfolioReportV1 version must be "1.0"."""
    # Valid version
    report = PortfolioReportV1(
        version="1.0",
        portfolio_id="port123",
        created_at=datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
        parameters=None,
        admission_summary=PortfolioAdmissionSummaryV1(admitted_count=0, rejected_count=0),
        correlation=PortfolioCorrelationV1(labels=[], matrix=[]),
        risk_budget_steps=None,
        admitted_strategies=None,
        rejected_strategies=None,
        governance_params_snapshot=None,
        links=PortfolioLinksV1(),
    )
    assert report.version == "1.0"
    
    # Invalid version should raise validation error
    with pytest.raises(ValueError):
        PortfolioReportV1(
            version="2.0",  # wrong version
            portfolio_id="port123",
            created_at=datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
            parameters=None,
            admission_summary=PortfolioAdmissionSummaryV1(admitted_count=0, rejected_count=0),
            correlation=PortfolioCorrelationV1(labels=[], matrix=[]),
            risk_budget_steps=None,
            admitted_strategies=None,
            rejected_strategies=None,
            governance_params_snapshot=None,
            links=PortfolioLinksV1(),
        )
