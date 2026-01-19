from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
    QHeaderView,
    QMessageBox,
)

from gui.services.artifact_navigator_vm import (
    ArtifactNavigatorVM,
    Action,
    GATE_SUMMARY_TARGET,
    EXPLAIN_TARGET_PREFIX,
)
from gui.desktop.widgets.gate_summary_widget import GateSummaryWidget
from gui.services.action_router_service import get_action_router_service


class ArtifactNavigatorDialog(QDialog):
    """Dialog that surfaces gate, explain, and artifact navigation for a job."""

    open_gate_summary = Signal()
    open_explain = Signal(str)

    def __init__(self, job_id: str, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setProperty("job_id", job_id)
        self.setWindowTitle(f"Artifact Navigator — {job_id[:8] + '...' if len(job_id) > 8 else job_id}")
        self.vm = ArtifactNavigatorVM()
        self._setup_ui()
        self._load_data()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)

        header = QLabel(f"<b>Artifact Navigator</b> for {self._job_identifier()}")
        header.setAlignment(Qt.AlignmentFlag.AlignLeft)
        header.setFont(QFont("Arial", 11))
        layout.addWidget(header)

        self.gate_group = self._create_section("Gate Summary")
        layout.addWidget(self.gate_group)
        self.explain_group = self._create_section("Explain")
        layout.addWidget(self.explain_group)
        self.artifacts_group = self._create_artifacts_section()
        layout.addWidget(self.artifacts_group)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _create_section(self, title: str) -> QGroupBox:
        group = QGroupBox(title)
        group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                border: 1px solid #444;
                border-radius: 4px;
                padding: 8px;
                background-color: #121212;
                color: #E6E6E6;
            }
        """)
        layout = QVBoxLayout(group)
        layout.setSpacing(4)

        status = QLabel("Status: —")
        status.setObjectName(f"{title.lower().replace(' ', '_')}_status_label")
        status.setFont(QFont("Arial", 10, QFont.Weight.Bold))
        layout.addWidget(status)

        message = QLabel("")
        message.setWordWrap(True)
        layout.addWidget(message)

        action_btn = QPushButton("Open")
        action_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        action_btn.setEnabled(False)
        layout.addWidget(action_btn, alignment=Qt.AlignmentFlag.AlignRight)

        setattr(self, f"{title.lower().replace(' ', '_')}_status", status)
        setattr(self, f"{title.lower().replace(' ', '_')}_message", message)
        setattr(self, f"{title.lower().replace(' ', '_')}_action_btn", action_btn)

        return group

    def _create_artifacts_section(self) -> QGroupBox:
        group = QGroupBox("Artifacts")
        layout = QVBoxLayout(group)
        layout.setContentsMargins(8, 8, 8, 8)
        self.artifacts_table = QTableWidget()
        self.artifacts_table.setColumnCount(4)
        self.artifacts_table.setHorizontalHeaderLabels(["Name", "Status", "Path/URL", "Action"])
        self.artifacts_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.artifacts_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.artifacts_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.artifacts_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.artifacts_table.verticalHeader().setVisible(False)
        self.artifacts_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.artifacts_table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        layout.addWidget(self.artifacts_table)
        return group

    def _load_data(self) -> None:
        try:
            self.vm.load_for_job(self._job_identifier())
            self._refresh_gate_section()
            self._refresh_explain_section()
            self._refresh_artifacts_table()
        except Exception as exc:
            QMessageBox.critical(self, "Artifact Navigator", f"Failed to load data for {self._job_identifier()}: {exc}")

    def _refresh_gate_section(self) -> None:
        gate = self.vm.gate
        status_label: QLabel = getattr(self, "gate_summary_status", None)
        if status_label:
            status_text = gate.get("status", "UNKNOWN")
            status_label.setText(f"Status: {status_text}")
            status_label.setStyleSheet(self._status_style(status_text))
        message_label: QLabel = getattr(self, "gate_summary_message", None)
        if message_label:
            message_label.setText(gate.get("message", ""))
        action_btn: QPushButton = getattr(self, "gate_summary_action_btn", None)
        if action_btn:
            self._bind_action(action_btn, gate.get("actions", []))

    def _refresh_explain_section(self) -> None:
        explain = self.vm.explain
        status_label: QLabel = getattr(self, "explain_status", None)
        if status_label:
            status = explain.get("data_alignment_status", "UNKNOWN")
            status_label.setText(f"Alignment: {status}")
            status_label.setStyleSheet(self._status_style(status))
        message_label: QLabel = getattr(self, "explain_message", None)
        if message_label:
            message_label.setText(explain.get("message", ""))
        action_btn: QPushButton = getattr(self, "explain_action_btn", None)
        if action_btn:
            self._bind_action(action_btn, explain.get("actions", []))

    def _refresh_artifacts_table(self) -> None:
        rows = self.vm.artifacts
        self.artifacts_table.setRowCount(len(rows))
        for row_idx, entry in enumerate(rows):
            self.artifacts_table.setItem(row_idx, 0, QTableWidgetItem(entry.get("name")))
            status_item = QTableWidgetItem(entry.get("status"))
            status_item.setForeground(QColor("#FFFFFF"))
            status_item.setBackground(self._status_background(entry.get("status")))
            self.artifacts_table.setItem(row_idx, 1, status_item)
            self.artifacts_table.setItem(row_idx, 2, QTableWidgetItem(entry.get("url_or_path", "")))
            action_btn = QPushButton(entry.get("action").label)
            action_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            action_btn.clicked.connect(lambda _, act=entry.get("action"): self._handle_artifact_action(act))
            self.artifacts_table.setCellWidget(row_idx, 3, action_btn)

    def _bind_action(self, button: QPushButton, actions: list[Action]) -> None:
        if not actions:
            button.setEnabled(False)
            return
        button.setEnabled(True)
        action = actions[0]
        button.setText(action.label)
        try:
            button.clicked.disconnect()
        except Exception:
            pass
        button.clicked.connect(lambda: self._handle_action(action))

    def _handle_action(self, action: Action) -> None:
        if action.target == GATE_SUMMARY_TARGET:
            self.open_gate_summary.emit()
        elif action.target.startswith(EXPLAIN_TARGET_PREFIX):
            self.open_explain.emit(self._job_identifier())
        else:
            self._open_local_path(action.target)

    def _handle_artifact_action(self, action: Action) -> None:
        self._open_local_path(action.target)

    def _open_local_path(self, path: str) -> None:
        target = Path(path)
        if not target.exists():
            QMessageBox.information(self, "Path Missing", f"Expected artifact path:\n{path}")
        router = get_action_router_service()
        router.handle_action(f"file://{path}")

    def _job_identifier(self) -> str:
        return str(self.property("job_id") or "")

    @staticmethod
    def _status_style(value: str) -> str:
        color = "#4CAF50" if value == "PASS" or value == "OK" else "#FF9800" if value == "WARN" or value == "MISSING" else "#F44336"
        return f"color: {color};"

    @staticmethod
    def _status_background(value: str) -> QColor:
        if value == "PRESENT":
            return QColor("#2E7D32")
        if value == "MISSING":
            return QColor("#B71C1C")
        return QColor("#555555")


class GateSummaryDialog(QDialog):
    """Simple dialog that reuses GateSummaryWidget."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle("Gate Summary")
        layout = QVBoxLayout(self)
        self.widget = GateSummaryWidget()
        layout.addWidget(self.widget)
        self.resize(640, 320)
