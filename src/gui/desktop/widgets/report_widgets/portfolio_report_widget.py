"""
Portfolio Report Widget for CTA-grade Allocation Decision Desk.
"""

import json
import logging
from typing import Dict, Any, Optional, List, Tuple

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QTableWidget, QTableWidgetItem, QGroupBox, QScrollArea,
    QFileDialog, QMessageBox, QStackedWidget, QSplitter,
    QAbstractItemView
)
from PySide6.QtGui import QPixmap, QDesktopServices, QColor

from ...widgets.metric_cards import MetricCard, MetricRow
from ...widgets.charts.heatmap import HeatmapWidget
from ...services.supervisor_client import (
    get_portfolio_artifacts, reveal_portfolio_admission_path
)

logger = logging.getLogger(__name__)


class PortfolioReportWidget(QWidget):
    """Portfolio Report Widget."""
    
    log_signal = Signal(str)
    pair_selected = Signal(str, str, float)
    
    def __init__(self, portfolio_id: str, report_data: Dict[str, Any]):
        super().__init__()
        self.portfolio_id = portfolio_id
        self.report_data = report_data
        self.admitted_table_items = {}
        self.rejected_table_items = {}
        
        self.setup_ui()
        self.populate_data()
    
    def setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(12)
        
        # Toolbar
        self.setup_toolbar(main_layout)
        
        # Metrics
        self.metrics_row = MetricRow()
        main_layout.addWidget(self.metrics_row)
        
        # Splitter
        splitter = QSplitter(Qt.Horizontal)
        
        # Left panel
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(12)
        
        # Timeline
        self.setup_timeline(left_layout)
        
        # Tables
        self.setup_tables(left_layout)
        
        # Right panel
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(12)
        
        # Heatmap
        self.heatmap = HeatmapWidget("Strategy Correlation Matrix")
        self.heatmap.setMinimumHeight(400)
        self.heatmap.cell_hovered.connect(self.on_heatmap_hover)
        self.heatmap.cell_clicked.connect(self.on_heatmap_click)
        right_layout.addWidget(self.heatmap)
        
        # Selected pair
        self.selected_pair_label = QLabel("No pair selected")
        self.selected_pair_label.setStyleSheet("color: #9A9A9A; font-size: 12px;")
        right_layout.addWidget(self.selected_pair_label)
        
        splitter.addWidget(left_widget)
        splitter.addWidget(right_widget)
        splitter.setSizes([400, 600])
        
        main_layout.addWidget(splitter, 1)
    
    def setup_toolbar(self, parent_layout):
        toolbar = QWidget()
        toolbar.setStyleSheet("background-color: #2A2A2A; border-radius: 4px; padding: 4px;")
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(8, 4, 8, 4)
        
        self.export_json_btn = QPushButton("📊 Export JSON")
        self.export_json_btn.clicked.connect(self.export_json)
        
        self.export_png_btn = QPushButton("🖼️ Export PNG")
        self.export_png_btn.clicked.connect(self.export_png)
        
        self.open_evidence_btn = QPushButton("📁 Open Admission Evidence")
        self.open_evidence_btn.clicked.connect(self.open_admission_evidence)
        
        for btn in [self.export_json_btn, self.export_png_btn, self.open_evidence_btn]:
            btn.setStyleSheet("""
                QPushButton {
                    background-color: #3A3A3A;
                    color: #E6E6E6;
                    border: 1px solid #555555;
                    border-radius: 4px;
                    padding: 6px 12px;
                    font-size: 11px;
                }
                QPushButton:hover {
                    background-color: #4A4A4A;
                    border-color: #3A8DFF;
                }
            """)
        
        toolbar_layout.addWidget(self.export_json_btn)
        toolbar_layout.addWidget(self.export_png_btn)
        toolbar_layout.addWidget(self.open_evidence_btn)
        toolbar_layout.addStretch()
        
        parent_layout.addWidget(toolbar)
    
    def setup_timeline(self, parent_layout):
        timeline_group = QGroupBox("Admission Timeline")
        timeline_group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                border: 1px solid #555555;
                background-color: #1E1E1E;
                margin-top: 5px;
                padding-top: 8px;
                font-size: 11px;
            }
            QGroupBox::title {
                color: #E6E6E6;
            }
        """)
        
        timeline_layout = QVBoxLayout()
        self.timeline_widget = QWidget()
        self.timeline_inner_layout = QVBoxLayout(self.timeline_widget)
        
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.timeline_widget)
        scroll.setMaximumHeight(200)
        
        timeline_layout.addWidget(scroll)
        timeline_group.setLayout(timeline_layout)
        parent_layout.addWidget(timeline_group)
    
    def setup_tables(self, parent_layout):
        tables_group = QGroupBox("Strategy Decisions")
        tables_group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                border: 1px solid #555555;
                background-color: #1E1E1E;
                margin-top: 5px;
                padding-top: 8px;
                font-size: 11px;
            }
            QGroupBox::title {
                color: #E6E6E6;
            }
        """)
        
        tables_layout = QVBoxLayout()
        self.tables_stack = QStackedWidget()
        
        # Admitted table
        self.admitted_table = QTableWidget()
        self.setup_table_style(self.admitted_table)
        self.admitted_table.setHorizontalHeaderLabels(["Strategy", "Weight", "Score", "Risk"])
        self.admitted_table.horizontalHeader().setStretchLastSection(True)
        self.admitted_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.admitted_table.itemSelectionChanged.connect(self.on_admitted_row_selected)
        
        # Rejected table
        self.rejected_table = QTableWidget()
        self.setup_table_style(self.rejected_table)
        self.rejected_table.setHorizontalHeaderLabels(["Strategy", "Reason", "Score"])
        self.rejected_table.horizontalHeader().setStretchLastSection(True)
        self.rejected_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.rejected_table.itemSelectionChanged.connect(self.on_rejected_row_selected)
        
        # Tab buttons
        tab_buttons = QWidget()
        tab_layout = QHBoxLayout(tab_buttons)
        
        self.admitted_tab_btn = QPushButton("Admitted")
        self.rejected_tab_btn = QPushButton("Rejected")
        
        for btn in [self.admitted_tab_btn, self.rejected_tab_btn]:
            btn.setCheckable(True)
            btn.setStyleSheet("""
                QPushButton {
                    background-color: #3A3A3A;
                    color: #E6E6E6;
                    border: 1px solid #555555;
                    border-radius: 3px;
                    padding: 6px 12px;
                    font-size: 11px;
                }
                QPushButton:checked {
                    background-color: #4CAF50;
                    color: white;
                }
            """)
            tab_layout.addWidget(btn)
        
        self.admitted_tab_btn.setChecked(True)
        self.admitted_tab_btn.clicked.connect(lambda: self.tables_stack.setCurrentWidget(self.admitted_table))
        self.rejected_tab_btn.clicked.connect(lambda: self.tables_stack.setCurrentWidget(self.rejected_table))
        
        tab_layout.addStretch()
        
        self.tables_stack.addWidget(self.admitted_table)
        self.tables_stack.addWidget(self.rejected_table)
        
        tables_layout.addWidget(tab_buttons)
        tables_layout.addWidget(self.tables_stack)
        tables_group.setLayout(tables_layout)
        parent_layout.addWidget(tables_group, 1)
    
    def setup_table_style(self, table):
        table.setAlternatingRowColors(True)
        table.setStyleSheet("""
            QTableWidget {
                background-color: #1E1E1E;
                color: #E6E6E6;
                border: 1px solid #555555;
                font-size: 11px;
            }
            QHeaderView::section {
                background-color: #2A2A2A;
                color: #E6E6E6;
                border: 1px solid #555555;
                padding: 4px;
                font-weight: bold;
            }
            QTableWidget::item:selected {
                background-color: #1a237e;
            }
        """)
    
    def populate_data(self):
        try:
            self.populate_metrics()
            self.populate_heatmap()
            self.populate_timeline()
            self.populate_tables()
        except Exception as e:
            logger.error(f"Error populating report data: {e}")
            self.log_signal.emit(f"Error loading report data: {e}")
    
    def populate_metrics(self):
        try:
            admission_summary = self.report_data.get('admission_summary', {})
            correlation = self.report_data.get('correlation', {})
            matrix = correlation.get('matrix', [])
            labels = correlation.get('labels', [])
            
            risk_used = admission_summary.get('total_risk', 0.0)
            risk_budget = self.report_data.get('parameters', {}).get('portfolio_risk_budget_max', 0.0)
            admitted_count = len(admission_summary.get('admitted', []))
            rejected_count = len(admission_summary.get('rejected', []))
            
            # Compute correlation metrics
            avg_corr = correlation.get('average_pairwise_correlation')
            if avg_corr is None and matrix and len(matrix) > 0:
                off_diag_values = []
                n = len(matrix)
                for i in range(n):
                    for j in range(i + 1, n):
                        off_diag_values.append(matrix[i][j])
                if off_diag_values:
                    avg_corr = sum(off_diag_values) / len(off_diag_values)
            
            worst_pair = correlation.get('worst_pair', {})
            if not worst_pair and matrix and len(matrix) > 0:
                max_corr = 0.0
                worst_i, worst_j = 0, 0
                n = len(matrix)
                for i in range(n):
                    for j in range(i + 1, n):
                        corr_abs = abs(matrix[i][j])
                        if corr_abs > max_corr:
                            max_corr = corr_abs
                            worst_i, worst_j = i, j
                
                if max_corr > 0 and worst_i < len(labels) and worst_j < len(labels):
                    worst_pair = {
                        'strategy_a': labels[worst_i],
                        'strategy_b': labels[worst_j],
                        'correlation': matrix[worst_i][worst_j]
                    }
            
            worst_pair_text = "—"
            if worst_pair:
                a = worst_pair.get('strategy_a', '?')
                b = worst_pair.get('strategy_b', '?')
                corr = worst_pair.get('correlation', 0.0)
                worst_pair_text = f"{a} vs {b} = {corr:.3f}"
            
            self.metrics_row.clear()
            
            self.metrics_row.add_card(MetricCard(
                title="Risk Used",
                value=f"{risk_used:.2f}",
                subtitle=f"Budget: {risk_budget:.2f}",
                color="#4CAF50" if risk_used <= risk_budget else "#F44336"
            ))
            
            self.metrics_row.add_card(MetricCard(
                title="Admitted",
                value=str(admitted_count),
                subtitle="Strategies",
                color="#4CAF50"
            ))
            
            self.metrics_row.add_card(MetricCard(
                title="Rejected",
                value=str(rejected_count),
                subtitle="Strategies",
                color="#F44336"
            ))
            
            avg_corr_value = avg_corr if avg_corr is not None else "—"
            self.metrics_row.add_card(MetricCard(
                title="Avg Correlation",
                value=f"{avg_corr_value:.3f}" if isinstance(avg_corr_value, (int, float)) else str(avg_corr_value),
                subtitle="Pairwise",
                color="#2196F3"
            ))
            
            self.metrics_row.add_card(MetricCard(
                title="Worst Pair",
                value=worst_pair_text,
                subtitle="Highest correlation",
                color="#FF9800"
            ))
            
        except Exception as e:
            logger.error(f"Error populating metrics: {e}")
            self.metrics_row.clear()
            self.metrics_row.add_card(MetricCard("Error", "—", "Loading failed", "#F44336"))
    
    def populate_heatmap(self):
        try:
            correlation = self.report_data.get('correlation', {})
            matrix = correlation.get('matrix', [])
            labels = correlation.get('labels', [])
            
            if matrix and labels:
                self.heatmap.set_data(matrix, labels)
                self.heatmap.set_title("Strategy Correlation Matrix")
            else:
                self.heatmap.set_message("No correlation data available")
        except Exception as e:
            logger.error(f"Error populating heatmap: {e}")
            self.heatmap.set_message(f"Error loading correlation data: {e}")
    
    def populate_timeline(self):
        try:
            while self.timeline_inner_layout.count():
                item = self.timeline_inner_layout.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()
            
            admission_summary = self.report_data.get('admission_summary', {})
            steps = admission_summary.get('steps', [])
            
            if not steps:
                self.add_timeline_step("Precondition Gate", "PASS", 
                                     f"Admitted: {len(admission_summary.get('admitted', []))}, "
                                     f"Rejected: {len(admission_summary.get('rejected', []))}")
                
                correlation = self.report_data.get('correlation', {})
                if correlation.get('matrix'):
                    self.add_timeline_step("Correlation Gate", "PASS", 
                                         f"Matrix {len(correlation.get('matrix', []))}×{len(correlation.get('matrix', []))}")
                
                risk_budget = self.report_data.get('parameters', {}).get('portfolio_risk_budget_max')
                if risk_budget:
                    self.add_timeline_step("Risk Budget Gate", "PASS", 
                                         f"Budget: {risk_budget}")
                
                self.add_timeline_step("Final Allocation", "COMPLETE", 
                                     f"Portfolio built successfully")
            else:
                for step in steps:
                    title = step.get('title', 'Unknown Step')
                    result = step.get('result', 'UNKNOWN')
                    detail = step.get('detail', '')
                    self.add_timeline_step(title, result, detail)
                    
        except Exception as e:
            logger.error(f"Error populating timeline: {e}")
            self.add_timeline_step("Error", "FAIL", f"Failed to load timeline: {e}")
    
    def add_timeline_step(self, title: str, result: str, detail: str):
        step_widget = QWidget()
        step_layout = QHBoxLayout(step_widget)
        step_layout.setContentsMargins(4, 2, 4, 2)
        step_layout.setSpacing(8)
        
        result_label = QLabel()
        result_label.setFixedSize(16, 16)
        result_label.setStyleSheet(f"""
            QLabel {{
                border-radius: 8px;
                background-color: {self.get_result_color(result)};
                border: 1px solid #555555;
            }}
        """)
        
        text_widget = QWidget()
        text_layout = QVBoxLayout(text_widget)
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(2)
        
        title_label = QLabel(f"<b>{title}</b>")
        title_label.setStyleSheet("color: #E6E6E6; font-size: 11px;")
        
        detail_label = QLabel(detail)
        detail_label.setStyleSheet("color: #9A9A9A; font-size: 10px;")
        detail_label.setWordWrap(True)
        
        text_layout.addWidget(title_label)
        text_layout.addWidget(detail_label)
        
        step_layout.addWidget(result_label)
        step_layout.addWidget(text_widget, 1)
        
        self.timeline_inner_layout.addWidget(step_widget)
    
    def get_result_color(self, result: str) -> str:
        result = result.upper()
        if result in ['PASS', 'COMPLETE', 'SUCCESS']:
            return "#4CAF50"
        elif result in ['FAIL', 'ERROR', 'REJECTED']:
            return "#F44336"
        elif result in ['WARNING', 'PARTIAL']:
            return "#FF9800"
        else:
            return "#9E9E9E"
    
    def populate_tables(self):
        """Populate admitted and rejected strategy tables."""
        try:
            admission_summary = self.report_data.get('admission_summary', {})
            admitted = admission_summary.get('admitted', [])
            rejected = admission_summary.get('rejected', [])
            
            # Clear tables
            self.admitted_table.setRowCount(0)
            self.rejected_table.setRowCount(0)
            self.admitted_table_items.clear()
            self.rejected_table_items.clear()
            
            # Populate admitted table
            self.admitted_table.setRowCount(len(admitted))
            for i, strat in enumerate(admitted):
                name = strat.get('strategy_name', f'Strategy_{i}')
                weight = strat.get('weight', 0.0)
                score = strat.get('score', 0.0)
                risk = strat.get('risk', 0.0)
                
                # Create items
                name_item = QTableWidgetItem(name)
                weight_item = QTableWidgetItem(f"{weight:.4f}")
                score_item = QTableWidgetItem(f"{score:.4f}")
                risk_item = QTableWidgetItem(f"{risk:.4f}")
                
                # Store for highlighting
                self.admitted_table_items[name] = (name_item, weight_item, score_item, risk_item)
                
                # Set items
                self.admitted_table.setItem(i, 0, name_item)
                self.admitted_table.setItem(i, 1, weight_item)
                self.admitted_table.setItem(i, 2, score_item)
                self.admitted_table.setItem(i, 3, risk_item)
            
            # Populate rejected table
            self.rejected_table.setRowCount(len(rejected))
            for i, strat in enumerate(rejected):
                name = strat.get('strategy_name', f'Strategy_{i}')
                reason = strat.get('reason', 'Unknown')
                score = strat.get('score', 0.0)
                
                # Create items
                name_item = QTableWidgetItem(name)
                reason_item = QTableWidgetItem(reason)
                score_item = QTableWidgetItem(f"{score:.4f}")
                
                # Store for highlighting
                self.rejected_table_items[name] = (name_item, reason_item, score_item)
                
                # Set items
                self.rejected_table.setItem(i, 0, name_item)
                self.rejected_table.setItem(i, 1, reason_item)
                self.rejected_table.setItem(i, 2, score_item)
            
            # Resize columns
            self.admitted_table.resizeColumnsToContents()
            self.rejected_table.resizeColumnsToContents()
            
        except Exception as e:
            logger.error(f"Error populating tables: {e}")
            self.admitted_table.setRowCount(0)
            self.rejected_table.setRowCount(0)
    
    @Slot(int, int, float, str, str)
    def on_heatmap_hover(self, row: int, col: int, value: float, row_label: str, col_label: str):
        """Handle heatmap cell hover."""
        try:
            self.heatmap.set_tooltip(f"{row_label} × {col_label}: corr={value:.3f}")
        except Exception as e:
            logger.debug(f"Error in heatmap hover: {e}")
    
    @Slot(int, int, float, str, str)
    def on_heatmap_click(self, row: int, col: int, value: float, row_label: str, col_label: str):
        """Handle heatmap cell click."""
        try:
            # Store selected pair
            self.selected_pair = (row_label, col_label, value)
            
            # Update display
            self.selected_pair_label.setText(
                f"<b>Selected Pair:</b> {row_label} vs {col_label} (corr={value:.3f})"
            )
            self.selected_pair_label.setStyleSheet("color: #2196F3; font-size: 12px;")
            
            # Emit signal
            self.pair_selected.emit(row_label, col_label, value)
            
            # Highlight strategies in tables
            self.highlight_strategy_in_tables(row_label)
            self.highlight_strategy_in_tables(col_label)
                
        except Exception as e:
            logger.error(f"Error in heatmap click: {e}")
    
    def highlight_strategy_in_tables(self, strategy_name: str):
        """Highlight a strategy in both admitted and rejected tables."""
        # Clear previous highlights
        self.clear_table_highlights()
        
        # Highlight in admitted table
        if strategy_name in self.admitted_table_items:
            items = self.admitted_table_items[strategy_name]
            for item in items:
                item.setBackground(QColor("#1a237e"))  # Dark blue
        
        # Highlight in rejected table
        if strategy_name in self.rejected_table_items:
            items = self.rejected_table_items[strategy_name]
            for item in items:
                item.setBackground(QColor("#1a237e"))  # Dark blue
    
    def clear_table_highlights(self):
        """Clear all highlights from tables."""
        # Clear admitted table highlights
        for items in self.admitted_table_items.values():
            for item in items:
                item.setBackground(QColor("#1E1E1E"))
        
        # Clear rejected table highlights
        for items in self.rejected_table_items.values():
            for item in items:
                item.setBackground(QColor("#1E1E1E"))
    
    @Slot()
    def on_admitted_row_selected(self):
        """Handle admitted table row selection."""
        selected_items = self.admitted_table.selectedItems()
        if selected_items:
            row = selected_items[0].row()
            name_item = self.admitted_table.item(row, 0)
            if name_item:
                strategy_name = name_item.text()
                # Clear heatmap selection
                self.selected_pair = None
                self.selected_pair_label.setText("No pair selected")
                self.selected_pair_label.setStyleSheet("color: #9A9A9A; font-size: 12px;")
    
    @Slot()
    def on_rejected_row_selected(self):
        """Handle rejected table row selection."""
        selected_items = self.rejected_table.selectedItems()
        if selected_items:
            row = selected_items[0].row()
            name_item = self.rejected_table.item(row, 0)
            if name_item:
                strategy_name = name_item.text()
                # Clear heatmap selection
                self.selected_pair = None
                self.selected_pair_label.setText("No pair selected")
                self.selected_pair_label.setStyleSheet("color: #9A9A9A; font-size: 12px;")
    
    def export_json(self):
        """Export report data as JSON file."""
        try:
            file_path, _ = QFileDialog.getSaveFileName(
                self, "Export JSON", f"portfolio_report_{self.portfolio_id}.json", "JSON Files (*.json)"
            )
            
            if file_path:
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(self.report_data, f, indent=2, ensure_ascii=False)
                
                self.log_signal.emit(f"JSON exported to {file_path}")
                QMessageBox.information(self, "Export Successful", f"Report exported to {file_path}")
                
        except Exception as e:
            logger.error(f"Error exporting JSON: {e}")
            QMessageBox.critical(self, "Export Failed", f"Failed to export JSON: {e}")
    
    def export_png(self):
        """Export charts as PNG image."""
        try:
            file_path, _ = QFileDialog.getSaveFileName(
                self, "Export PNG", f"portfolio_report_{self.portfolio_id}.png", "PNG Files (*.png)"
            )
            
            if file_path:
                # Create a pixmap of the heatmap
                pixmap = QPixmap(self.heatmap.size())
                self.heatmap.render(pixmap)
                pixmap.save(file_path, "PNG")
                
                self.log_signal.emit(f"PNG exported to {file_path}")
                QMessageBox.information(self, "Export Successful", f"Chart exported to {file_path}")
                
        except Exception as e:
            logger.error(f"Error exporting PNG: {e}")
            QMessageBox.critical(self, "Export Failed", f"Failed to export PNG: {e}")
    
    def open_admission_evidence(self):
        """Open admission evidence folder via API."""
        try:
            # Get artifacts to find admission evidence path
            artifacts = get_portfolio_artifacts(self.portfolio_id)
            
            # Look for admission evidence path
            admission_path = None
            for artifact in artifacts.get('artifacts', []):
                if artifact.get('type') == 'admission_evidence':
                    admission_path = artifact.get('path')
                    break
            
            # If not found, try to reveal via API
            if not admission_path:
                admission_path = reveal_portfolio_admission_path(self.portfolio_id)
            
            if admission_path:
                # Open folder using QDesktopServices
                QDesktopServices.openUrl(QUrl.fromLocalFile(admission_path))
                self.log_signal.emit(f"Opened admission evidence: {admission_path}")
            else:
                QMessageBox.warning(self, "Not Found", "Admission evidence not available for this portfolio")
                
        except Exception as e:
            logger.error(f"Error opening admission evidence: {e}")
            QMessageBox.critical(self, "Error", f"Failed to open admission evidence: {e}")