from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
)


class StickyVerdictBar(QWidget):
    """Minimal sticky header that shows overall verdict and refresh control."""

    refresh_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("stickyVerdictBar")
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(12)

        self.overall_label = QLabel("Overall: —")
        self.overall_label.setObjectName("stickyVerdictBar_overall")
        layout.addWidget(self.overall_label, alignment=Qt.AlignmentFlag.AlignVCenter)

        self.status_label = QLabel("")
        self.status_label.setObjectName("stickyVerdictBar_status")
        layout.addWidget(self.status_label, alignment=Qt.AlignmentFlag.AlignVCenter)

        layout.addStretch()

        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.setObjectName("stickyVerdictBar_refresh")
        self.refresh_button.clicked.connect(self.refresh_requested.emit)
        layout.addWidget(self.refresh_button, alignment=Qt.AlignmentFlag.AlignVCenter)

    def set_overall_text(self, text: str) -> None:
        self.overall_label.setText(text)

    def set_status_text(self, text: str) -> None:
        self.status_label.setText(text)
