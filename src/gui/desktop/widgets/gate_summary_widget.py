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
from pathlib import Path
from typing import Optional, List, Dict, Any, cast

from PySide6.QtCore import Qt, Signal, Slot, QTimer  # type: ignore
from PySide6.QtWidgets import (  # type: ignore
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QGroupBox, QPushButton, QSizePolicy
)
from PySide6.QtGui import QFont, QColor, QPalette, QDesktopServices, QMouseEvent  # type: ignore
from PySide6.QtCore import QUrl

from gui.services.gate_summary_service import (
    GateSummary, GateResult, GateStatus, fetch_gate_summary
)
from gui.services.consolidated_gate_summary_service import (
    fetch_consolidated_gate_summary,
    get_consolidated_gate_summary_service,
)
from contracts.portfolio.gate_summary_schemas import (
    GateSummaryV1,
    GateItemV1,
    GateStatus as ContractGateStatus,
    safe_gate_summary_from_raw,
    safe_gate_item_from_raw,
    build_error_gate_item,
    GateReasonCode,
    sanitize_raw
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

        # Subtitle (optional, for ranking explain gates)
        subtitle = self._get_subtitle()
        if subtitle:
            subtitle_label = QLabel(subtitle)
            subtitle_label.setStyleSheet("color: #9A9A9A; font-size: 9px; font-style: italic;")
            subtitle_label.setWordWrap(True)
            subtitle_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(subtitle_label)

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
        
        # Set tooltip
        self._set_tooltip()

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

    def _get_subtitle(self) -> Optional[str]:
        """Get subtitle text for the gate card."""
        # Special handling for ranking explain gates
        if self.gate_result.gate_id in ("ranking_explain", "ranking_explain_missing"):
            return "Click to open ranking explain report"
        # Other gates could have subtitles from details field
        if self.gate_result.details and "subtitle" in self.gate_result.details:
            return str(self.gate_result.details["subtitle"])
        return None
    
    def _set_tooltip(self) -> None:
        """Set tooltip for the gate card."""
        # Special handling for ranking explain gates
        if self.gate_result.gate_id in ("ranking_explain", "ranking_explain_missing"):
            self.setToolTip("Open ranking_explain_report.json in default viewer")
        elif self.gate_result.gate_id == "ranking_explain_error":
            self.setToolTip("Error processing ranking explain report")
        else:
            # Default tooltip shows gate name and status
            self.setToolTip(f"{self.gate_result.gate_name}: {self.gate_result.status.value}")
    
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

    def __init__(self, job_id: Optional[str] = None, parent=None):
        super().__init__(parent)
        self.setProperty('job_id', job_id)
        self.gate_cards: Dict[str, GateCard] = {}
        self.refresh_timer = QTimer()
        self.refresh_timer.timeout.connect(self.refresh)
        self.refresh_interval = 10000  # 10 seconds
        self.setup_ui()
        self.refresh()  # initial fetch
        # Set default opener for ranking explain artifacts
        self._set_default_ranking_explain_opener()
    
    @property
    def job_id(self) -> Optional[str]:
        """Get job_id from Qt property."""
        return self.property('job_id')
    
    def _set_default_ranking_explain_opener(self) -> None:
        """Set default opener for ranking explain artifacts using QDesktopServices."""
        from PySide6.QtWidgets import QMessageBox
        
        def default_opener(artifact_path: Path) -> None:
            """Default opener that uses QDesktopServices.openUrl."""
            if not artifact_path.exists():
                # Show informative message
                QMessageBox.information(
                    self,
                    "Ranking Explain Report Missing",
                    f"The ranking explain report has not been generated yet.\n\n"
                    f"Expected path:\n{artifact_path}\n\n"
                    f"This is normal if the job is still running or if ranking explain "
                    f"has not been computed for this job."
                )
                return
            
            # Open the file with default application
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(artifact_path)))
        
        self.setProperty('ranking_explain_opener', default_opener)
    
    def set_ranking_explain_opener(self, opener: callable) -> None:
        """Set custom opener for ranking explain artifacts (for testing).
        
        Args:
            opener: Callable that takes a Path argument and opens the artifact.
                   Should handle missing file case appropriately.
        """
        self.setProperty('ranking_explain_opener', opener)
    
    def _get_ranking_explain_opener(self) -> callable:
        """Get the ranking explain artifact opener.
        
        Returns:
            Callable that takes a Path argument.
        """
        opener = self.property('ranking_explain_opener')
        if opener is None:
            # Fallback to default opener if not set
            self._set_default_ranking_explain_opener()
            opener = self.property('ranking_explain_opener')
        return opener

    def setup_ui(self):
        """Initialize the UI components."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        # Group box - show job context if job_id provided
        if self.job_id:
            group_title = f"Gates for Job: {self.job_id[:8]}..."
        else:
            group_title = "System Gates"
        
        self.group = QGroupBox(group_title)
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
            if self.job_id:
                # Use consolidated service with job_id to get ranking explain gates
                service = get_consolidated_gate_summary_service()
                consolidated_summary = service.fetch_consolidated_summary(job_id=self.job_id)
                summary = self._convert_consolidated_to_gate_summary(consolidated_summary)
            else:
                # Use regular system gates
                summary = fetch_gate_summary()
            
            self.update_ui(summary)
            self.summary_updated.emit(summary)
        except Exception as e:
            logger.error(f"Failed to fetch gate summary: {e}")
            self.summary_label.setText("Overall: ERROR")
            self.summary_label.setStyleSheet("color: #F44336; font-weight: bold;")

    def _convert_consolidated_to_gate_summary(self, consolidated_summary: GateSummaryV1) -> GateSummary:
        """
        Convert GateSummaryV1 (consolidated) to GateSummary (legacy) for UI compatibility.
        
        Uses safe helpers to handle parsing errors and preserve telemetry details.
        """
        from gui.services.gate_summary_service import GateResult, GateStatus
        
        # Map GateItemV1 to GateResult with safe handling
        gate_results = []
        error_count = 0
        
        for item in consolidated_summary.gates:
            try:
                # Map ContractGateStatus to UI GateStatus
                status_map = {
                    ContractGateStatus.PASS: GateStatus.PASS,
                    ContractGateStatus.WARN: GateStatus.WARN,
                    ContractGateStatus.REJECT: GateStatus.FAIL,  # REJECT maps to FAIL in UI
                    ContractGateStatus.SKIP: GateStatus.UNKNOWN,
                    ContractGateStatus.UNKNOWN: GateStatus.UNKNOWN,
                }
                status = status_map.get(item.status, GateStatus.UNKNOWN)
                
                # Convert evidence_refs to actions if present
                actions = []
                if item.evidence_refs:
                    for ref in item.evidence_refs[:3]:  # Limit to 3 actions
                        actions.append({
                            "label": f"View {ref.split('/')[-1]}" if '/' in ref else "View Evidence",
                            "url": ref
                        })
                
                # Preserve telemetry details from GateItemV1.details
                details = {}
                if item.details:
                    # Sanitize details to ensure JSON-safe structure
                    details = sanitize_raw(item.details)
                
                # Add reason_codes to details for UI consumption
                if item.reason_codes:
                    details["reason_codes"] = item.reason_codes
                
                gate_result = GateResult(
                    gate_id=item.gate_id,
                    gate_name=item.gate_name,
                    status=status,
                    message=item.message,
                    timestamp=item.evaluated_at_utc,
                    actions=actions if actions else None,
                    details=details if details else None,
                )
                gate_results.append(gate_result)
                
            except Exception as e:
                # If individual gate conversion fails, create error gate
                error_count += 1
                logger.warning(f"Failed to convert gate item {getattr(item, 'gate_id', 'unknown')}: {e}")
                
                # Create error gate using safe helper
                error_gate = build_error_gate_item(
                    gate_id="gate_conversion_error",
                    reason_code=GateReasonCode.GATE_ITEM_PARSE_ERROR.value,
                    error=e,
                    error_path="gui.desktop.widgets.gate_summary_widget._convert_consolidated_to_gate_summary",
                    raw=sanitize_raw(item) if hasattr(item, 'model_dump') else str(item),
                )
                
                # Convert error gate to GateResult
                error_gate_result = GateResult(
                    gate_id=error_gate.gate_id,
                    gate_name=error_gate.gate_name,
                    status=GateStatus.FAIL,  # Error gates are FAIL in UI
                    message=error_gate.message,
                    timestamp=error_gate.evaluated_at_utc,
                    actions=None,
                    details=error_gate.details,
                )
                gate_results.append(error_gate_result)
        
        # Determine overall status based on converted gates
        overall_status = GateStatus.UNKNOWN
        if gate_results:
            if any(g.status == GateStatus.FAIL for g in gate_results):
                overall_status = GateStatus.FAIL
            elif any(g.status == GateStatus.WARN for g in gate_results):
                overall_status = GateStatus.WARN
            elif all(g.status == GateStatus.PASS for g in gate_results):
                overall_status = GateStatus.PASS
        
        # Generate appropriate overall message
        if error_count > 0:
            overall_message = f"Consolidated gates ({error_count} conversion errors)"
        else:
            overall_message = "Consolidated gates"
        
        # Create GateSummary
        return GateSummary(
            gates=gate_results,
            overall_status=overall_status,
            overall_message=overall_message,
            timestamp=consolidated_summary.evaluated_at_utc,
        )

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
        """Handle gate card click: open explanation dialog or artifact."""
        # Special handling for ranking_explain gates - open artifact in Artifact Navigator
        if gate_result.gate_id in ("ranking_explain", "ranking_explain_missing"):
            self._open_ranking_explain_artifact(gate_result)
            return
        
        # For other gates, show explanation dialog
        dialog = GateExplanationDialog(gate_result, parent=self)
        dialog.exec()

    def _open_ranking_explain_artifact(self, gate_result: GateResult) -> None:
        """Open ranking_explain_report.json using the configured opener seam."""
        if not self.job_id:
            logger.error("Cannot open ranking explain artifact: job_id is None")
            return
        
        from pathlib import Path
        
        # Construct path to ranking_explain_report.json
        artifact_path = Path("outputs") / "jobs" / self.job_id / "ranking_explain_report.json"
        
        # Get the configured opener and call it
        opener = self._get_ranking_explain_opener()
        try:
            opener(artifact_path)
        except Exception as e:
            logger.error(f"Failed to open ranking explain artifact: {e}")
            # Fallback: show error message
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.critical(
                self,
                "Error Opening Report",
                f"Failed to open ranking explain report:\n{artifact_path}\n\n{e}"
            )

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