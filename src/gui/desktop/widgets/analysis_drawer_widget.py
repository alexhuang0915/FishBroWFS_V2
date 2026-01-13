"""
Analysis Drawer Widget for Hybrid BC v1.1 Shadow Adoption - Layer 3.

Slide-over drawer that hosts existing report widgets (Strategy/Portfolio report).
Lazy-loads analysis content on open.
Auto-closes when selection changes.
"""

from typing import Optional, Any
from PySide6.QtCore import Qt, Signal, QPropertyAnimation, QEasingCurve, QRect
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QScrollArea, QSizePolicy
)
from PySide6.QtGui import QPainter, QBrush, QColor, QPen

from gui.services.hybrid_bc_vms import JobAnalysisVM


class AnalysisDrawerWidget(QWidget):
    """Analysis drawer widget for Hybrid BC Layer 3."""
    
    # Signals
    drawer_closed = Signal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_job_id: Optional[str] = None
        self.current_vm: Optional[JobAnalysisVM] = None
        self.is_open = False
        self.animation = None
        
        # Container for hosted report widget
        self.report_container = None
        self.current_report_widget = None
        
        self.setup_ui()
        self.hide()  # Initially hidden
        
    def setup_ui(self):
        """Initialize UI components."""
        # Make drawer overlay on parent
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # Backdrop (semi-transparent overlay)
        self.backdrop = QFrame()
        self.backdrop.setStyleSheet("""
            QFrame {
                background-color: rgba(0, 0, 0, 0.5);
            }
        """)
        self.backdrop.mousePressEvent = self._on_backdrop_click
        main_layout.addWidget(self.backdrop)
        
        # Drawer content (right side, 85% width)
        drawer_content = QFrame()
        drawer_content.setStyleSheet("""
            QFrame {
                background-color: #1E1E1E;
                border-left: 1px solid #444444;
            }
        """)
        drawer_content.setFixedWidth(int(self.parent().width() * 0.85) if self.parent() else 800)
        
        drawer_layout = QVBoxLayout(drawer_content)
        drawer_layout.setContentsMargins(0, 0, 0, 0)
        drawer_layout.setSpacing(0)
        
        # Drawer header
        header_frame = QFrame()
        header_frame.setStyleSheet("""
            QFrame {
                background-color: #2a2a2a;
                border-bottom: 1px solid #444444;
                padding: 12px;
            }
        """)
        header_layout = QHBoxLayout(header_frame)
        header_layout.setContentsMargins(12, 12, 12, 12)
        
        self.title_label = QLabel("Analysis Drawer")
        self.title_label.setStyleSheet("font-weight: bold; font-size: 16px; color: #E6E6E6;")
        header_layout.addWidget(self.title_label)
        
        header_layout.addStretch()
        
        self.close_btn = QPushButton("×")
        self.close_btn.setFixedSize(32, 32)
        self.close_btn.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: #E6E6E6;
                font-size: 20px;
                font-weight: bold;
                border: none;
            }
            QPushButton:hover {
                background-color: #444444;
                border-radius: 4px;
            }
        """)
        self.close_btn.clicked.connect(self.close_drawer)
        header_layout.addWidget(self.close_btn)
        
        drawer_layout.addWidget(header_frame)
        
        # Scroll area for report content
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setStyleSheet("""
            QScrollArea {
                border: none;
                background-color: #1E1E1E;
            }
            QScrollArea > QWidget > QWidget {
                background-color: #1E1E1E;
            }
        """)
        
        # Container widget for report
        self.report_container = QWidget()
        self.report_container.setStyleSheet("background-color: #1E1E1E;")
        self.report_container_layout = QVBoxLayout(self.report_container)
        self.report_container_layout.setContentsMargins(16, 16, 16, 16)
        
        # Placeholder label (shown when no report loaded)
        self.placeholder_label = QLabel("No analysis content loaded")
        self.placeholder_label.setStyleSheet("color: #9e9e9e; font-size: 14px;")
        self.placeholder_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.report_container_layout.addWidget(self.placeholder_label)
        
        scroll_area.setWidget(self.report_container)
        drawer_layout.addWidget(scroll_area)
        
        main_layout.addWidget(drawer_content, 0, Qt.AlignmentFlag.AlignRight)
        
        # Set drawer to take full height
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
    
    def open_for_job(self, job_id: str, vm: Optional[JobAnalysisVM] = None):
        """Open drawer for a specific job."""
        if self.is_open and self.current_job_id == job_id:
            return  # Already open for this job
        
        self.current_job_id = job_id
        self.current_vm = vm
        
        # Update title
        self.title_label.setText(f"Analysis - {job_id[:8]}...")
        
        # Show drawer with animation
        self.show()
        self.raise_()
        
        # Animate slide-in from right
        if self.parent():
            parent_rect = self.parent().rect()
            self.setGeometry(parent_rect)
            
            # Start off-screen to the right
            start_rect = QRect(parent_rect.width(), 0, parent_rect.width(), parent_rect.height())
            end_rect = parent_rect
            
            self.animation = QPropertyAnimation(self, b"geometry")
            self.animation.setDuration(300)
            self.animation.setEasingCurve(QEasingCurve.Type.OutCubic)
            self.animation.setStartValue(start_rect)
            self.animation.setEndValue(end_rect)
            self.animation.start()
        
        self.is_open = True
        
        # Load analysis content if VM provided
        if vm:
            self._load_analysis_content(vm)
        else:
            # Show loading state
            self.placeholder_label.setText("Loading analysis...")
            # In real implementation, would fetch data asynchronously
    
    def close_drawer(self):
        """Close the drawer with animation."""
        if not self.is_open:
            return
        
        if self.parent() and self.animation:
            parent_rect = self.parent().rect()
            end_rect = QRect(parent_rect.width(), 0, parent_rect.width(), parent_rect.height())
            
            self.animation = QPropertyAnimation(self, b"geometry")
            self.animation.setDuration(300)
            self.animation.setEasingCurve(QEasingCurve.Type.InCubic)
            self.animation.setStartValue(self.geometry())
            self.animation.setEndValue(end_rect)
            self.animation.finished.connect(self._on_animation_finished)
            self.animation.start()
        else:
            self._on_animation_finished()
        
        self.is_open = False
    
    def _on_animation_finished(self):
        """Handle animation finished."""
        self.hide()
        self.clear()
        self.drawer_closed.emit()
    
    def _on_backdrop_click(self, event):
        """Handle backdrop click to close drawer."""
        self.close_drawer()
    
    def _load_analysis_content(self, vm: JobAnalysisVM):
        """Load analysis content from VM."""
        # Clear existing content
        self._clear_report_container()
        
        # Hide placeholder
        self.placeholder_label.hide()
        
        # Determine which report widget to create based on job type or payload
        # For now, we'll create a simple placeholder
        # In real implementation, would instantiate StrategyReportWidget or PortfolioReportWidget
        
        # Create a simple info display for now
        info_label = QLabel(f"Analysis for job: {vm.job_id}")
        info_label.setStyleSheet("color: #E6E6E6; font-size: 14px; margin-bottom: 16px;")
        self.report_container_layout.addWidget(info_label)
        
        # Add payload info if available
        if vm.payload:
            payload_label = QLabel("Payload data available")
            payload_label.setStyleSheet("color: #9e9e9e; font-size: 12px;")
            self.report_container_layout.addWidget(payload_label)
        
        # Add stretch at bottom
        self.report_container_layout.addStretch()
        
        # Store reference to current widget
        self.current_report_widget = info_label
    
    def _clear_report_container(self):
        """Clear all widgets from report container."""
        # Remove all widgets except placeholder
        while self.report_container_layout.count() > 1:  # Keep placeholder
            item = self.report_container_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        # Show placeholder again
        self.placeholder_label.show()
        self.current_report_widget = None
    
    def clear(self):
        """Clear all data and reset to initial state."""
        self.current_job_id = None
        self.current_vm = None
        self._clear_report_container()
        self.title_label.setText("Analysis Drawer")
    
    def resizeEvent(self, event):
        """Handle resize events to maintain proper geometry."""
        super().resizeEvent(event)
        if self.parent() and self.is_open:
            self.setGeometry(self.parent().rect())
    
    def paintEvent(self, event):
        """Paint backdrop blur effect (simplified)."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Draw semi-transparent backdrop
        painter.setBrush(QBrush(QColor(0, 0, 0, 128)))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRect(self.rect())
        
        super().paintEvent(event)