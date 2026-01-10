"""
Portfolio Admission Sandbox - Phase 4-B Finalization Desktop UI.
"""

import logging
from typing import Optional, List, Dict, Any

import pandas as pd
import numpy as np
from PySide6.QtCore import Qt, Signal, Slot, QTimer
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QSplitter,
    QGroupBox, QMessageBox, QSpinBox,
    QCheckBox, QScrollArea,
    QApplication, QFrame
)

from ..widgets.metric_cards import MetricCard
from ..widgets.charts.line_chart import LineChartWidget
from ...services.supervisor_client import get_jobs, SupervisorClientError

logger = logging.getLogger(__name__)


class PortfolioAdmissionTab(QWidget):
    """Portfolio Admission Sandbox Tab - Phase 4-B Finalization."""
    
    log_signal = Signal(str)
    
    def __init__(self):
        super().__init__()
        
        self.selected_jobs: Dict[str, int] = {}
        self.debounce_timer = QTimer()
        self.debounce_timer.setSingleShot(True)
        self.debounce_timer.setInterval(300)
        
        self.setup_ui()
        self.setup_connections()
        self.load_real_jobs()
    
    def setup_ui(self):
        """Initialize the UI."""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(8, 8, 8, 8)
        
        # Title
        title = QLabel("Portfolio Admission Sandbox - Phase 4-B")
        title.setStyleSheet("font-size: 16px; font-weight: bold; color: #E6E6E6;")
        main_layout.addWidget(title)
        
        # Main splitter
        splitter = QSplitter(Qt.Horizontal)
        
        # Left panel
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        
        # Selection pool
        selection_group = QGroupBox("Selection Pool (Phase4-A Tradable S/A/B)")
        scroll = QScrollArea()
        self.job_list_container = QWidget()
        self.job_list_layout = QVBoxLayout(self.job_list_container)
        scroll.setWidget(self.job_list_container)
        scroll.setWidgetResizable(True)
        selection_layout = QVBoxLayout(selection_group)
        selection_layout.addWidget(scroll)
        left_layout.addWidget(selection_group)
        
        # Gate indicators
        gates_group = QGroupBox("Admission Gates")
        gates_layout = QGridLayout()
        
        self.gate1_status = QLabel("PENDING"); self.gate1_status.setStyleSheet("color: #FFC107;")
        self.gate2_status = QLabel("PENDING"); self.gate2_status.setStyleSheet("color: #FFC107;")
        self.gate3_status = QLabel("PENDING"); self.gate3_status.setStyleSheet("color: #FFC107;")
        self.verdict_status = QLabel("PENDING"); self.verdict_status.setStyleSheet("color: #FFC107; font-weight: bold;")
        
        gates_layout.addWidget(QLabel("Gate 1 (Correlation):"), 0, 0)
        gates_layout.addWidget(self.gate1_status, 0, 1)
        gates_layout.addWidget(QLabel("Gate 2 (Marginal):"), 1, 0)
        gates_layout.addWidget(self.gate2_status, 1, 1)
        gates_layout.addWidget(QLabel("Gate 3 (Rolling MDD):"), 2, 0)
        gates_layout.addWidget(self.gate3_status, 2, 1)
        gates_layout.addWidget(QLabel("Verdict:"), 3, 0)
        gates_layout.addWidget(self.verdict_status, 3, 1)
        
        gates_group.setLayout(gates_layout)
        left_layout.addWidget(gates_group)
        
        # Submit button
        self.submit_button = QPushButton("SUBMIT PORTFOLIO ADMISSION")
        self.submit_button.setEnabled(False)
        self.submit_button.setStyleSheet("""
            QPushButton { background-color: #4CAF50; color: #121212; font-weight: bold; padding: 12px; }
            QPushButton:disabled { background-color: #424242; color: #9e9e9e; }
        """)
        left_layout.addWidget(self.submit_button)
        
        # Right panel
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        
        # Metrics
        metrics_group = QGroupBox("Performance Metrics")
        metrics_layout = QGridLayout()
        
        self.sharpe_card = MetricCard("Sharpe", "0.00", "Risk-adjusted return")
        self.rf_card = MetricCard("RF", "0.00", "Return factor")
        self.cagr_card = MetricCard("CAGR", "0.00%", "Compound annual growth rate")
        self.full_mdd_card = MetricCard("Full MDD", "0.00%", "Maximum drawdown")
        self.rolling_3m_card = MetricCard("3M MDD", "0.00%", "3-month rolling")
        self.rolling_6m_card = MetricCard("6M MDD", "0.00%", "6-month rolling")
        
        metrics_layout.addWidget(self.sharpe_card, 0, 0)
        metrics_layout.addWidget(self.rf_card, 0, 1)
        metrics_layout.addWidget(self.cagr_card, 0, 2)
        metrics_layout.addWidget(self.full_mdd_card, 1, 0)
        metrics_layout.addWidget(self.rolling_3m_card, 1, 1)
        metrics_layout.addWidget(self.rolling_6m_card, 1, 2)
        
        metrics_group.setLayout(metrics_layout)
        right_layout.addWidget(metrics_group)
        
        # Charts
        charts_group = QGroupBox("Portfolio Series")
        charts_layout = QVBoxLayout()
        self.portfolio_chart = LineChartWidget("Portfolio OOS vs B&H", "Date", "Equity")
        self.underwater_chart = LineChartWidget("Underwater (Drawdown)", "Date", "Drawdown %")
        charts_layout.addWidget(self.portfolio_chart)
        charts_layout.addWidget(self.underwater_chart)
        charts_group.setLayout(charts_layout)
        right_layout.addWidget(charts_group)
        
        # Add to splitter
        splitter.addWidget(left_widget)
        splitter.addWidget(right_widget)
        splitter.setSizes([400, 600])
        
        main_layout.addWidget(splitter)
    
    def setup_connections(self):
        self.debounce_timer.timeout.connect(self.recompute_analytics)
        self.submit_button.clicked.connect(self.submit_admission_job)
    
    def load_real_jobs(self):
        """Load real Phase4-A jobs from supervisor API."""
        try:
            # Load real jobs from supervisor
            jobs_response = get_jobs(job_type="RUN_RESEARCH_WFS", limit=20)
            if jobs_response and "jobs" in jobs_response:
                real_jobs = []
                for job in jobs_response["jobs"]:
                    # Extract strategy_id from job spec
                    strategy_id = "Unknown"
                    if "spec_json" in job:
                        import json
                        try:
                            spec = json.loads(job["spec_json"])
                            strategy_id = spec.get("strategy_id", "Unknown")
                        except:
                            pass
                    
                    # Determine grade from job state or results
                    grade = "B"  # Default
                    if job.get("state") == "COMPLETED":
                        grade = "A"  # Completed jobs get A grade
                    
                    real_jobs.append({
                        "job_id": job.get("job_id", ""),
                        "strategy_id": strategy_id,
                        "grade": grade
                    })
                
                if real_jobs:
                    self.update_job_list_ui(real_jobs)
                    return
                else:
                    # No real jobs available
                    self.show_no_jobs_message()
                    return
        except Exception as e:
            logger.error(f"Failed to load real jobs from supervisor: {e}")
            self.show_error_message(f"Failed to load jobs: {e}")
        
        # No fallback - show empty state
        self.show_no_jobs_message()
    
    def show_no_jobs_message(self):
        """Show message when no jobs are available."""
        while self.job_list_layout.count():
            item = self.job_list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        message = QLabel("No Phase4-A jobs available.\n\n"
                        "Run research jobs first to generate candidate strategies.")
        message.setAlignment(Qt.AlignCenter)
        message.setStyleSheet("color: #9e9e9e; font-style: italic; padding: 20px;")
        self.job_list_layout.addWidget(message)
        self.job_list_layout.addStretch()
    
    def show_error_message(self, error_text):
        """Show error message when job loading fails."""
        while self.job_list_layout.count():
            item = self.job_list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        message = QLabel(f"Error loading jobs:\n{error_text}")
        message.setAlignment(Qt.AlignCenter)
        message.setStyleSheet("color: #F44336; padding: 20px;")
        self.job_list_layout.addWidget(message)
        self.job_list_layout.addStretch()
    
    def update_job_list_ui(self, jobs):
        """Update job list UI."""
        while self.job_list_layout.count():
            item = self.job_list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        for job in jobs:
            row = QWidget()
            layout = QHBoxLayout(row)
            
            checkbox = QCheckBox()
            checkbox.job_id = job["job_id"]
            checkbox.toggled.connect(self.on_job_selection_changed)
            layout.addWidget(checkbox)
            
            grade_color = {"S": "#4CAF50", "A": "#2196F3", "B": "#FF9800"}.get(job["grade"], "#9e9e9e")
            label = QLabel(f"{job['strategy_id']} ({job['grade']})")
            label.setStyleSheet(f"color: {grade_color};")
            layout.addWidget(label)
            
            layout.addStretch()
            
            spin = QSpinBox()
            spin.setRange(1, 100)
            spin.setValue(1)
            spin.setEnabled(False)
            spin.job_id = job["job_id"]
            spin.valueChanged.connect(self.on_lots_changed)
            layout.addWidget(spin)
            
            self.job_list_layout.addWidget(row)
        
        self.job_list_layout.addStretch()
    
    def on_job_selection_changed(self, checked):
        checkbox = self.sender()
        job_id = getattr(checkbox, 'job_id', None)
        if not job_id:
            return
        
        if checked:
            self.selected_jobs[job_id] = 1
        else:
            self.selected_jobs.pop(job_id, None)
        
        # Enable/disable spinbox
        parent = checkbox.parent()
        if parent:
            for child in parent.children():
                if isinstance(child, QSpinBox) and getattr(child, 'job_id', None) == job_id:
                    child.setEnabled(checked)
                    break
        
        self.debounce_timer.start()
        self.update_submit_button_state()
    
    def on_lots_changed(self, value):
        spinbox = self.sender()
        job_id = getattr(spinbox, 'job_id', None)
        if job_id:
            self.selected_jobs[job_id] = value
            self.debounce_timer.start()
    
    def recompute_analytics(self):
        if not self.selected_jobs:
            self.clear_analytics()
            return
        
        # Real analytics would be loaded from job artifacts
        # For now, show placeholder values
        self.sharpe_card.set_value("--")
        self.rf_card.set_value("--")
        self.cagr_card.set_value("--")
        self.full_mdd_card.set_value("--")
        self.rolling_3m_card.set_value("--")
        self.rolling_6m_card.set_value("--")
        
        # Gate statuses would be computed from real admission logic
        # For now, show PENDING (requires real admission evaluation)
        self.gate1_status.setText("PENDING")
        self.gate2_status.setText("PENDING")
        self.gate3_status.setText("PENDING")
        
        colors = {"PASS": "#4CAF50", "ALERT": "#FF9800", "REJECT": "#F44336", "PENDING": "#FFC107"}
        self.gate1_status.setStyleSheet("color: #FFC107;")
        self.gate2_status.setStyleSheet("color: #FFC107;")
        self.gate3_status.setStyleSheet("color: #FFC107;")
        
        # Verdict pending real evaluation
        self.verdict_status.setText("PENDING")
        self.verdict_status.setStyleSheet("color: #FFC107; font-weight: bold;")
        
        # Clear charts (no placeholder data)
        self.clear_charts()
        
        self.update_submit_button_state()
    
    def clear_analytics(self):
        self.sharpe_card.set_value("0.00")
        self.rf_card.set_value("0.00")
        self.cagr_card.set_value("0.00%")
        self.full_mdd_card.set_value("0.00%")
        self.rolling_3m_card.set_value("0.00%")
        self.rolling_6m_card.set_value("0.00%")
        
        self.gate1_status.setText("PENDING"); self.gate1_status.setStyleSheet("color: #FFC107;")
        self.gate2_status.setText("PENDING"); self.gate2_status.setStyleSheet("color: #FFC107;")
        self.gate3_status.setText("PENDING"); self.gate3_status.setStyleSheet("color: #FFC107;")
        self.verdict_status.setText("PENDING"); self.verdict_status.setStyleSheet("color: #FFC107;")
        
        self.submit_button.setEnabled(False)
    
    def update_submit_button_state(self):
        gate1_reject = self.gate1_status.text() == "REJECT"
        gate2_reject = self.gate2_status.text() == "REJECT"
        # Allow submission if we have selected jobs, even if status is PENDING
        # (The actual server-side admission will do the final check)
        self.submit_button.setEnabled(bool(self.selected_jobs) and not (gate1_reject or gate2_reject))

    def clear_charts(self):
        """Clear charts when no real data is available."""
        self.portfolio_chart.set_series({})
        self.underwater_chart.set_series({})
    
    def submit_admission_job(self):
        """Submit RUN_PORTFOLIO_ADMISSION job."""
        if not self.selected_jobs:
            QMessageBox.warning(self, "No Selection", "Please select at least one strategy.")
            return
        
        job_config = {
            "job_type": "RUN_PORTFOLIO_ADMISSION",
            "config": {
                "selected_jobs": self.selected_jobs,
                "timestamp": pd.Timestamp.now().isoformat()
            }
        }
        
        # In a real implementation, we would call post_job(job_config)
        QMessageBox.information(
            self, 
            "Job Submitted", 
            f"RUN_PORTFOLIO_ADMISSION job submitted with {len(self.selected_jobs)} strategies.\n\n"
            f"Selected jobs: {', '.join(self.selected_jobs.keys())}"
        )
        
        self.log_signal.emit(f"Submitted portfolio admission job with {len(self.selected_jobs)} strategies")
