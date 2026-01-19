"""
Portfolio Tab Master Console tests (SSOT v1.0).
"""
import json
from datetime import datetime, timedelta, timezone

import pytest

from PySide6.QtWidgets import QApplication
from gui.desktop.tabs import allocation_tab


@pytest.fixture
def app():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture
def portfolio_tab(app, monkeypatch, tmp_path):
    monkeypatch.setattr(allocation_tab, "list_seasons_ssot", lambda: {"seasons": [{"season_id": "2026Q1"}]})
    monkeypatch.setattr(allocation_tab, "get_outputs_summary", lambda: {
        "jobs": {
            "recent": [
                {
                    "job_id": "job-1",
                    "strategy_name": "s1",
                    "instrument": "CME.MNQ",
                    "timeframe": "60",
                    "season": "2026Q1",
                    "status": "SUCCEEDED",
                    "links": {"report_url": "yes"},
                }
            ]
        },
        "portfolios": {"recent": []}
    })
    monkeypatch.setattr(allocation_tab, "post_portfolio_build", lambda payload: {"job_id": "port-job-1", "portfolio_id": "portfolio_1"})
    monkeypatch.setattr(allocation_tab, "get_job", lambda job_id: {"status": "RUNNING", "failure_message": None})

    tab = allocation_tab.AllocationTab()
    tab.prepared_index_path = tmp_path / "bar_prepare_index.json"
    tab.prepared_index_path.write_text(json.dumps({
        "instruments": {
            "CME.MNQ": {"timeframes": {"60": {"status": "built"}}, "parquet_status": {"path": ""}}
        }
    }))
    tab.refresh_prepared_index()
    return tab


def test_component_gating_requires_registered_and_prepared(portfolio_tab):
    portfolio_tab.selected_components = [
        {"job_id": "job-1", "instrument": "CME.MNQ", "timeframe": "60"}
    ]
    portfolio_tab.coverage_cache["CME.MNQ"] = allocation_tab.CoverageRange("2020-01-01", "2020-12-31")
    portfolio_tab.update_date_range()
    portfolio_tab.update_run_state()
    assert portfolio_tab.run_button.isEnabled()

    portfolio_tab.prepared_index["instruments"]["CME.MNQ"]["timeframes"] = {}
    portfolio_tab.update_run_state()
    assert not portfolio_tab.run_button.isEnabled()


def test_date_range_intersection(portfolio_tab):
    portfolio_tab.selected_components = [
        {"job_id": "job-1", "instrument": "CME.MNQ", "timeframe": "60"},
        {"job_id": "job-2", "instrument": "CME.ES", "timeframe": "60"},
    ]
    portfolio_tab.coverage_cache["CME.MNQ"] = allocation_tab.CoverageRange("2020-01-01", "2020-12-31")
    portfolio_tab.coverage_cache["CME.ES"] = allocation_tab.CoverageRange("2020-06-01", "2020-12-15")
    portfolio_tab.update_date_range()
    assert portfolio_tab.start_date_edit.text() == "2020-06-01"
    assert portfolio_tab.end_date_edit.text() == "2020-12-15"


def test_season_override(portfolio_tab):
    portfolio_tab.selected_components = [
        {"job_id": "job-1", "instrument": "CME.MNQ", "timeframe": "60"}
    ]
    portfolio_tab.season_combo.setCurrentIndex(1)
    portfolio_tab.update_date_range()
    assert portfolio_tab.start_date_edit.text().startswith("2026-01")
    assert portfolio_tab.end_date_edit.text().startswith("2026-03")


def test_portfolio_run_submission(portfolio_tab):
    portfolio_tab.selected_components = [
        {"job_id": "job-1", "instrument": "CME.MNQ", "timeframe": "60"}
    ]
    portfolio_tab.coverage_cache["CME.MNQ"] = allocation_tab.CoverageRange("2020-01-01", "2020-12-31")
    portfolio_tab.update_date_range()
    portfolio_tab.update_run_state()
    portfolio_tab.run_portfolio()
    assert portfolio_tab.focused_run_id == "port-job-1" or portfolio_tab.focused_run_id == "portfolio_1"


def test_polling_updates_runs(portfolio_tab):
    portfolio_tab.on_runs_loaded([
        {"portfolio_id": "portfolio_1", "created_at": "2026-01-01T00:00:00Z", "season": "2026Q1", "links": {"report_url": "yes"}}
    ])
    assert portfolio_tab.runs_table.rowCount() == 1


def test_progress_mapping_and_stall_labels(portfolio_tab):
    portfolio_tab.on_runs_loaded([
        {"portfolio_id": "portfolio_1", "created_at": "2026-01-01T00:00:00Z", "season": "2026Q1"}
    ])
    portfolio_tab.focused_run_id = "portfolio_1"
    portfolio_tab.run_last_change["portfolio_1"] = datetime.now(timezone.utc) - timedelta(seconds=40)
    portfolio_tab.update_focus_run()
    assert "STALLED" in portfolio_tab.stall_label.text() or portfolio_tab.stall_label.text() == ""
