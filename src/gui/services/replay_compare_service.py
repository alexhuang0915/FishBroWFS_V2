"""
Replay/Compare Service v1 - Desktop UI hook for deployment bundle comparison.

Provides a simple UI integration for the replay/compare functionality:
- Integration with existing AnalysisDrawerWidget
- Context menu actions for comparing deployment bundles
- Read-only audit diff display
- Hybrid BC v1.1 compliant (no metric leakage)

This service is optional and can be used by desktop UI components to provide
replay/compare functionality without requiring CLI usage.
"""

import logging
from pathlib import Path
from typing import Optional, Dict, Any, List
from dataclasses import dataclass

from PySide6.QtCore import Signal, QObject, Slot
from PySide6.QtWidgets import QMessageBox, QFileDialog, QWidget
from gui.services.action_router_service import get_action_router_service

from core.deployment.bundle_resolver import BundleResolver
from core.deployment.diff_engine import DiffEngine, CompareReportV1
from core.paths import get_outputs_root

logger = logging.getLogger(__name__)


@dataclass
class CompareResult:
    """Result of a deployment bundle comparison."""
    success: bool
    report: Optional[CompareReportV1] = None
    error_message: Optional[str] = None
    bundle_a_path: Optional[Path] = None
    bundle_b_path: Optional[Path] = None


