"""
Pytest configuration and fixtures for GUI desktop tests.
Patches supervisor client to avoid network calls.
"""
import sys
from unittest.mock import Mock, patch
import pytest


@pytest.fixture(scope="function", autouse=True)
def mock_supervisor_client():
    """Mock supervisor client functions to avoid network calls.
    
    Patches the imported functions in src.gui.desktop.tabs.op_tab where they are used,
    and also patches supervisor_client functions used by other services.
    """
    with patch("src.gui.desktop.tabs.op_tab.get_registry_strategies") as mock_strategies, \
         patch("src.gui.desktop.tabs.op_tab.get_registry_instruments") as mock_instruments, \
         patch("src.gui.desktop.tabs.op_tab.get_registry_datasets") as mock_datasets, \
         patch("src.gui.desktop.tabs.op_tab.get_jobs") as mock_jobs, \
         patch("src.gui.desktop.tabs.op_tab.get_reveal_evidence_path") as mock_reveal, \
         patch("src.gui.desktop.tabs.op_tab.get_strategy_report_v1") as mock_report, \
         patch("src.gui.desktop.tabs.op_tab.submit_job") as mock_submit, \
         patch("src.gui.desktop.tabs.op_tab.get_artifacts") as mock_artifacts, \
         patch("src.gui.desktop.tabs.op_tab.get_stdout_tail") as mock_stdout_tail, \
         patch("src.gui.services.supervisor_client.check_readiness") as mock_check_readiness:
        
        # Mock strategies: list of dicts with id and name
        mock_strategies.return_value = [
            {"id": "s1", "name": "Strategy S1"},
            {"id": "s2", "name": "Strategy S2"},
            {"id": "s3", "name": "Strategy S3"},
        ]
        # Mock instruments: list of strings
        mock_instruments.return_value = ["MNQ", "MXF", "ES", "NQ"]
        # Mock datasets: list of strings
        mock_datasets.return_value = ["VX.FUT", "DX.FUT", "ZN.FUT", "6J.FUT"]
        # Mock jobs: empty list
        mock_jobs.return_value = []
        # Mock reveal evidence path: dict with path
        mock_reveal.return_value = {"path": "/tmp/evidence"}
        # Mock strategy report: dict with dummy report
        mock_report.return_value = {"report": "dummy"}
        # Mock submit job: returns job_id
        mock_submit.return_value = {"job_id": "test_job_123"}
        # Mock artifacts: empty dict
        mock_artifacts.return_value = {}
        # Mock stdout tail: empty string
        mock_stdout_tail.return_value = ""
        # Mock check_readiness: returns both bars and features ready
        mock_check_readiness.return_value = {
            "bars_ready": True,
            "features_ready": True,
            "bars_path": "/tmp/bars.parquet",
            "features_path": "/tmp/features.npz",
        }
        
        yield {
            "strategies": mock_strategies,
            "instruments": mock_instruments,
            "datasets": mock_datasets,
            "jobs": mock_jobs,
            "reveal": mock_reveal,
            "report": mock_report,
            "submit": mock_submit,
            "artifacts": mock_artifacts,
            "stdout_tail": mock_stdout_tail,
            "check_readiness": mock_check_readiness,
        }


@pytest.fixture(scope="session")
def qapp():
    """Provide a QApplication instance for Qt tests (session-scoped)."""
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app