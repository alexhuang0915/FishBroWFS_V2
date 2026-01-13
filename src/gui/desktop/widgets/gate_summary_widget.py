"""
Gate Summary Widget – Visualizes five system gates with PASS/WARN/FAIL status.

Five gates:
1. API Health
2. API Readiness
3. Supervisor DB SSOT
4. Worker Execution Reality
5. Registry Surface

Each gate is displayed as a card with icon, name, status, message, and optional drill‑down action.
"""

import logging
from typing import Optional, List, Dict, Any

from PySide6.QtCore import Qt, Signal, Slot, QTimer  # type: ignore
from PySide6.QtWidgets import (  # type: ignore
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QGroupBox, QPushButton, QSizePolicy
)
from PySide6.QtGui import QFont, QColor, QPalette, QDesktopServices, QMouseEvent  # type: ignore

from gui.services.gate_summary_service import (
    GateSummary, GateResult, GateStatus, fetch_gate_summary
)
from .gate_explanation_dialog import GateExplanationDialog

logger = logging.getLogger(__name__)


class GateCard(QWidget):
    """Single gate card widget."""

    clicked = Signal(object)  # emits GateResult

    def __init__(self, gate_result: GateResult, parent=None):
        super().__init__(parent)
        self.gate_result = gate_result
        self.setup_ui()
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def setup_ui(self):
        """Initialize card UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(6)

        # Gate name (bold)
        name_label = QLabel(self.gate_result.gate_name)
        name_label.setStyleSheet("color: #E6E6E6; font-weight: bold; font-size: 12px;")
        name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(name_label)

        # Status icon and text
        status_layout = QHBoxLayout()
        status_layout.setSpacing(8)
        # Icon
        icon_label = QLabel()
        icon_label.setFixedSize(24, 24)
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._set_status_icon(icon_label)
        status_layout.addWidget(icon_label)
        # Status text
        status_text = QLabel(self.gate_result.status.value)
        status_text.setStyleSheet(self._status_color_style())
        status_text.setFont(QFont("Arial", 10, QFont.Weight.Bold))
        status_layout.addWidget(status_text)
        status_layout.addStretch()
        layout.addLayout(status_layout)

        # Message (truncated if too long)
        message = self.gate_result.message
        if len(message) > 80:
            message = message[:77] + "..."
        message_label = QLabel(message)
        message_label.setStyleSheet("color: #B0B0B0; font-size: 10px;")
        message_label.setWordWrap(True)
        message_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        layout.addWidget(message_label)

        # Actions (if any)
        if self.gate_result.actions:
            actions_layout = QHBoxLayout()
            actions_layout.setSpacing(4)
            for action in self.gate_result.actions[:2]:  # limit to 2 buttons
                btn = QPushButton(action.get("label", "Action"))
                btn.setStyleSheet("""
                    QPushButton {
                        background-color: #2A2A2A;
                        color: #E6E6E6;
                        border: 1px solid #555555;
                        border-radius: 3px;
                        padding: 4px 8px;
                        font-size: 10px;
                    }
                    QPushButton:hover {
                        background-color: #3A3A3A;
                        border: 1px solid #3A8DFF;
                    }
                """)
                btn.setCursor(Qt.CursorShape.PointingHandCursor)
                # Store URL as property
                url = action.get("url")
                if url:
                    btn.clicked.connect(lambda checked, u=url: self._open_url(u))
                actions_layout.addWidget(btn)
            actions_layout.addStretch()
            layout.addLayout(actions_layout)

        # Timestamp (optional)
        if self.gate_result.timestamp:
            ts_label = QLabel(self.gate_result.timestamp[:19].replace("T", " "))
            ts_label.setStyleSheet("color: #666666; font-size: 9px;")
            ts_label.setAlignment(Qt.AlignmentFlag.AlignRight)
            layout.addWidget(ts_label)

        layout.addStretch()

        # Set card background based on status
        self.setStyleSheet(self._card_background_style())

    def _set_status_icon(self, icon_label: QLabel):
        """Set icon based on gate status."""
        status = self.gate_result.status
        if status == GateStatus.PASS:
            icon_label.setText("✅")
            icon_label.setStyleSheet("color: #4CAF50; font-size: 18px;")
        elif status == GateStatus.WARN:
            icon_label.setText("⚠️")
            icon_label.setStyleSheet("color: #FF9800; font-size: 18px;")
        elif status == GateStatus.FAIL:
            icon_label.setText("❌")
            icon_label.setStyleSheet("color: #F44336; font-size: 18px;")
        else:
            icon_label.setText("❓")
            icon_label.setStyleSheet("color: #9E9E9E; font-size: 18px;")

    def _status_color_style(self) -> str:
        """Return CSS color for status text."""
        status = self.gate_result.status
        if status == GateStatus.PASS:
            return "color: #4CAF50;"
        elif status == GateStatus.WARN:
            return "color: #FF9800;"
        elif status == GateStatus.FAIL:
            return "color: #F44336;"
        else:
            return "color: #9E9E9E;"

    def _card_background_style(self) -> str:
        """Return CSS for card background."""
        status = self.gate_result.status
        if status == GateStatus.PASS:
            return """
                QWidget {
                    background-color: #1A2A1A;
                    border: 1px solid #2E7D32;
                    border-radius: 6px;
                }
            """
        elif status == GateStatus.WARN:
            return """
                QWidget {
                    background-color: #2A2A1A;
                    border: 1px solid #FF9800;
                    border-radius: 6px;
                }
            """
        elif status == GateStatus.FAIL:
            return """
                QWidget {
                    background-color: #2A1A1A;
                    border: 1px solid #F44336;
                    border-radius: 6px;
                }
            """
        else:
            return """
                QWidget {
                    background-color: #1E1E1E;
                    border: 1px solid #555555;
                    border-radius: 6px;
                }
            """

    def _open_url(self, url: str):
        """Open URL in default browser (or internal navigation)."""
        # If it's a relative path, we could open in internal UI, but for now just log.
        logger.info(f"Gate card action clicked: {url}")
        # For simplicity, we'll just emit a signal that parent can handle.
        # We'll implement later if needed.
        pass

    def mousePressEvent(self, event: QMouseEvent):
        """Emit clicked signal when card is clicked."""
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.gate_result)
        super().mousePressEvent(event)

    def update_gate(self, gate_result: GateResult):
        """Update card with new gate result."""
        self.gate_result = gate_result
        # Clear layout and rebuild? Simpler: just update labels.
        # For now we'll just replace the widget later.
        pass


class GateSummaryWidget(QWidget):
    """Widget that displays five gate cards and refreshes periodically."""

    # Signal emitted when gate summary is updated
    summary_updated = Signal(GateSummary)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.gate_cards: Dict[str, GateCard] = {}
        self.refresh_timer = QTimer()
        self.refresh_timer.timeout.connect(self.refresh)
        self.refresh_interval = 10000  # 10 seconds
        self.setup_ui()
        self.refresh()  # initial fetch

    def setup_ui(self):
        """Initialize the UI components."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        # Group box
        self.group = QGroupBox("System Gates")
        self.group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                border: 2px solid #5d4037;
                background-color: #1E1E1E;
                margin-top: 5px;
                padding-top: 8px;
                font-size: 12px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 8px;
                padding: 0 4px 0 4px;
                color: #E6E6E6;
            }
        """)

        # Horizontal layout for cards
        self.cards_layout = QHBoxLayout()
        self.cards_layout.setSpacing(12)
        self.cards_layout.setContentsMargins(8, 8, 8, 8)

        # Placeholder cards (will be populated by refresh)
        self.placeholder_label = QLabel("Loading gate status...")
        self.placeholder_label.setStyleSheet("color: #9e9e9e; font-size: 11px;")
        self.placeholder_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.cards_layout.addWidget(self.placeholder_label)

        # Summary label (overall status)
        self.summary_label = QLabel("Overall: —")
        self.summary_label.setStyleSheet("color: #E6E6E6; font-weight: bold; font-size: 11px;")
        self.summary_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Refresh button
        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.setStyleSheet("""
            QPushButton {
                background-color: #2A2A2A;
                color: #E6E6E6;
                border: 1px solid #555555;
                border-radius: 3px;
                padding: 4px 12px;
                font-size: 10px;
            }
            QPushButton:hover {
                background-color: #3A3A3A;
                border: 1px solid #3A8DFF;
            }
        """)
        self.refresh_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.refresh_button.clicked.connect(self.refresh)

        # Controls layout
        controls_layout = QHBoxLayout()
        controls_layout.addStretch()
        controls_layout.addWidget(self.summary_label)
        controls_layout.addStretch()
        controls_layout.addWidget(self.refresh_button)

        # Add to group
        group_layout = QVBoxLayout(self.group)
        group_layout.addLayout(self.cards_layout)
        group_layout.addLayout(controls_layout)

        layout.addWidget(self.group)

        # Start auto-refresh timer
        self.refresh_timer.start(self.refresh_interval)

    def refresh(self):
        """Fetch latest gate summary and update UI."""
        try:
            summary = fetch_gate_summary()
            self.update_ui(summary)
            self.summary_updated.emit(summary)
        except Exception as e:
            logger.error(f"Failed to fetch gate summary: {e}")
            self.summary_label.setText("Overall: ERROR")
            self.summary_label.setStyleSheet("color: #F44336; font-weight: bold;")

    def update_ui(self, summary: GateSummary):
        """Update UI with new gate summary."""
        # Remove placeholder if present
        if self.placeholder_label is not None:
            self.cards_layout.removeWidget(self.placeholder_label)
            self.placeholder_label.deleteLater()
            self.placeholder_label = None

        # Ensure we have five cards (create or update)
        for gate in summary.gates:
            if gate.gate_id in self.gate_cards:
                # Update existing card (simplify: replace)
                card = self.gate_cards[gate.gate_id]
                self.cards_layout.removeWidget(card)
                card.deleteLater()
            # Create new card
            card = GateCard(gate)
            card.clicked.connect(self._on_gate_clicked)
            self.gate_cards[gate.gate_id] = card
            self.cards_layout.addWidget(card)

        # Ensure we have exactly five cards (if missing, add empty?)
        # Not needed.

        # Update overall status
        overall = summary.overall_status
        if overall == GateStatus.PASS:
            color = "#4CAF50"
        elif overall == GateStatus.WARN:
            color = "#FF9800"
        elif overall == GateStatus.FAIL:
            color = "#F44336"
        else:
            color = "#9E9E9E"
        self.summary_label.setText(f"Overall: {overall.value} – {summary.overall_message}")
        self.summary_label.setStyleSheet(f"color: {color}; font-weight: bold; font-size: 11px;")

        # Update timestamp
        # Could add a small timestamp label

    def _on_gate_clicked(self, gate_result: GateResult):
        """Handle gate card click: open explanation dialog."""
        dialog = GateExplanationDialog(gate_result, parent=self)
        dialog.exec()

    def set_refresh_interval(self, interval_ms: int):
        """Set auto-refresh interval in milliseconds."""
        self.refresh_interval = interval_ms
        self.refresh_timer.stop()
        self.refresh_timer.start(self.refresh_interval)

    def stop_auto_refresh(self):
        """Stop auto-refresh timer."""
        self.refresh_timer.stop()

    def start_auto_refresh(self):
        """Start auto-refresh timer."""
        self.refresh_timer.start(self.refresh_interval)