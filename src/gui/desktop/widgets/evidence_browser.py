"""
Evidence Browser Dialog – Tree‑view navigation of job evidence files.

Provides a categorized view of all evidence files (manifest.json, runtime_metrics.json,
policy_check.json, reports, logs, etc.) with click‑to‑open functionality.

Design principles:
- Evidence‑first: show files before logs.
- Categorized: group by semantic type.
- Actionable: each file can be opened, viewed, or its path copied.
"""

import logging
from typing import Optional, List
from pathlib import Path

from PySide6.QtCore import Qt, Signal, Slot  # type: ignore
from PySide6.QtWidgets import (  # type: ignore
    QDialog, QVBoxLayout, QHBoxLayout, QTreeWidget, QTreeWidgetItem,
    QPushButton, QLabel, QSplitter, QTextEdit, QMessageBox,
    QFileDialog, QMenu, QApplication
)
from PySide6.QtGui import QAction, QDesktopServices, QFont  # type: ignore
from PySide6.QtCore import QUrl  # type: ignore

from ..services.evidence_locator import list_evidence_files, EvidenceFile, get_evidence_root

logger = logging.getLogger(__name__)


class EvidenceBrowserDialog(QDialog):
    """Dialog that displays evidence files in a tree view."""
    
    def __init__(self, job_id: str, parent=None):
        super().__init__(parent)
        self.setProperty('job_id', job_id)
        self.evidence_files: List[EvidenceFile] = []
        self.setup_ui()
        self.load_evidence()
    
    def setup_ui(self):
        """Initialize the UI components."""
        self.setWindowTitle(f"Evidence Browser – {self.job_id[:8]}...")
        self.setMinimumSize(800, 600)
        
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(8)
        
        # Header with job info
        header_layout = QHBoxLayout()
self.setProperty('job_label', QLabel(f"Job: {self.job_id}"))
        self.job_label.setStyleSheet("font-weight: bold; color: #E6E6E6;")
        header_layout.addWidget(self.job_label)
        
self.setProperty('evidence_root_label', QLabel(""))
        self.evidence_root_label.setStyleSheet("color: #9e9e9e; font-size: 10px;")
        header_layout.addStretch()
        header_layout.addWidget(self.evidence_root_label)
        
        main_layout.addLayout(header_layout)
        
        # Splitter for tree and preview
        splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # Left panel: tree view
self.setProperty('tree', QTreeWidget())
        self.tree.setHeaderLabels(["Evidence Files", "Size", "Type"])
        self.tree.setColumnWidth(0, 300)
        self.tree.setColumnWidth(1, 80)
        self.tree.setColumnWidth(2, 100)
        self.tree.setStyleSheet("""
            QTreeWidget {
                background-color: #1E1E1E;
                color: #E6E6E6;
                font-size: 11px;
                border: 1px solid #333333;
            }
            QTreeWidget::item {
                padding: 4px;
            }
            QTreeWidget::item:selected {
                background-color: #2a2a2a;
                color: #FFFFFF;
            }
        """)
        self.tree.itemDoubleClicked.connect(self.on_item_double_clicked)
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self.show_context_menu)
        
        # Right panel: preview / details
self.setProperty('preview_text', QTextEdit())
        self.preview_text.setReadOnly(True)
        self.preview_text.setPlaceholderText("Select a file to preview its content...")
        self.preview_text.setStyleSheet("""
            QTextEdit {
                background-color: #1E1E1E;
                color: #E6E6E6;
                font-family: monospace;
                font-size: 11px;
                border: 1px solid #333333;
            }
        """)
        
        splitter.addWidget(self.tree)
        splitter.addWidget(self.preview_text)
        splitter.setSizes([400, 400])
        
        main_layout.addWidget(splitter)
        
        # Button bar
        button_layout = QHBoxLayout()
        
self.setProperty('open_file_btn', QPushButton("Open File"))
        self.open_file_btn.setToolTip("Open selected file with default application")
        self.open_file_btn.clicked.connect(self.open_selected_file)
        self.open_file_btn.setEnabled(False)
        
