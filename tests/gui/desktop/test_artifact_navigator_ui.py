import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication

from gui.desktop.tabs.op_tab_legacy import OpTab
from gui.services.gate_summary_service import GateSummary, GateStatus


@pytest.fixture
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_artifacts_affordance_opens_navigator(monkeypatch, qapp):
    job = {
        "job_id": "job-123",
        "strategy_name": "Test",
        "instrument": "MNQ",
        "timeframe": "5m",
        "run_mode": "backtest",
        "season": "2026Q1",
        "status": "SUCCEEDED",
        "created_at": "2026-01-17T00:00:00Z",
        "finished_at": "2026-01-17T00:05:00Z",
    }

    monkeypatch.setattr("gui.services.supervisor_client.get_registry_strategies", lambda: [])
    monkeypatch.setattr("gui.services.supervisor_client.get_registry_instruments", lambda: [])
    monkeypatch.setattr("gui.services.supervisor_client.get_registry_datasets", lambda: [])
    monkeypatch.setattr("gui.services.supervisor_client.get_jobs", lambda limit=50: [job])
    monkeypatch.setattr("gui.desktop.widgets.gate_summary_widget.fetch_gate_summary", lambda: GateSummary(
        gates=[],
        timestamp="2026-01-17T00:00:00Z",
        overall_status=GateStatus.PASS,
        overall_message="ok",
    ))

    captured = {}

    class DummySignal:
        def __init__(self):
            self._handlers = []

        def connect(self, handler):
            self._handlers.append(handler)

    class StubDialog:
        def __init__(self, job_id, parent=None):
            captured["job_id"] = job_id
            self.open_gate_summary = DummySignal()
            self.open_explain = DummySignal()

        def exec(self):
            captured["opened"] = True

    monkeypatch.setattr(
        "gui.desktop.tabs.op_tab_legacy.ArtifactNavigatorDialog",
        StubDialog,
    )

    tab = OpTab()
    tab.jobs_model.set_jobs([job])
    tab.handle_action_click(0, "artifacts")

    assert captured.get("job_id") == job["job_id"]
    assert captured.get("opened") is True