class ReplayCompareService(QObject):
    """
    Service for replay/compare functionality with desktop UI integration.
    
    Provides:
    - Bundle selection dialogs
    - Comparison execution
    - Result display integration
    - Evidence generation
    """
    
    # Signals
    comparison_started = Signal(str, str)  # bundle_a, bundle_b
    comparison_completed = Signal(CompareResult)
    comparison_failed = Signal(str)  # error message
    
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.parent_widget = parent
        self.outputs_root = get_outputs_root()
        self.bundle_resolver = BundleResolver(outputs_root=self.outputs_root)
        self.diff_engine = DiffEngine(outputs_root=self.outputs_root)
        
        logger.info("ReplayCompareService initialized")
    
    @Slot()
    def open_compare_dialog(self):
        """Open a dialog to select two deployment bundles for comparison."""
        if not self.parent_widget:
            logger.error("No parent widget for dialog")
            return
        
        # Select first bundle
        bundle_a_path = self._select_deployment_bundle("Select first deployment bundle")
        if not bundle_a_path:
            return
        
        # Select second bundle
        bundle_b_path = self._select_deployment_bundle("Select second deployment bundle")
        if not bundle_b_path:
            return
        
        # Compare the bundles
        self.compare_bundles(bundle_a_path, bundle_b_path)
    
    @Slot()
    def compare_with_latest(self, bundle_path: Path):
        """Compare a deployment bundle with the latest bundle for the same job."""
        if not bundle_path.exists():
            self._show_error(f"Bundle not found: {bundle_path}")
            return
        
        # Resolve the bundle to get job ID
        resolution = self.bundle_resolver.resolve_bundle(bundle_path)
        if not resolution.is_valid or not resolution.manifest:
            self._show_error(f"Invalid bundle: {bundle_path}")
            return
        
        job_id = resolution.manifest.job_id
        
        # Find all deployment bundles for this job
        deployment_dirs = self.bundle_resolver.find_deployment_bundles(job_id)
        if len(deployment_dirs) < 2:
            self._show_error(f"Only {len(deployment_dirs)} deployment bundle(s) found for job {job_id}")
            return
        
        # Find the latest bundle (excluding the current one)
        deployment_dirs.sort(key=lambda d: d.stat().st_mtime, reverse=True)
        
        # Find a different bundle
        latest_bundle = None
        for deployment_dir in deployment_dirs:
            if deployment_dir != bundle_path:
                latest_bundle = deployment_dir
                break
        
        if not latest_bundle:
            self._show_error(f"No other deployment bundle found for job {job_id}")
            return
        
        # Compare with latest
        self.compare_bundles(bundle_path, latest_bundle)
    
    @Slot()
    def compare_bundles(self, bundle_a_path: Path, bundle_b_path: Path):
        """Compare two deployment bundles and show results."""
        # Validate paths
        if not bundle_a_path.exists():
            self._show_error(f"Bundle A not found: {bundle_a_path}")
            return
        
        if not bundle_b_path.exists():
            self._show_error(f"Bundle B not found: {bundle_b_path}")
            return
        
        # Emit signal
        self.comparison_started.emit(str(bundle_a_path), str(bundle_b_path))
        
        try:
            # Generate diff report
            report = self.diff_engine.compare(
                bundle_a_path,
                bundle_b_path,
                output_dir=None,  # Use default evidence location
                redact_metrics=True  # Hybrid BC v1.1 compliance
            )
            
            # Create result
            result = CompareResult(
                success=True,
                report=report,
                bundle_a_path=bundle_a_path,
                bundle_b_path=bundle_b_path
            )
            
            # Emit completion signal
            self.comparison_completed.emit(result)
            
            # Show results dialog
            self._show_comparison_results(result)
            
        except Exception as e:
            error_msg = f"Comparison failed: {str(e)}"
            logger.exception(error_msg)
            self.comparison_failed.emit(error_msg)
            self._show_error(error_msg)
    
    @Slot()
    def show_bundle_info(self, bundle_path: Path):
        """Show information about a deployment bundle."""
        if not bundle_path.exists():
            self._show_error(f"Bundle not found: {bundle_path}")
            return
        
        try:
            resolution = self.bundle_resolver.resolve_bundle(bundle_path)
            
            # Create info message
            if resolution.is_valid and resolution.manifest:
                manifest = resolution.manifest
                info_text = f"""
                <b>Deployment Bundle Information</b>
                
                <b>Path:</b> {bundle_path}
                <b>Deployment ID:</b> {manifest.deployment_id}
                <b>Job ID:</b> {manifest.job_id}
                <b>Created:</b> {manifest.created_at}
                <b>Created by:</b> {manifest.created_by}
                <b>Deployment target:</b> {manifest.deployment_target}
                <b>Artifact count:</b> {manifest.artifact_count}
                
                <b>Key artifacts:</b>
                • Gate Summary: {bool(manifest.gate_summary)}
                • Strategy Report: {bool(manifest.strategy_report)}
                • Portfolio Config: {bool(manifest.portfolio_config)}
                • Admission Report: {bool(manifest.admission_report)}
                • Config Snapshot: {bool(manifest.config_snapshot)}
                • Input Manifest: {bool(manifest.input_manifest)}
                
                <b>Validation:</b> {"✓ Valid" if resolution.is_valid else "✗ Invalid"}
                """
                
                if resolution.validation_errors:
                    info_text += f"\n<b>Validation errors:</b>\n"
                    for error in resolution.validation_errors:
                        info_text += f"• {error}\n"
            else:
                info_text = f"""
                <b>Deployment Bundle Information</b>
                
                <b>Path:</b> {bundle_path}
                <b>Status:</b> Invalid
                
                <b>Validation errors:</b>
                """
                for error in resolution.validation_errors:
                    info_text += f"• {error}\n"
            
            # Show dialog
            QMessageBox.information(
                self.parent_widget,
                "Deployment Bundle Info",
                info_text,
                QMessageBox.StandardButton.Ok
            )
            
        except Exception as e:
            self._show_error(f"Failed to show bundle info: {str(e)}")
    
    @Slot()
    def list_bundles_for_job(self, job_id: str):
        """List deployment bundles for a job and show in dialog."""
        try:
            deployment_dirs = self.bundle_resolver.find_deployment_bundles(job_id)
            
            if not deployment_dirs:
                QMessageBox.information(
                    self.parent_widget,
                    "Deployment Bundles",
                    f"No deployment bundles found for job: {job_id}",
                    QMessageBox.StandardButton.Ok
                )
                return
            
            # Create list text
            list_text = f"<b>Deployment bundles for job: {job_id}</b>\n\n"
            
            for i, deployment_dir in enumerate(deployment_dirs):
                resolution = self.bundle_resolver.resolve_bundle(deployment_dir)
                
                if resolution.is_valid and resolution.manifest:
                    manifest = resolution.manifest
                    list_text += f"""
                    <b>{i+1}. {deployment_dir.name}</b>
                    • Deployment ID: {manifest.deployment_id}
                    • Created: {manifest.created_at}
                    • Artifacts: {manifest.artifact_count}
                    • Path: {deployment_dir}
                    """
                else:
                    list_text += f"""
                    <b>{i+1}. {deployment_dir.name}</b>
                    • Status: Invalid
                    • Path: {deployment_dir}
                    """
                
                list_text += "\n"
            
            # Show dialog
            QMessageBox.information(
                self.parent_widget,
                "Deployment Bundles",
                list_text,
                QMessageBox.StandardButton.Ok
            )
            
        except Exception as e:
            self._show_error(f"Failed to list bundles: {str(e)}")
    
    # ----------------------------------------------------------------------
    # Helper methods
    # ----------------------------------------------------------------------
    
    def _select_deployment_bundle(self, title: str) -> Optional[Path]:
        """Open a directory dialog to select a deployment bundle."""
        if not self.parent_widget:
            return None
        
        # Start in outputs directory
        start_dir = str(self.outputs_root)
        
        # Open directory dialog
        selected_dir = QFileDialog.getExistingDirectory(
            self.parent_widget,
            title,
            start_dir,
            QFileDialog.Option.ShowDirsOnly
        )
        
        if not selected_dir:
            return None
        
        return Path(selected_dir)
    
    def _show_comparison_results(self, result: CompareResult):
        """Show comparison results in a dialog."""
        if not self.parent_widget or not result.report:
            return
        
        report = result.report
        
        # Create results text
        results_text = f"""
        <b>Deployment Bundle Comparison Results</b>
        
        <b>Bundle A:</b> {result.bundle_a_path.name}
        • Deployment ID: {report.bundle_a.deployment_id}
        • Job ID: {report.bundle_a.job_id}
        • Valid: {"✓" if report.bundle_a.is_valid else "✗"}
        
        <b>Bundle B:</b> {result.bundle_b_path.name}
        • Deployment ID: {report.bundle_b.deployment_id}
        • Job ID: {report.bundle_b.job_id}
        • Valid: {"✓" if report.bundle_b.is_valid else "✗"}
        
        <b>Comparison:</b>
        • Same job: {"✓" if report.comparison.same_job else "✗"}
        • Same deployment: {"✓" if report.comparison.same_deployment else "✗"}
        • Artifact count difference: {report.comparison.artifact_count_diff}
        
        <b>Gate Summary Changes:</b>
        """
        
        if report.comparison.gate_summary_diff:
            gate_diff = report.comparison.gate_summary_diff
            results_text += f"""
            • Overall status changed: {"✓" if gate_diff.overall_status_changed else "✗"}
            • Overall status A: {gate_diff.overall_status_a}
            • Overall status B: {gate_diff.overall_status_b}
            • Gate count difference: {gate_diff.gate_count_diff}
            """
            
            if gate_diff.gate_status_changes:
                results_text += f"""
                • Gate status changes: {len(gate_diff.gate_status_changes)}
                """
        else:
            results_text += "• No gate summary changes"
        
        results_text += f"""
        
        <b>Report:</b>
        • Generated at: {report.generated_at}
        • Report ID: {report.report_id}
        • Evidence saved to: {report.evidence_path}
        """
        
        # Show dialog
        QMessageBox.information(
            self.parent_widget,
            "Comparison Results",
            results_text,
            QMessageBox.StandardButton.Ok
        )
        
        # Offer to open evidence directory
        if report.evidence_path and report.evidence_path.exists():
            reply = QMessageBox.question(
                self.parent_widget,
                "Open Evidence",
                "Would you like to open the evidence directory?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes
            )
            
            if reply == QMessageBox.StandardButton.Yes:
                # Open directory via ActionRouterService
                router = get_action_router_service()
                router.handle_action(f"file://{report.evidence_path}")
    
    def _show_error(self, message: str):
        """Show an error message dialog."""
        if not self.parent_widget:
            logger.error(message)
            return
        
        QMessageBox.critical(
            self.parent_widget,
            "Error",
            message,
            QMessageBox.StandardButton.Ok
        )
    
    def _show_info(self, message: str):
        """Show an info message dialog."""
        if not self.parent_widget:
            logger.info(message)
            return
        
        QMessageBox.information(
            self.parent_widget,
            "Information",
            message,
            QMessageBox.StandardButton.Ok
        )