self.setProperty('open_folder_btn', QPushButton("Open Folder"))
        self.open_folder_btn.setToolTip("Open evidence root folder in file explorer")
        self.open_folder_btn.clicked.connect(self.open_evidence_folder)
        
self.setProperty('copy_path_btn', QPushButton("Copy Path"))
        self.copy_path_btn.setToolTip("Copy file path to clipboard")
        self.copy_path_btn.clicked.connect(self.copy_selected_path)
        self.copy_path_btn.setEnabled(False)
        
self.setProperty('refresh_btn', QPushButton("Refresh"))
        self.refresh_btn.setToolTip("Reload evidence files")
        self.refresh_btn.clicked.connect(self.load_evidence)
        
        button_layout.addWidget(self.open_file_btn)
        button_layout.addWidget(self.open_folder_btn)
        button_layout.addWidget(self.copy_path_btn)
        button_layout.addWidget(self.refresh_btn)
        button_layout.addStretch()
        
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        button_layout.addWidget(close_btn)
        
        main_layout.addLayout(button_layout)
        
        # Connect selection change
        self.tree.itemSelectionChanged.connect(self.on_selection_changed)
    
    def load_evidence(self):
        """Load evidence files and populate the tree."""
        self.tree.clear()
self.setProperty('evidence_files', list_evidence_files(self.job_id))
        
        # Update root label
        root = get_evidence_root(self.job_id)
        if root:
            self.evidence_root_label.setText(f"Evidence root: {root}")
        else:
            self.evidence_root_label.setText("Evidence root: not available")
        
        if not self.evidence_files:
            no_files_item = QTreeWidgetItem(self.tree, ["No evidence files found"])
            no_files_item.setFirstColumnSpanned(True)
            return
        
        # Group by category
        categories = {}
        for file in self.evidence_files:
            categories.setdefault(file.category, []).append(file)
        
        # Create category items
        category_order = ["manifest", "metrics", "policy", "report", "log", "other"]
        for category in category_order:
            if category not in categories:
                continue
            
            # Create category item
            cat_item = QTreeWidgetItem(self.tree)
            cat_item.setText(0, self._category_display_name(category))
            # Icon omitted (we use emoji in text)
            cat_item.setData(0, Qt.ItemDataRole.UserRole, None)  # No file attached
            cat_item.setExpanded(True)
            
            # Add files under category
            for file in categories[category]:
                file_item = QTreeWidgetItem(cat_item)
                file_item.setText(0, f"{file.icon} {file.display_name}")
                file_item.setText(1, self._format_size(file.size_bytes))
                file_item.setText(2, file.category)
                file_item.setData(0, Qt.ItemDataRole.UserRole, file)
                file_item.setToolTip(0, file.description)
                file_item.setToolTip(1, f"{file.size_bytes} bytes" if file.size_bytes else "Unknown size")
                file_item.setToolTip(2, file.relative_path)
        
        # Expand all categories
        self.tree.expandAll()
    
    def _category_display_name(self, category: str) -> str:
        """Convert category slug to display name."""
        names = {
            "manifest": "Manifest",
            "metrics": "Runtime Metrics",
            "policy": "Policy Check",
            "report": "Reports",
            "log": "Logs",
            "other": "Other Artifacts",
        }
        return names.get(category, category.capitalize())
    
    def _category_icon(self, category: str) -> str:
        """Return icon for category (emoji as text)."""
        # Qt doesn't support emoji icons directly; we'll just use text.
        # For simplicity, we'll set icon via setText with emoji.
        # Actually we'll just use text emoji in the label.
        return ""
    
    def _format_size(self, size_bytes: Optional[int]) -> str:
        """Format file size human‑readably."""
        if size_bytes is None:
            return "—"
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f} KB"
        elif size_bytes < 1024 * 1024 * 1024:
            return f"{size_bytes / (1024 * 1024):.1f} MB"
        else:
            return f"{size_bytes / (1024 * 1024 * 1024):.1f} GB"
    
    def on_selection_changed(self):
        """Handle selection change in tree."""
        selected_items = self.tree.selectedItems()
        if not selected_items:
            self.open_file_btn.setEnabled(False)
            self.copy_path_btn.setEnabled(False)
            self.preview_text.clear()
            return
        
        item = selected_items[0]
        file = item.data(0, Qt.ItemDataRole.UserRole)
        if file is None:
            # Category item selected
            self.open_file_btn.setEnabled(False)
            self.copy_path_btn.setEnabled(False)
            self.preview_text.clear()
            return
        
        # Enable buttons
        self.open_file_btn.setEnabled(True)
        self.copy_path_btn.setEnabled(True)
        
        # Preview file content if it's a text file
        self.preview_file(file)
    
    def preview_file(self, file: EvidenceFile):
        """Preview file content in the text edit."""
        # Only preview text files (JSON, log, etc.)
        if file.path.suffix.lower() not in ['.json', '.log', '.txt', '.csv', '.md', '.html']:
            self.preview_text.setPlainText(f"Binary file ({file.size_bytes} bytes)\nPreview not available.")
            return
        
        try:
            content = file.path.read_text(encoding='utf-8', errors='replace')
            # Limit preview size to 100 KB
            if len(content) > 100 * 1024:
                content = content[:100 * 1024] + "\n\n... (truncated)"
            self.preview_text.setPlainText(content)
        except Exception as e:
            self.preview_text.setPlainText(f"Failed to read file: {e}")
    
    def on_item_double_clicked(self, item, column):
        """Handle double‑click on item (open file)."""
        file = item.data(0, Qt.ItemDataRole.UserRole)
        if file:
            self.open_file(file)
    
    def open_selected_file(self):
        """Open the currently selected file."""
        selected_items = self.tree.selectedItems()
        if not selected_items:
            return
        item = selected_items[0]
        file = item.data(0, Qt.ItemDataRole.UserRole)
        if file:
            self.open_file(file)
    
    def open_file(self, file: EvidenceFile):
        """Open file with default application."""
        try:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(file.path)))
        except Exception as e:
            QMessageBox.critical(self, "Open File Error", f"Failed to open file:\n{file.path}\n\n{e}")
    
    def open_evidence_folder(self):
        """Open evidence root folder in file explorer."""
        root = get_evidence_root(self.job_id)
        if root:
            try:
                QDesktopServices.openUrl(QUrl.fromLocalFile(str(root)))
            except Exception as e:
                QMessageBox.critical(self, "Open Folder Error", f"Failed to open folder:\n{root}\n\n{e}")
        else:
            QMessageBox.warning(self, "No Evidence", "Evidence root not available.")
    
    def copy_selected_path(self):
        """Copy selected file path to clipboard."""
        selected_items = self.tree.selectedItems()
        if not selected_items:
            return
        item = selected_items[0]
        file = item.data(0, Qt.ItemDataRole.UserRole)
        if not file:
            return
        
        clipboard = QApplication.clipboard()
        clipboard.setText(str(file.path))
        # Show a brief feedback
        QMessageBox.information(self, "Copied", f"Path copied:\n{file.path}")
    
    def show_context_menu(self, position):
        """Show context menu for tree item."""
        item = self.tree.itemAt(position)
        if not item:
            return
        
        file = item.data(0, Qt.ItemDataRole.UserRole)
        menu = QMenu(self)
        
        if file:
            open_action = QAction("Open File", self)
            open_action.triggered.connect(lambda: self.open_file(file))
            menu.addAction(open_action)
            
            copy_path_action = QAction("Copy Path", self)
            copy_path_action.triggered.connect(lambda: self.copy_path(file))
            menu.addAction(copy_path_action)
            
            menu.addSeparator()
        
        refresh_action = QAction("Refresh", self)
        refresh_action.triggered.connect(self.load_evidence)
        menu.addAction(refresh_action)
        
        menu.exec(self.tree.viewport().mapToGlobal(position))
    
    def copy_path(self, file: EvidenceFile):
        """Copy file path to clipboard."""
        clipboard = QApplication.clipboard()
        clipboard.setText(str(file.path))
        QMessageBox.information(self, "Copied", f"Path copied:\n{file.path}")