from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
)


class GateDrawer(QWidget):
    """Collapsible drawer that wraps the gate summary content."""

    collapsed_changed = Signal(bool)

    def __init__(self, expanded_widget: QWidget, parent=None):
        super().__init__(parent)
        self.expanded_widget = expanded_widget
        self._collapsed = True

        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.summary_label = QLabel("Gates: —")
        self.summary_label.setObjectName("gateDrawer_summary")

        self.toggle_button = QPushButton("Expand")
        self.toggle_button.setObjectName("gateDrawer_toggle")
        self.toggle_button.clicked.connect(self._toggle)

        self.summary_strip = QWidget()
        strip_layout = QHBoxLayout(self.summary_strip)
        strip_layout.setContentsMargins(8, 4, 8, 4)
        strip_layout.setSpacing(12)
        strip_layout.addWidget(self.summary_label)
        strip_layout.addStretch()
        strip_layout.addWidget(self.toggle_button)
        self.summary_strip.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        self.expanded_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.summary_strip)
        layout.addWidget(self.expanded_widget)

        self.set_collapsed(True)

    def _toggle(self):
        self.set_collapsed(not self._collapsed)

    def set_collapsed(self, collapsed: bool):
        if self._collapsed == collapsed:
            return
        self._collapsed = collapsed
        self.expanded_widget.setVisible(not collapsed)
        self.toggle_button.setText("Expand" if collapsed else "Collapse")
        self.collapsed_changed.emit(self._collapsed)

    def is_collapsed(self) -> bool:
        return self._collapsed

    def set_summary_counts(self, fail: int, warn: int, ok: int, total: int) -> None:
        self.summary_label.setText(f"Gates: FAIL {fail}  WARN {warn}  PASS {ok}  TOTAL {total}")
