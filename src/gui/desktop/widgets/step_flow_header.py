"""
Step Flow Header - persistent step navigation for ControlStation.
"""

from typing import Dict, List, Tuple

from PySide6.QtCore import Qt, Signal  # type: ignore
from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel, QPushButton, QFrame  # type: ignore

from gui.desktop.state.step_flow_state import StepId, STEP_LABELS


class StepFlowHeader(QWidget):
    """Persistent step header with gated navigation and tool buttons."""

    step_clicked = Signal(int)
    tool_clicked = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.step_buttons: Dict[StepId, QPushButton] = {}
        self.tool_buttons: List[QPushButton] = []
        self._build_ui()

    def _build_ui(self) -> None:
        self.setStyleSheet("background-color: #151515;")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 6, 12, 6)
        layout.setSpacing(8)

        step_bar = QFrame()
        step_bar.setStyleSheet("background-color: #1E1E1E; border-radius: 6px;")
        step_layout = QHBoxLayout(step_bar)
        step_layout.setContentsMargins(8, 6, 8, 6)
        step_layout.setSpacing(6)

        for step_id in StepId:
            label = STEP_LABELS.get(step_id, f"Step {int(step_id)}")
            btn = QPushButton(f"{int(step_id)} {label}")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setCheckable(False)
            btn.clicked.connect(lambda _checked=False, sid=step_id: self.step_clicked.emit(int(sid)))
            btn.setStyleSheet(self._step_style(enabled=True, active=False))
            self.step_buttons[step_id] = btn
            step_layout.addWidget(btn)

            if step_id != StepId.EXPORT:
                arrow = QLabel("→")
                arrow.setStyleSheet("color: #6A6A6A; font-size: 11px;")
                step_layout.addWidget(arrow)

        layout.addWidget(step_bar)
        layout.addStretch()

        self.tools_label = QLabel("Tools:")
        self.tools_label.setStyleSheet("color: #9A9A9A; font-size: 11px;")
        layout.addWidget(self.tools_label)

    def set_step_state(self, current_step: StepId, max_enabled_step: StepId) -> None:
        """Update step highlighting and gating."""
        for step_id, button in self.step_buttons.items():
            if step_id == current_step:
                button.setEnabled(True)
                button.setStyleSheet(self._step_style(enabled=True, active=True))
            elif step_id.value <= max_enabled_step.value:
                button.setEnabled(True)
                button.setStyleSheet(self._step_style(enabled=True, active=False))
            else:
                button.setEnabled(False)
                button.setStyleSheet(self._step_style(enabled=False, active=False))

    def set_tools(self, tools: List[Tuple[str, str]]) -> None:
        """Replace tool buttons with provided (label, tool_id) list."""
        for btn in self.tool_buttons:
            if self.layout():
                self.layout().removeWidget(btn)
            btn.deleteLater()
        self.tool_buttons.clear()

        for label, tool_id in tools:
            btn = QPushButton(label)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet("""
                QPushButton {
                    background-color: #2A2A2A;
                    color: #E6E6E6;
                    border: 1px solid #444444;
                    border-radius: 4px;
                    padding: 4px 10px;
                    font-size: 10px;
                }
                QPushButton:hover:enabled {
                    background-color: #333333;
                    border: 1px solid #3A8DFF;
                }
                QPushButton:disabled {
                    background-color: #1F1F1F;
                    color: #6A6A6A;
                    border: 1px solid #333333;
                }
            """)
            btn.clicked.connect(lambda _checked=False, tid=tool_id: self.tool_clicked.emit(tid))
            self.layout().addWidget(btn)
            self.tool_buttons.append(btn)

    def _step_style(self, enabled: bool, active: bool) -> str:
        if active:
            return """
                QPushButton {
                    background-color: #2D6CDF;
                    color: #FFFFFF;
                    border: 1px solid #2D6CDF;
                    border-radius: 4px;
                    padding: 4px 10px;
                    font-size: 11px;
                    font-weight: bold;
                }
            """
        if enabled:
            return """
                QPushButton {
                    background-color: #252525;
                    color: #E6E6E6;
                    border: 1px solid #3A3A3A;
                    border-radius: 4px;
                    padding: 4px 10px;
                    font-size: 11px;
                }
                QPushButton:hover:enabled {
                    border: 1px solid #3A8DFF;
                }
            """
        return """
            QPushButton {
                background-color: #1B1B1B;
                color: #6A6A6A;
                border: 1px solid #2A2A2A;
                border-radius: 4px;
                padding: 4px 10px;
                font-size: 11px;
            }
        """