# ----------------------------------------------------------------------
# Integration with AnalysisDrawerWidget
# ----------------------------------------------------------------------

def add_compare_context_menu(analysis_drawer, job_id: str):
    """
    Add compare context menu to AnalysisDrawerWidget.
    
    This function can be called from AnalysisDrawerWidget to add
    replay/compare functionality to its context menus.
    """
    # Import here to avoid circular imports
    from gui.desktop.widgets.analysis_drawer_widget import AnalysisDrawerWidget
    
    if not isinstance(analysis_drawer, AnalysisDrawerWidget):
        return
    
    # Create service instance
    service = ReplayCompareService(parent=analysis_drawer)
    
    # Add compare action to chart context menu
    def add_compare_action_to_chart_menu():
        """Add compare action to chart context menu."""
        # This would be called from within AnalysisDrawerWidget
        # to add a "Compare Deployment Bundles" action to the chart menu
        pass
    
    # Add compare action to gate summary card menu
    def add_compare_action_to_gate_menu():
        """Add compare action to gate summary card menu."""
        # This would be called from within AnalysisDrawerWidget
        # to add a "Compare with Other Deployment" action to the gate card menu
        pass
    
    # Return the service for external use
    return service


# ----------------------------------------------------------------------
# Simple standalone UI component
# ----------------------------------------------------------------------

