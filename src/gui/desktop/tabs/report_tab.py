"""
Report TAB for Desktop UI.

Displays artifact checklist and report details for the ACTIVE_RUN.
Binds to the same ACTIVE_RUN selection as Operation/Analytics tabs.
"""

from __future__ import annotations
import json
import logging
from pathlib import Path
from typing import Optional, Dict, Any

from PySide6.QtCore import Qt, Signal, Slot  # type: ignore
from PySide6.QtWidgets import (  # type: ignore
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QTextEdit, QGroupBox,
    QFrame, QScrollArea, QSizePolicy, QTableWidget,
    QTableWidgetItem, QHeaderView, QFormLayout
)

from ..state.active_run_state import active_run_state, RunStatus

logger = logging.getLogger(__name__)


class ReportTab(QWidget):
    """Report tab showing artifact checklist and report details."""
    
    # Signal for logging
    log_signal = Signal(str)
    
    def __init__(self):
        super().__init__()
        self.setup_ui()
        self.refresh_from_state()
    
    def setup_ui(self):
        """Initialize the UI components."""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(8)
        
        # Header section
        header_widget = QWidget()
        header_widget.setStyleSheet("background-color: #1E1E1E; border-radius: 4px; padding: 8px;")
        header_layout = QVBoxLayout(header_widget)
        
        self.run_header_label = QLabel("No run selected")
        self.run_header_label.setStyleSheet("font-size: 14px; font-weight: bold; color: #E6E6E6;")
        header_layout.addWidget(self.run_header_label)
        
        self.run_path_label = QLabel("")
        self.run_path_label.setStyleSheet("color: #9A9A9A; font-size: 11px; font-family: monospace;")
        header_layout.addWidget(self.run_path_label)
        
        main_layout.addWidget(header_widget)
        
        # Create split view: left checklist, right details
        split_widget = QWidget()
        split_layout = QHBoxLayout(split_widget)
        split_layout.setContentsMargins(0, 0, 0, 0)
        split_layout.setSpacing(12)
        
        # Left panel: Artifact Checklist (40%)
        left_panel = QWidget()
        left_panel.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        
        checklist_group = QGroupBox("Artifact Checklist")
        checklist_group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                border: 2px solid #0288d1;
                background-color: #1E1E1E;
                margin-top: 5px;
                padding-top: 8px;
                font-size: 11px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 8px;
                padding: 0 4px 0 4px;
                color: #E6E6E6;
            }
        """)
        checklist_layout = QVBoxLayout()
        
        # Create checklist items
        self.checklist_items = {}
        artifact_defs = [
            ("metrics.json", "Primary performance metrics"),
            ("manifest.json", "Run configuration and metadata"),
            ("run_record.json", "Execution timeline and logs"),
            ("equity.parquet", "Equity curve time series"),
            ("trades.parquet", "Individual trade records"),
            ("report.json", "Comprehensive analysis report"),
            ("governance_summary.json", "Governance compliance snapshot"),
            ("scoring_breakdown.json", "Detailed scoring breakdown"),
        ]
        
        for artifact_name, description in artifact_defs:
            item_widget = self.create_checklist_item(artifact_name, description)
            self.checklist_items[artifact_name] = item_widget
            checklist_layout.addWidget(item_widget)
        
        checklist_layout.addStretch()
        checklist_group.setLayout(checklist_layout)
        left_layout.addWidget(checklist_group)
        
        # Right panel: Details (60%)
        right_panel = QWidget()
        right_panel.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        
        # Metrics JSON viewer
        metrics_group = QGroupBox("Metrics.json")
        metrics_group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                border: 2px solid #2e7d32;
                background-color: #1E1E1E;
                margin-top: 5px;
                padding-top: 8px;
                font-size: 11px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 8px;
                padding: 0 4px 0 4px;
                color: #E6E6E6;
            }
        """)
        metrics_layout = QVBoxLayout()
        
        self.metrics_text = QTextEdit()
        self.metrics_text.setReadOnly(True)
        self.metrics_text.setFontFamily("Monospace")
        self.metrics_text.setFontPointSize(9)
        self.metrics_text.setStyleSheet("""
            QTextEdit {
                background-color: #1E1E1E;
                color: #E6E6E6;
                border: 1px solid #555555;
                border-radius: 3px;
                font-family: 'Consolas', 'Monaco', monospace;
            }
        """)
        self.metrics_text.setPlaceholderText("No metrics.json available")
        
        metrics_layout.addWidget(self.metrics_text)
        metrics_group.setLayout(metrics_layout)
        right_layout.addWidget(metrics_group, 60)  # 60% height
        
        # File preview section
        preview_group = QGroupBox("File Preview")
        preview_group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                border: 2px solid #7b1fa2;
                background-color: #1E1E1E;
                margin-top: 5px;
                padding-top: 8px;
                font-size: 11px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 8px;
                padding: 0 4px 0 4px;
                color: #E6E6E6;
            }
        """)
        preview_layout = QVBoxLayout()
        
        self.preview_text = QTextEdit()
        self.preview_text.setReadOnly(True)
        self.preview_text.setFontFamily("Monospace")
        self.preview_text.setFontPointSize(9)
        self.preview_text.setStyleSheet("""
            QTextEdit {
                background-color: #1E1E1E;
                color: #E6E6E6;
                border: 1px solid #555555;
                border-radius: 3px;
                font-family: 'Consolas', 'Monaco', monospace;
            }
        """)
        self.preview_text.setPlaceholderText("Select a file to preview")
        
        # Preview buttons
        preview_buttons_layout = QHBoxLayout()
        self.preview_equity_btn = QPushButton("Preview Equity")
        self.preview_trades_btn = QPushButton("Preview Trades")
        self.preview_report_btn = QPushButton("Preview Report")
        
        for btn in [self.preview_equity_btn, self.preview_trades_btn, self.preview_report_btn]:
            btn.setStyleSheet("""
                QPushButton {
                    background-color: #2A2A2A;
                    color: #E6E6E6;
                    border: 1px solid #555555;
                    border-radius: 3px;
                    padding: 4px 8px;
                    font-size: 10px;
                }
                QPushButton:hover:enabled {
                    background-color: #3A3A3A;
                    border: 1px solid #3A8DFF;
                }
                QPushButton:disabled {
                    background-color: #1A1A1A;
                    color: #666666;
                    border: 1px solid #333333;
                }
            """)
            btn.setEnabled(False)
            preview_buttons_layout.addWidget(btn)
        
        preview_buttons_layout.addStretch()
        preview_layout.addLayout(preview_buttons_layout)
        preview_layout.addWidget(self.preview_text)
        preview_group.setLayout(preview_layout)
        right_layout.addWidget(preview_group, 40)  # 40% height
        
        # Governance + scoring section (read-only hook)
        governance_group = QGroupBox("Governance & Scoring")
        governance_group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                border: 2px solid #ffa000;
                background-color: #1E1E1E;
                margin-top: 5px;
                padding-top: 8px;
                font-size: 11px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 8px;
                padding: 0 4px 0 4px;
                color: #E6E6E6;
            }
        """)
        governance_layout = QVBoxLayout()
        governance_layout.setContentsMargins(6, 6, 6, 6)
        governance_layout.setSpacing(4)

        def _build_row(file_name: str, btn: QPushButton, status_label: QLabel) -> QWidget:
            widget = QWidget()
            layout = QHBoxLayout(widget)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(8)
            label = QLabel(file_name)
            label.setStyleSheet("font-weight: bold; color: #E6E6E6; font-size: 11px;")
            status_label.setStyleSheet("color: #9A9A9A; font-size: 10px;")
            layout.addWidget(label)
            layout.addStretch()
            layout.addWidget(status_label)
            layout.addWidget(btn)
            return widget

        self.gov_summary_btn = QPushButton("Open governance_summary.json")
        self.gov_summary_status = QLabel("Not available")
        self.gov_summary_btn.setStyleSheet("""
            QPushButton {
                background-color: #2A2A2A;
                color: #E6E6E6;
                border: 1px solid #555555;
                border-radius: 3px;
                padding: 2px 6px;
                font-size: 10px;
            }
            QPushButton:disabled {
                color: #777777;
            }
        """)
        self.gov_summary_btn.setEnabled(False)

        self.scoring_breakdown_btn = QPushButton("Open scoring_breakdown.json")
        self.scoring_breakdown_status = QLabel("Not available")
        self.scoring_breakdown_btn.setStyleSheet("""
            QPushButton {
                background-color: #2A2A2A;
                color: #E6E6E6;
                border: 1px solid #555555;
                border-radius: 3px;
                padding: 2px 6px;
                font-size: 10px;
            }
            QPushButton:disabled {
                color: #777777;
            }
        """)
        self.scoring_breakdown_btn.setEnabled(False)

        governance_layout.addWidget(_build_row(
            "governance_summary.json", self.gov_summary_btn, self.gov_summary_status
        ))
        governance_layout.addWidget(_build_row(
            "scoring_breakdown.json", self.scoring_breakdown_btn, self.scoring_breakdown_status
        ))

        # Policy info display
        policy_info_widget = QWidget()
        policy_info_layout = QFormLayout()
        policy_info_layout.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        policy_info_layout.setFormAlignment(Qt.AlignmentFlag.AlignLeft)

        self.policy_name_value = QLabel("Not available")
        self.policy_name_value.setStyleSheet("color: #E6E6E6; font-weight: bold;")
        policy_info_layout.addRow("Policy Name:", self.policy_name_value)

        self.policy_hash_value = QLabel("Not available")
        policy_info_layout.addRow("Policy Hash:", self.policy_hash_value)

        self.policy_selector_value = QLabel("Not available")
        policy_info_layout.addRow("Selector:", self.policy_selector_value)

        self.policy_resolved_value = QLabel("Not available")
        policy_info_layout.addRow("Resolved Source:", self.policy_resolved_value)

        policy_info_widget.setLayout(policy_info_layout)
        governance_layout.addWidget(policy_info_widget)
        governance_group.setLayout(governance_layout)
        right_layout.addWidget(governance_group, 20)
        
        # Add panels to split layout
        split_layout.addWidget(left_panel, 40)  # 40% width
        split_layout.addWidget(right_panel, 60)  # 60% width
        
        main_layout.addWidget(split_widget)
        
        # Connect signals
        self.preview_equity_btn.clicked.connect(lambda: self.preview_file("equity.parquet"))
        self.preview_trades_btn.clicked.connect(lambda: self.preview_file("trades.parquet"))
        self.preview_report_btn.clicked.connect(lambda: self.preview_file("report.json"))
        self.gov_summary_btn.clicked.connect(lambda: self.preview_file("governance_summary.json"))
        self.scoring_breakdown_btn.clicked.connect(lambda: self.preview_file("scoring_breakdown.json"))
    
    def create_checklist_item(self, artifact_name: str, description: str) -> QWidget:
        """Create a checklist item widget for an artifact."""
        item_widget = QWidget()
        item_layout = QHBoxLayout(item_widget)
        item_layout.setContentsMargins(4, 4, 4, 4)
        item_layout.setSpacing(8)
        
        # Status indicator
        status_indicator = QLabel("◯")
        status_indicator.setStyleSheet("font-size: 14px; color: #666666;")
        status_indicator.setFixedWidth(20)
        item_layout.addWidget(status_indicator)
        
        # Artifact name and description
        text_widget = QWidget()
        text_layout = QVBoxLayout(text_widget)
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(2)
        
        name_label = QLabel(artifact_name)
        name_label.setStyleSheet("font-weight: bold; color: #E6E6E6; font-size: 11px;")
        text_layout.addWidget(name_label)
        
        desc_label = QLabel(description)
        desc_label.setStyleSheet("color: #9A9A9A; font-size: 10px; font-style: italic;")
        text_layout.addWidget(desc_label)
        
        item_layout.addWidget(text_widget)
        item_layout.addStretch()
        
        # Store references
        setattr(item_widget, "status_indicator", status_indicator)
        setattr(item_widget, "artifact_name", artifact_name)
        
        return item_widget
    
    def update_checklist_item(self, artifact_name: str, status: str):
        """Update a checklist item with its current status."""
        if artifact_name not in self.checklist_items:
            return
        
        item_widget = self.checklist_items[artifact_name]
        status_indicator = getattr(item_widget, "status_indicator", None)
        
        if not status_indicator:
            return
        
        # Map status to indicator
        status_config = {
            "READY": ("✓", "#4caf50"),
            "MISSING": ("✗", "#f44336"),
            "EMPTY": ("◯", "#ff9800"),
            "UNKNOWN": ("?", "#9A9A9A"),
        }
        
        symbol, color = status_config.get(status, ("?", "#9A9A9A"))
        status_indicator.setText(symbol)
        status_indicator.setStyleSheet(f"font-size: 14px; color: {color}; font-weight: bold;")
    
    def set_active_run(self, run_dir: Path, season: str, run_name: str) -> None:
        """Set the active run and refresh the display."""
        # Update header
        self.run_header_label.setText(f"Run: {run_name} ({season})")
        
        # Show absolute path
        abs_path = run_dir.absolute()
        self.run_path_label.setText(f"Path: {abs_path}")
        
        # Update checklist from active run state
        self.refresh_from_state()
        
        # Update preview buttons based on what's available
        diagnostics = active_run_state.diagnostics
        self.preview_equity_btn.setEnabled(diagnostics.get("equity_parquet") == "READY")
        self.preview_trades_btn.setEnabled(diagnostics.get("trades_parquet") == "READY")
        self.preview_report_btn.setEnabled(diagnostics.get("report_json") == "READY")
        
        # Display metrics.json if available
        self.update_metrics_display()
        self.update_governance_controls()
    
    def refresh_from_state(self):
        """Refresh the display from the active run state."""
        if active_run_state.status == RunStatus.NONE:
            self.run_header_label.setText("No run selected")
            self.run_path_label.setText("")
            
            # Reset all checklist items to UNKNOWN
            for artifact_name in self.checklist_items:
                self.update_checklist_item(artifact_name, "UNKNOWN")
            
            # Clear metrics display
            self.metrics_text.clear()
            self.preview_text.clear()
            
            # Disable preview buttons
            self.preview_equity_btn.setEnabled(False)
            self.preview_trades_btn.setEnabled(False)
            self.preview_report_btn.setEnabled(False)
            self.update_governance_controls()
            return
        
        # Update checklist from diagnostics
        diagnostics = active_run_state.diagnostics
        
        # Map diagnostics keys to artifact names
        diagnostic_map = {
            "metrics_json": "metrics.json",
            "manifest_json": "manifest.json",
            "run_record_json": "run_record.json",
            "equity_parquet": "equity.parquet",
            "trades_parquet": "trades.parquet",
            "report_json": "report.json",
            "governance_summary_json": "governance_summary.json",
            "scoring_breakdown_json": "scoring_breakdown.json",
        }
        
        for diag_key, artifact_name in diagnostic_map.items():
            status = diagnostics.get(diag_key, "UNKNOWN")
            self.update_checklist_item(artifact_name, status)
        self.update_governance_controls()
    
    def update_metrics_display(self):
        """Update the metrics.json display."""
        if not active_run_state.has_metrics:
            self.metrics_text.setPlainText("No metrics available")
            return
        
        try:
            # Pretty-print JSON
            metrics_json = json.dumps(active_run_state.metrics, indent=2, sort_keys=True)
            self.metrics_text.setPlainText(metrics_json)
        except Exception as e:
            self.metrics_text.setPlainText(f"Error displaying metrics: {str(e)}")
    
    def update_governance_controls(self):
        """Update governance/scoring availability controls."""
        def _normalize_status(key: str) -> str:
            state = active_run_state.diagnostics.get(key, "")
            return "Ready" if state == "READY" else "Not available"

        if not active_run_state.run_dir:
            self.gov_summary_status.setText("Not available")
            self.scoring_breakdown_status.setText("Not available")
            self.gov_summary_btn.setEnabled(False)
            self.scoring_breakdown_btn.setEnabled(False)
            self.update_policy_display()
            return

        summary_ready = active_run_state.diagnostics.get("governance_summary_json") == "READY"
        scoring_ready = active_run_state.diagnostics.get("scoring_breakdown_json") == "READY"

        self.gov_summary_status.setText(_normalize_status("governance_summary_json"))
        self.scoring_breakdown_status.setText(_normalize_status("scoring_breakdown_json"))
        self.gov_summary_btn.setEnabled(summary_ready)
        self.scoring_breakdown_btn.setEnabled(scoring_ready)
        self.update_policy_display()

    def update_policy_display(self):
        """Display the selected policy metadata."""
        policy_info = active_run_state.policy_info
        if not policy_info:
            self.policy_name_value.setText("Not available")
            self.policy_hash_value.setText("Not available")
            self.policy_selector_value.setText("Not available")
            self.policy_resolved_value.setText("Not available")
            return

        self.policy_name_value.setText(policy_info.get("name", "Unknown"))
        self.policy_hash_value.setText(policy_info.get("hash", "Unknown"))
        selector = policy_info.get("selector")
        self.policy_selector_value.setText(selector if selector else "default")
        self.policy_resolved_value.setText(
            policy_info.get("resolved_source", policy_info.get("source", "Unknown"))
        )

    def preview_file(self, file_name: str):
        """Preview the contents of a file."""
        if not active_run_state.run_dir:
            self.preview_text.setPlainText("No active run selected")
            return
        
        file_path = active_run_state.run_dir / file_name
        if not file_path.exists():
            self.preview_text.setPlainText(f"File not found: {file_name}")
            return
        
        try:
            if file_name.endswith(".json"):
                # JSON file - pretty print
                with open(file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                preview_text = json.dumps(data, indent=2, sort_keys=True)
                self.preview_text.setPlainText(preview_text)
                
            elif file_name.endswith(".parquet"):
                # Parquet file - show basic info and sample
                try:
                    import pandas as pd
                    df = pd.read_parquet(file_path)
                    
                    # Create preview with basic info
                    preview_lines = list()
                    preview_lines.append(f"File: {file_name}")
                    preview_lines.append(f"Shape: {df.shape[0]} rows × {df.shape[1]} columns")
                    preview_lines.append(f"Columns: {', '.join(df.columns.tolist())}")
                    preview_lines.append("")
                    preview_lines.append("First 10 rows:")
                    preview_lines.append("=" * 80)
                    
                    # Convert first 10 rows to string
                    preview_lines.append(df.head(10).to_string())
                    
                    self.preview_text.setPlainText("\n".join(preview_lines))
                    
                except ImportError:
                    self.preview_text.setPlainText("pandas not available for parquet preview")
                except Exception as e:
                    self.preview_text.setPlainText(f"Error reading parquet file: {str(e)}")
            
            else:
                # Other file types - try to read as text
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        content = f.read(5000)  # Limit preview size
                    
                    if len(content) >= 5000:
                        content += "\n\n... (preview truncated)"
                    
                    self.preview_text.setPlainText(content)
                except UnicodeDecodeError:
                    self.preview_text.setPlainText(f"Binary file: {file_name} (cannot preview)")
                    
        except Exception as e:
            self.preview_text.setPlainText(f"Error previewing file: {str(e)}")
    
    @Slot(str)
    def log(self, message: str):
        """Log a message."""
        self.log_signal.emit(message)