class CompareDeploymentDialog(QWidget):
    """
    Simple dialog for comparing deployment bundles.
    
    This is a minimal UI component that can be used standalone
    or integrated into larger desktop applications.
    """
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.service = ReplayCompareService(parent=self)
        self.setup_ui()
    
    def setup_ui(self):
        """Setup the UI components."""
        from PySide6.QtWidgets import (
            QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
            QLineEdit, QGroupBox, QTextEdit, QFileDialog
        )
        from PySide6.QtCore import Qt
        
        layout = QVBoxLayout(self)
        
        # Title
        title_label = QLabel("Replay/Compare Deployment Bundles")
        title_label.setStyleSheet("font-weight: bold; font-size: 16px;")
        layout.addWidget(title_label)
        
        # Bundle selection group
        selection_group = QGroupBox("Bundle Selection")
        selection_layout = QVBoxLayout()
        
        # Bundle A
        bundle_a_layout = QHBoxLayout()
        bundle_a_layout.addWidget(QLabel("Bundle A:"))
        self.bundle_a_edit = QLineEdit()
        self.bundle_a_edit.setPlaceholderText("Select first deployment bundle...")
        bundle_a_layout.addWidget(self.bundle_a_edit)
        
        browse_a_btn = QPushButton("Browse...")
        browse_a_btn.clicked.connect(self._browse_bundle_a)
        bundle_a_layout.addWidget(browse_a_btn)
        
        selection_layout.addLayout(bundle_a_layout)
        
        # Bundle B
        bundle_b_layout = QHBoxLayout()
        bundle_b_layout.addWidget(QLabel("Bundle B:"))
        self.bundle_b_edit = QLineEdit()
        self.bundle_b_edit.setPlaceholderText("Select second deployment bundle...")
        bundle_b_layout.addWidget(self.bundle_b_edit)
        
        browse_b_btn = QPushButton("Browse...")
        browse_b_btn.clicked.connect(self._browse_bundle_b)
        bundle_b_layout.addWidget(browse_b_btn)
        
        selection_group.setLayout(selection_layout)
        layout.addWidget(selection_group)
        
        # Compare button
        compare_btn = QPushButton("Compare Bundles")
        compare_btn.setStyleSheet("font-weight: bold; padding: 8px;")
        compare_btn.clicked.connect(self._compare_bundles)
        layout.addWidget(compare_btn)
        
        # Results area
        results_group = QGroupBox("Comparison Results")
        results_layout = QVBoxLayout()
        
        self.results_text = QTextEdit()
        self.results_text.setReadOnly(True)
        self.results_text.setMinimumHeight(200)
        results_layout.addWidget(self.results_text)
        
        results_group.setLayout(results_layout)
        layout.addWidget(results_group)
        
        # Connect service signals
        self.service.comparison_started.connect(self._on_comparison_started)
        self.service.comparison_completed.connect(self._on_comparison_completed)
        self.service.comparison_failed.connect(self._on_comparison_failed)
        
        # Add stretch at bottom
        layout.addStretch()
    
    def _browse_bundle_a(self):
        """Browse for bundle A."""
        bundle_path = self.service._select_deployment_bundle("Select first deployment bundle")
        if bundle_path:
            self.bundle_a_edit.setText(str(bundle_path))
    
    def _browse_bundle_b(self):
        """Browse for bundle B."""
        bundle_path = self.service._select_deployment_bundle("Select second deployment bundle")
        if bundle_path:
            self.bundle_b_edit.setText(str(bundle_path))
    
    def _compare_bundles(self):
        """Compare the selected bundles."""
        bundle_a_path = Path(self.bundle_a_edit.text().strip())
        bundle_b_path = Path(self.bundle_b_edit.text().strip())
        
        if not bundle_a_path or not bundle_a_path.exists():
            self.results_text.setText("Error: Bundle A path is invalid or does not exist.")
            return
        
        if not bundle_b_path or not bundle_b_path.exists():
            self.results_text.setText("Error: Bundle B path is invalid or does not exist.")
            return
        
        # Clear results
        self.results_text.setText("Comparing bundles...")
        
        # Start comparison
        self.service.compare_bundles(bundle_a_path, bundle_b_path)
    
    def _on_comparison_started(self, bundle_a: str, bundle_b: str):
        """Handle comparison started signal."""
        self.results_text.setText(f"Comparing:\n• {bundle_a}\n• {bundle_b}\n\nProcessing...")
    
    def _on_comparison_completed(self, result: CompareResult):
        """Handle comparison completed signal."""
        if result.success and result.report:
            report = result.report
            
            # Format results
            results_text = f"""
            <b>Comparison Completed Successfully</b>
            
            <b>Bundle A:</b> {result.bundle_a_path.name}
            • Deployment ID: {report.bundle_a.deployment_id}
            • Job ID: {report.bundle_a.job_id}
            • Valid: {"✓" if report.bundle_a.is_valid else "✗"}
            
            <b>Bundle B:</b> {result.bundle_b_path.name}
            • Deployment ID: {report.bundle_b.deployment_id}
            • Job ID: {report.bundle_b.job_id}
            • Valid: {"✓" if report.bundle_b.is_valid else "✗"}
            
            <b>Comparison:</b>
            • Same job: {"✓" if report.comparison.same_job else "✗"}
            • Same deployment: {"✓" if report.comparison.same_deployment else "✗"}
            • Artifact count difference: {report.comparison.artifact_count_diff}
            """
            
            if report.comparison.gate_summary_diff:
                gate_diff = report.comparison.gate_summary_diff
                results_text += f"""
                <b>Gate Summary Changes:</b>
                • Overall status changed: {"✓" if gate_diff.overall_status_changed else "✗"}
                • Overall status A: {gate_diff.overall_status_a}
                • Overall status B: {gate_diff.overall_status_b}
                • Gate count difference: {gate_diff.gate_count_diff}
                """
                
                if gate_diff.gate_status_changes:
                    results_text += f"""
                    • Gate status changes: {len(gate_diff.gate_status_changes)}
                    """
            
            results_text += f"""
            
            <b>Report:</b>
            • Generated at: {report.generated_at}
            • Report ID: {report.report_id}
            • Evidence saved to: {report.evidence_path}
            """
            
            self.results_text.setText(results_text)
        else:
            self.results_text.setText(f"Comparison failed: {result.error_message}")
    
    def _on_comparison_failed(self, error_message: str):
        """Handle comparison failed signal."""
        self.results_text.setText(f"<b>Error:</b> {error_message}")