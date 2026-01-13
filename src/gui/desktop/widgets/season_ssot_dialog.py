"""
Season SSOT Dialog - Minimal UI hooks for Season SSOT + Boundary Validator.

Provides basic UI for:
- Creating new seasons with boundary fields
- Listing existing seasons
- Attaching jobs to seasons with boundary validation
- Freezing/archiving seasons
"""

from typing import Optional, List, Dict, Any
import logging

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QWidget, QLabel,
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
    QMessageBox, QTabWidget, QLineEdit, QTextEdit, QFormLayout,
    QGroupBox, QComboBox, QDialogButtonBox, QProgressBar,
)
from PySide6.QtCore import Qt, QTimer, Signal, QThread, QObject
from PySide6.QtGui import QFont

from gui.services.supervisor_client import (
    create_season_ssot,
    list_seasons_ssot,
    get_season_ssot,
    attach_job_to_season_ssot,
    freeze_season_ssot,
    archive_season_ssot,
    analyze_season_ssot,
    admit_candidates_to_season_ssot,
    export_candidates_from_season_ssot,
    SupervisorClientError,
)

logger = logging.getLogger(__name__)


class SeasonSSOTDialog(QDialog):
    """Dialog for Season SSOT operations."""
    
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle("Season SSOT Manager")
        self.setMinimumSize(800, 600)
        
        self._setup_ui()
        self._load_seasons()
    
    def _setup_ui(self):
        """Setup the dialog UI."""
        layout = QVBoxLayout(self)
        
        # Create tab widget
        self.tab_widget = QTabWidget()
        layout.addWidget(self.tab_widget)
        
        # Tab 1: List seasons
        self._setup_list_tab()
        
        # Tab 2: Create season
        self._setup_create_tab()
        
        # Tab 3: Attach job
        self._setup_attach_tab()
        
        # Tab 4: Manage season
        self._setup_manage_tab()
        
        # Tab 5: Season Viewer (P2-B/C/D)
        self._setup_viewer_tab()
        
        # Status bar
        self.status_label = QLabel("Ready")
        self.status_label.setStyleSheet("color: gray; font-style: italic;")
        layout.addWidget(self.status_label)
        
        # Close button
        button_box = QDialogButtonBox(QDialogButtonBox.Close)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
    
    def _setup_list_tab(self):
        """Setup the list seasons tab."""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        # Refresh button
        refresh_layout = QHBoxLayout()
        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self._load_seasons)
        refresh_layout.addWidget(refresh_btn)
        refresh_layout.addStretch()
        layout.addLayout(refresh_layout)
        
        # Seasons table
        self.seasons_table = QTableWidget()
        self.seasons_table.setColumnCount(6)
        self.seasons_table.setHorizontalHeaderLabels([
            "Season ID", "Display Name", "State", "Boundary Match", "Jobs", "Created"
        ])
        self.seasons_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.seasons_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.seasons_table.setSelectionMode(QTableWidget.SingleSelection)
        self.seasons_table.itemSelectionChanged.connect(self._on_season_selected)
        layout.addWidget(self.seasons_table)
        
        # Details group
        details_group = QGroupBox("Season Details")
        details_layout = QFormLayout()
        
        self.detail_id = QLabel()
        self.detail_name = QLabel()
        self.detail_state = QLabel()
        self.detail_boundary = QLabel()
        self.detail_jobs = QLabel()
        self.detail_created = QLabel()
        
        details_layout.addRow("ID:", self.detail_id)
        details_layout.addRow("Display Name:", self.detail_name)
        details_layout.addRow("State:", self.detail_state)
        details_layout.addRow("Boundary:", self.detail_boundary)
        details_layout.addRow("Attached Jobs:", self.detail_jobs)
        details_layout.addRow("Created:", self.detail_created)
        
        details_group.setLayout(details_layout)
        layout.addWidget(details_group)
        
        self.tab_widget.addTab(tab, "Seasons")
    
    def _setup_create_tab(self):
        """Setup the create season tab."""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        form_group = QGroupBox("Create New Season")
        form_layout = QFormLayout()
        
        self.create_id = QLineEdit()
        self.create_id.setPlaceholderText("e.g., 2026Q1_MNQ_15m")
        self.create_name = QLineEdit()
        self.create_name.setPlaceholderText("e.g., MNQ 15m Season 2026Q1")
        
        self.create_universe = QLineEdit()
        self.create_universe.setPlaceholderText("Universe fingerprint")
        self.create_timeframes = QLineEdit()
        self.create_timeframes.setPlaceholderText("Timeframes fingerprint")
        self.create_dataset = QLineEdit()
        self.create_dataset.setPlaceholderText("Dataset snapshot ID")
        self.create_engine = QLineEdit()
        self.create_engine.setPlaceholderText("Engine constitution ID")
        
        self.create_tags = QLineEdit()
        self.create_tags.setPlaceholderText("comma-separated tags")
        self.create_note = QTextEdit()
        self.create_note.setMaximumHeight(100)
        
        form_layout.addRow("Season ID*:", self.create_id)
        form_layout.addRow("Display Name:", self.create_name)
        form_layout.addRow("Universe Fingerprint*:", self.create_universe)
        form_layout.addRow("Timeframes Fingerprint*:", self.create_timeframes)
        form_layout.addRow("Dataset Snapshot ID*:", self.create_dataset)
        form_layout.addRow("Engine Constitution ID*:", self.create_engine)
        form_layout.addRow("Tags:", self.create_tags)
        form_layout.addRow("Note:", self.create_note)
        
        form_group.setLayout(form_layout)
        layout.addWidget(form_group)
        
        # Create button
        create_btn = QPushButton("Create Season")
        create_btn.clicked.connect(self._create_season)
        layout.addWidget(create_btn)
        
        self.tab_widget.addTab(tab, "Create")
    
    def _setup_attach_tab(self):
        """Setup the attach job tab."""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        form_group = QGroupBox("Attach Job to Season")
        form_layout = QFormLayout()
        
        # Season selector
        self.attach_season_combo = QComboBox()
        self.attach_season_combo.addItem("-- Select Season --", None)
        form_layout.addRow("Season:", self.attach_season_combo)
        
        # Job ID input
        self.attach_job_id = QLineEdit()
        self.attach_job_id.setPlaceholderText("Enter job ID")
        form_layout.addRow("Job ID*:", self.attach_job_id)
        
        form_group.setLayout(form_layout)
        layout.addWidget(form_group)
        
        # Boundary validation info
        boundary_group = QGroupBox("Boundary Validation")
        boundary_layout = QVBoxLayout()
        self.boundary_info = QLabel(
            "Job will be attached only if all 4 boundary fields match exactly:\n"
            "1. Universe fingerprint\n"
            "2. Timeframes fingerprint\n"
            "3. Dataset snapshot ID\n"
            "4. Engine constitution ID"
        )
        self.boundary_info.setWordWrap(True)
        self.boundary_info.setStyleSheet("color: #666; font-style: italic;")
        boundary_layout.addWidget(self.boundary_info)
        boundary_group.setLayout(boundary_layout)
        layout.addWidget(boundary_group)
        
        # Attach button
        attach_btn = QPushButton("Attach Job")
        attach_btn.clicked.connect(self._attach_job)
        layout.addWidget(attach_btn)
        
        self.tab_widget.addTab(tab, "Attach Job")
    
    def _setup_manage_tab(self):
        """Setup the manage season tab."""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        form_group = QGroupBox("Manage Season State")
        form_layout = QFormLayout()
        
        # Season selector
        self.manage_season_combo = QComboBox()
        self.manage_season_combo.addItem("-- Select Season --", None)
        self.manage_season_combo.currentIndexChanged.connect(self._on_manage_season_changed)
        form_layout.addRow("Season:", self.manage_season_combo)
        
        # Current state display
        self.manage_current_state = QLabel()
        self.manage_current_state.setStyleSheet("font-weight: bold;")
        form_layout.addRow("Current State:", self.manage_current_state)
        
        # Available actions
        self.manage_actions_group = QGroupBox("Available Actions")
        actions_layout = QVBoxLayout()
        
        self.freeze_btn = QPushButton("Freeze Season")
        self.freeze_btn.clicked.connect(self._freeze_season)
        self.freeze_btn.setEnabled(False)
        actions_layout.addWidget(self.freeze_btn)
        
        self.archive_btn = QPushButton("Archive Season")
        self.archive_btn.clicked.connect(self._archive_season)
        self.archive_btn.setEnabled(False)
        actions_layout.addWidget(self.archive_btn)
        
        self.manage_actions_group.setLayout(actions_layout)
        form_layout.addRow("", self.manage_actions_group)
        
        form_group.setLayout(form_layout)
        layout.addWidget(form_group)
        
        self.tab_widget.addTab(tab, "Manage")
    
    def _setup_viewer_tab(self):
        """Setup the Season Viewer tab (P2-B/C/D)."""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        # Season selector
        selector_group = QGroupBox("Select Season")
        selector_layout = QHBoxLayout()
        
        self.viewer_season_combo = QComboBox()
        self.viewer_season_combo.addItem("-- Select Season --", None)
        self.viewer_season_combo.currentIndexChanged.connect(self._on_viewer_season_changed)
        
        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self._load_seasons)
        
        selector_layout.addWidget(QLabel("Season:"))
        selector_layout.addWidget(self.viewer_season_combo, 1)
        selector_layout.addWidget(refresh_btn)
        selector_group.setLayout(selector_layout)
        layout.addWidget(selector_group)
        
        # Season info display
        info_group = QGroupBox("Season Information")
        info_layout = QFormLayout()
        
        self.viewer_season_id = QLabel()
        self.viewer_season_state = QLabel()
        self.viewer_total_jobs = QLabel()
        self.viewer_valid_candidates = QLabel()
        
        info_layout.addRow("Season ID:", self.viewer_season_id)
        info_layout.addRow("State:", self.viewer_season_state)
        info_layout.addRow("Total Jobs:", self.viewer_total_jobs)
        info_layout.addRow("Valid Candidates:", self.viewer_valid_candidates)
        
        info_group.setLayout(info_layout)
        layout.addWidget(info_group)
        
        # P2-B: Analysis section
        analysis_group = QGroupBox("Season Analysis (P2-B)")
        analysis_layout = QVBoxLayout()
        
        self.analysis_table = QTableWidget()
        self.analysis_table.setColumnCount(5)
        self.analysis_table.setHorizontalHeaderLabels([
            "Candidate ID", "Strategy", "Score", "Rank", "Source Job"
        ])
        self.analysis_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.analysis_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.analysis_table.setSelectionMode(QTableWidget.SingleSelection)
        
        analysis_layout.addWidget(self.analysis_table)
        
        # Analysis buttons
        analysis_btn_layout = QHBoxLayout()
        self.analyze_btn = QPushButton("Analyze Season")
        self.analyze_btn.clicked.connect(self._analyze_season)
        self.analyze_btn.setEnabled(False)
        
        analysis_btn_layout.addWidget(self.analyze_btn)
        analysis_btn_layout.addStretch()
        analysis_layout.addLayout(analysis_btn_layout)
        
        analysis_group.setLayout(analysis_layout)
        layout.addWidget(analysis_group)
        
        # P2-C: Admission Decisions section
        decisions_group = QGroupBox("Admission Decisions (P2-C)")
        decisions_layout = QVBoxLayout()
        
        self.decisions_table = QTableWidget()
        self.decisions_table.setColumnCount(4)
        self.decisions_table.setHorizontalHeaderLabels([
            "Candidate", "Current Decision", "New Decision", "Notes"
        ])
        self.decisions_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        
        decisions_layout.addWidget(self.decisions_table)
        
        # Decision buttons
        decisions_btn_layout = QHBoxLayout()
        self.admit_btn = QPushButton("Submit Admission Decisions")
        self.admit_btn.clicked.connect(self._submit_admission_decisions)
        self.admit_btn.setEnabled(False)
        
        decisions_btn_layout.addWidget(self.admit_btn)
        decisions_btn_layout.addStretch()
        decisions_layout.addLayout(decisions_btn_layout)
        
        decisions_group.setLayout(decisions_layout)
        layout.addWidget(decisions_group)
        
        # P2-D: Export section
        export_group = QGroupBox("Export Portfolio Candidate Set (P2-D)")
        export_layout = QVBoxLayout()
        
        export_info = QLabel(
            "Export the current season's candidate set as a portfolio candidate set.\n"
            "Only available for seasons in DECIDING state."
        )
        export_info.setWordWrap(True)
        export_info.setStyleSheet("color: #666; font-style: italic;")
        export_layout.addWidget(export_info)
        
        self.export_btn = QPushButton("Export Candidates")
        self.export_btn.clicked.connect(self._export_candidates)
        self.export_btn.setEnabled(False)
        export_layout.addWidget(self.export_btn)
        
        export_group.setLayout(export_layout)
        layout.addWidget(export_group)
        
        layout.addStretch()
        
        self.tab_widget.addTab(tab, "Season Viewer")

    def _load_seasons(self):
        """Load seasons from API."""
        self._set_status("Loading seasons...")
        
        try:
            response = list_seasons_ssot()
            seasons = response.get("seasons", [])
            
            # Update seasons table
            self.seasons_table.setRowCount(len(seasons))
            for i, season in enumerate(seasons):
                self.seasons_table.setItem(i, 0, QTableWidgetItem(season.get("season_id", "")))
                self.seasons_table.setItem(i, 1, QTableWidgetItem(season.get("display_name", "")))
                self.seasons_table.setItem(i, 2, QTableWidgetItem(season.get("state", "")))
                
                # Boundary match (simplified - just show if boundary exists)
                boundary = season.get("boundary", {})
                has_boundary = all([
                    boundary.get("universe_fingerprint"),
                    boundary.get("timeframes_fingerprint"),
                    boundary.get("dataset_snapshot_id"),
                    boundary.get("engine_constitution_id"),
                ])
                self.seasons_table.setItem(i, 3, QTableWidgetItem("✓" if has_boundary else "✗"))
                
                # Jobs count (placeholder - would need to fetch attached jobs)
                self.seasons_table.setItem(i, 4, QTableWidgetItem("0"))
                
                # Created date
                created = season.get("created_at", "")
                if created:
                    # Shorten timestamp for display
                    created = created.split("T")[0]
                self.seasons_table.setItem(i, 5, QTableWidgetItem(created))
            
            # Update combo boxes
            self._update_season_combos(seasons)
            
            self._set_status(f"Loaded {len(seasons)} seasons")
            
        except SupervisorClientError as e:
            self._show_error(f"Failed to load seasons: {e.message}")
            self._set_status("Error loading seasons")
        except Exception as e:
            logger.exception("Unexpected error loading seasons")
            self._show_error(f"Unexpected error: {e}")
            self._set_status("Error loading seasons")
    
    def _update_season_combos(self, seasons: List[Dict[str, Any]]):
        """Update season combo boxes."""
        # Save current selections
        attach_current = self.attach_season_combo.currentData()
        manage_current = self.manage_season_combo.currentData()
        viewer_current = self.viewer_season_combo.currentData()
        
        # Clear and repopulate
        self.attach_season_combo.clear()
        self.manage_season_combo.clear()
        self.viewer_season_combo.clear()
        
        self.attach_season_combo.addItem("-- Select Season --", None)
        self.manage_season_combo.addItem("-- Select Season --", None)
        self.viewer_season_combo.addItem("-- Select Season --", None)
        
        for season in seasons:
            season_id = season.get("season_id")
            display_name = season.get("display_name", season_id)
            combo_text = f"{display_name} ({season_id})"
            
            self.attach_season_combo.addItem(combo_text, season_id)
            self.manage_season_combo.addItem(combo_text, season_id)
            self.viewer_season_combo.addItem(combo_text, season_id)
        
        # Restore selections if possible
        if attach_current:
            index = self.attach_season_combo.findData(attach_current)
            if index >= 0:
                self.attach_season_combo.setCurrentIndex(index)
        
        if manage_current:
            index = self.manage_season_combo.findData(manage_current)
            if index >= 0:
                self.manage_season_combo.setCurrentIndex(index)
                self._on_manage_season_changed(index)
        
        if viewer_current:
            index = self.viewer_season_combo.findData(viewer_current)
            if index >= 0:
                self.viewer_season_combo.setCurrentIndex(index)
                self._on_viewer_season_changed(index)
    
    def _on_season_selected(self):
        """Handle season selection in table."""
        selected = self.seasons_table.selectedItems()
        if not selected:
            return
        
        row = selected[0].row()
        season_id = self.seasons_table.item(row, 0).text()
        
        try:
            response = get_season_ssot(season_id)
            
            self.detail_id.setText(response.get("season_id", ""))
            self.detail_name.setText(response.get("display_name", ""))
            self.detail_state.setText(response.get("state", ""))
            
            # Format boundary
            boundary = response.get("boundary", {})
            boundary_text = "\n".join([
                f"Universe: {boundary.get('universe_fingerprint', 'N/A')}",
                f"Timeframes: {boundary.get('timeframes_fingerprint', 'N/A')}",
                f"Dataset: {boundary.get('dataset_snapshot_id', 'N/A')}",
                f"Engine: {boundary.get('engine_constitution_id', 'N/A')}",
            ])
            self.detail_boundary.setText(boundary_text)
            
            # Format jobs
            jobs = response.get("attached_job_ids", [])
            self.detail_jobs.setText(f"{len(jobs)} jobs")
            
            # Format created date
            created = response.get("created_at", "")
            if created:
                created = created.replace("T", " ").split(".")[0]
            self.detail_created.setText(created)
            
        except Exception as e:
            logger.exception(f"Failed to load season details: {e}")
            self._show_error(f"Failed to load season details: {e}")
    
    def _on_manage_season_changed(self, index: int):
        """Handle manage season combo change."""
        season_id = self.manage_season_combo.currentData()
        
        if not season_id:
            self.manage_current_state.setText("--")
            self.freeze_btn.setEnabled(False)
            self.archive_btn.setEnabled(False)
            return
        
        try:
            response = get_season_ssot(season_id)
            state = response.get("state", "")
            self.manage_current_state.setText(state)
            
            # Enable/disable buttons based on state
            self.freeze_btn.setEnabled(state == "OPEN")
            self.archive_btn.setEnabled(state in ["FROZEN", "DECIDING"])
            
        except Exception as e:
            logger.exception(f"Failed to load season state: {e}")
            self.manage_current_state.setText("Error")
            self.freeze_btn.setEnabled(False)
            self.archive_btn.setEnabled(False)
    
    def _create_season(self):
        """Create a new season."""
        # Validate required fields
        season_id = self.create_id.text().strip()
        if not season_id:
            self._show_error("Season ID is required")
            return
        
        universe = self.create_universe.text().strip()
        timeframes = self.create_timeframes.text().strip()
        dataset = self.create_dataset.text().strip()
        engine = self.create_engine.text().strip()
        
        if not all([universe, timeframes, dataset, engine]):
            self._show_error("All boundary fields are required")
            return
        
        # Prepare payload
        payload = {
            "season_id": season_id,
            "display_name": self.create_name.text().strip() or season_id,
            "universe_fingerprint": universe,
            "timeframes_fingerprint": timeframes,
            "dataset_snapshot_id": dataset,
            "engine_constitution_id": engine,
        }
        
        # Optional fields
        tags = self.create_tags.text().strip()
        if tags:
            payload["tags"] = [tag.strip() for tag in tags.split(",") if tag.strip()]
        
        note = self.create_note.toPlainText().strip()
        if note:
            payload["note"] = note
        
        self._set_status("Creating season...")
        
        try:
            response = create_season_ssot(payload)
            self._show_success(f"Season '{season_id}' created successfully")
            
            # Clear form
            self.create_id.clear()
            self.create_name.clear()
            self.create_universe.clear()
            self.create_timeframes.clear()
            self.create_dataset.clear()
            self.create_engine.clear()
            self.create_tags.clear()
            self.create_note.clear()
            
            # Refresh list
            self._load_seasons()
            
            self._set_status(f"Season '{season_id}' created")
            
        except SupervisorClientError as e:
            if e.status_code == 409:
                self._show_error(f"Season '{season_id}' already exists")
            else:
                self._show_error(f"Failed to create season: {e.message}")
            self._set_status("Failed to create season")
        except Exception as e:
            logger.exception(f"Unexpected error creating season: {e}")
            self._show_error(f"Unexpected error: {e}")
            self._set_status("Failed to create season")
    
    def _attach_job(self):
        """Attach a job to a season."""
        season_id = self.attach_season_combo.currentData()
        if not season_id:
            self._show_error("Please select a season")
            return
        
        job_id = self.attach_job_id.text().strip()
        if not job_id:
            self._show_error("Job ID is required")
            return
        
        self._set_status(f"Attaching job {job_id} to season {season_id}...")
        
        try:
            response = attach_job_to_season_ssot(season_id, job_id)
            
            if response.get("attached", False):
                self._show_success(f"Job {job_id} attached to season {season_id}")
                self.attach_job_id.clear()
                self._load_seasons()  # Refresh to update job count
            else:
                self._show_error(f"Failed to attach job: {response}")
            
            self._set_status(f"Job attachment completed")
            
        except SupervisorClientError as e:
            if e.status_code == 422:
                # Boundary mismatch - extract details
                try:
                    error_data = e.message
                    if isinstance(error_data, dict):
                        mismatch = error_data.get("mismatch_details", {})
                        details = []
                        for field, reason in mismatch.items():
                            details.append(f"{field}: {reason}")
                        
                        error_msg = f"Boundary mismatch:\n" + "\n".join(details)
                        self._show_error(error_msg)
                    else:
                        self._show_error(f"Boundary mismatch: {e.message}")
                except:
                    self._show_error(f"Boundary mismatch: {e.message}")
            elif e.status_code == 403:
                self._show_error(f"Cannot attach to season: {e.message}")
            elif e.status_code == 404:
                self._show_error(f"Season or job not found: {e.message}")
            else:
                self._show_error(f"Failed to attach job: {e.message}")
            
            self._set_status("Failed to attach job")
        except Exception as e:
            logger.exception(f"Unexpected error attaching job: {e}")
            self._show_error(f"Unexpected error: {e}")
            self._set_status("Failed to attach job")
    
    def _freeze_season(self):
        """Freeze a season."""
        season_id = self.manage_season_combo.currentData()
        if not season_id:
            self._show_error("Please select a season")
            return
        
        reply = QMessageBox.question(
            self,
            "Confirm Freeze",
            f"Are you sure you want to freeze season '{season_id}'?\n\n"
            "Frozen seasons cannot accept new job attachments.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if reply != QMessageBox.StandardButton.Yes:
            return
        
        self._set_status(f"Freezing season {season_id}...")
        
        try:
            response = freeze_season_ssot(season_id)
            self._show_success(f"Season '{season_id}' frozen successfully")
            self._load_seasons()  # Refresh list
            self._on_manage_season_changed(self.manage_season_combo.currentIndex())
            self._set_status(f"Season '{season_id}' frozen")
            
        except SupervisorClientError as e:
            if e.status_code == 403:
                self._show_error(f"Cannot freeze season: {e.message}")
            elif e.status_code == 404:
                self._show_error(f"Season not found: {e.message}")
            else:
                self._show_error(f"Failed to freeze season: {e.message}")
            self._set_status("Failed to freeze season")
        except Exception as e:
            logger.exception(f"Unexpected error freezing season: {e}")
            self._show_error(f"Unexpected error: {e}")
            self._set_status("Failed to freeze season")
    
    def _archive_season(self):
        """Archive a season."""
        season_id = self.manage_season_combo.currentData()
        if not season_id:
            self._show_error("Please select a season")
            return
        
        reply = QMessageBox.question(
            self,
            "Confirm Archive",
            f"Are you sure you want to archive season '{season_id}'?\n\n"
            "Archived seasons are read-only.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if reply != QMessageBox.StandardButton.Yes:
            return
        
        self._set_status(f"Archiving season {season_id}...")
        
        try:
            response = archive_season_ssot(season_id)
            self._show_success(f"Season '{season_id}' archived successfully")
            self._load_seasons()  # Refresh list
            self._on_manage_season_changed(self.manage_season_combo.currentIndex())
            self._set_status(f"Season '{season_id}' archived")
            
        except SupervisorClientError as e:
            if e.status_code == 403:
                self._show_error(f"Cannot archive season: {e.message}")
            elif e.status_code == 404:
                self._show_error(f"Season not found: {e.message}")
            else:
                self._show_error(f"Failed to archive season: {e.message}")
            self._set_status("Failed to archive season")
        except Exception as e:
            logger.exception(f"Unexpected error archiving season: {e}")
            self._show_error(f"Unexpected error: {e}")
            self._set_status("Failed to archive season")
    
    def _on_viewer_season_changed(self, index: int):
        """Handle viewer season combo change."""
        season_id = self.viewer_season_combo.currentData()
        
        if not season_id:
            self.viewer_season_id.setText("--")
            self.viewer_season_state.setText("--")
            self.viewer_total_jobs.setText("--")
            self.viewer_valid_candidates.setText("--")
            self.analyze_btn.setEnabled(False)
            self.admit_btn.setEnabled(False)
            self.export_btn.setEnabled(False)
            return
        
        try:
            response = get_season_ssot(season_id)
            state = response.get("state", "")
            jobs = response.get("attached_job_ids", [])
            
            self.viewer_season_id.setText(season_id)
            self.viewer_season_state.setText(state)
            self.viewer_total_jobs.setText(f"{len(jobs)}")
            
            # Enable/disable buttons based on state
            self.analyze_btn.setEnabled(state in ["FROZEN", "DECIDING"])
            self.admit_btn.setEnabled(state == "FROZEN")
            self.export_btn.setEnabled(state == "DECIDING")
            
            # Clear tables
            self.analysis_table.setRowCount(0)
            self.decisions_table.setRowCount(0)
            
            # Set placeholder for valid candidates (will be updated after analysis)
            self.viewer_valid_candidates.setText("-- (run analysis)")
            
        except Exception as e:
            logger.exception(f"Failed to load season for viewer: {e}")
            self.viewer_season_id.setText("Error")
            self.viewer_season_state.setText("Error")
            self.viewer_total_jobs.setText("--")
            self.viewer_valid_candidates.setText("--")
            self.analyze_btn.setEnabled(False)
            self.admit_btn.setEnabled(False)
            self.export_btn.setEnabled(False)
    
    def _analyze_season(self):
        """Analyze season (P2-B)."""
        season_id = self.viewer_season_combo.currentData()
        if not season_id:
            self._show_error("Please select a season")
            return
        
        self._set_status(f"Analyzing season {season_id}...")
        
        try:
            response = analyze_season_ssot(season_id)
            
            # Update season info
            self.viewer_valid_candidates.setText(f"{response.get('valid_candidates', 0)}")
            
            # Populate analysis table
            candidates = response.get("candidates", [])
            self.analysis_table.setRowCount(len(candidates))
            
            for i, candidate in enumerate(candidates):
                identity = candidate.get("identity", {})
                research_metrics = candidate.get("research_metrics", {})
                source = candidate.get("source", {})
                
                self.analysis_table.setItem(i, 0, QTableWidgetItem(identity.get("candidate_id", "")))
                self.analysis_table.setItem(i, 1, QTableWidgetItem(candidate.get("strategy_id", "")))
                self.analysis_table.setItem(i, 2, QTableWidgetItem(str(research_metrics.get("score", ""))))
                self.analysis_table.setItem(i, 3, QTableWidgetItem(str(identity.get("rank", ""))))
                self.analysis_table.setItem(i, 4, QTableWidgetItem(source.get("job_id", "")))
            
            # Populate decisions table with empty decisions
            self.decisions_table.setRowCount(len(candidates))
            for i, candidate in enumerate(candidates):
                identity = candidate.get("identity", {})
                candidate_id = identity.get("candidate_id", "")
                
                self.decisions_table.setItem(i, 0, QTableWidgetItem(candidate_id))
                self.decisions_table.setItem(i, 1, QTableWidgetItem("PENDING"))
                
                # Add combo box for new decision
                decision_combo = QComboBox()
                decision_combo.addItem("PENDING", "PENDING")
                decision_combo.addItem("ADMIT", "ADMIT")
                decision_combo.addItem("REJECT", "REJECT")
                decision_combo.addItem("HOLD", "HOLD")
                self.decisions_table.setCellWidget(i, 2, decision_combo)
                
                # Add notes field
                notes_edit = QLineEdit()
                notes_edit.setPlaceholderText("Optional notes")
                self.decisions_table.setCellWidget(i, 3, notes_edit)
            
            self._show_success(f"Season analysis completed: {len(candidates)} candidates found")
            self._set_status(f"Season {season_id} analyzed: {len(candidates)} candidates")
            
        except SupervisorClientError as e:
            if e.status_code == 403:
                self._show_error(f"Cannot analyze season: {e.message}")
            elif e.status_code == 404:
                self._show_error(f"Season not found: {e.message}")
            else:
                self._show_error(f"Failed to analyze season: {e.message}")
            self._set_status("Failed to analyze season")
        except Exception as e:
            logger.exception(f"Unexpected error analyzing season: {e}")
            self._show_error(f"Unexpected error: {e}")
            self._set_status("Failed to analyze season")
    
    def _submit_admission_decisions(self):
        """Submit admission decisions (P2-C)."""
        season_id = self.viewer_season_combo.currentData()
        if not season_id:
            self._show_error("Please select a season")
            return
        
        # Collect decisions from table
        decisions = []
        for i in range(self.decisions_table.rowCount()):
            candidate_item = self.decisions_table.item(i, 0)
            if not candidate_item:
                continue
                
            candidate_id = candidate_item.text()
            decision_widget = self.decisions_table.cellWidget(i, 2)
            notes_widget = self.decisions_table.cellWidget(i, 3)
            
            if not decision_widget:
                continue
                
            decision = decision_widget.currentData()
            notes = notes_widget.text() if notes_widget else ""
            
            if decision != "PENDING":
                decisions.append({
                    "candidate_id": candidate_id,
                    "decision": decision,
                    "notes": notes
                })
        
        if not decisions:
            self._show_error("No decisions to submit. Please set decisions for at least one candidate.")
            return
        
        reply = QMessageBox.question(
            self,
            "Confirm Admission Decisions",
            f"Submit {len(decisions)} admission decisions for season '{season_id}'?\n\n"
            "This will create evidence and update the season state.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if reply != QMessageBox.StandardButton.Yes:
            return
        
        self._set_status(f"Submitting {len(decisions)} admission decisions...")
        
        try:
            response = admit_candidates_to_season_ssot(season_id, decisions)
            
            admitted = response.get("admitted", 0)
            rejected = response.get("rejected", 0)
            held = response.get("held", 0)
            
            self._show_success(
                f"Admission decisions submitted successfully:\n"
                f"- Admitted: {admitted}\n"
                f"- Rejected: {rejected}\n"
                f"- Held: {held}"
            )
            
            # Refresh season state
            self._on_viewer_season_changed(self.viewer_season_combo.currentIndex())
            
            self._set_status(f"Admission decisions submitted: {admitted} admitted, {rejected} rejected, {held} held")
            
        except SupervisorClientError as e:
            if e.status_code == 403:
                self._show_error(f"Cannot submit admission decisions: {e.message}")
            elif e.status_code == 404:
                self._show_error(f"Season not found: {e.message}")
            elif e.status_code == 422:
                self._show_error(f"Invalid decisions: {e.message}")
            else:
                self._show_error(f"Failed to submit admission decisions: {e.message}")
            self._set_status("Failed to submit admission decisions")
        except Exception as e:
            logger.exception(f"Unexpected error submitting admission decisions: {e}")
            self._show_error(f"Unexpected error: {e}")
            self._set_status("Failed to submit admission decisions")
    
    def _export_candidates(self):
        """Export candidate set (P2-D)."""
        season_id = self.viewer_season_combo.currentData()
        if not season_id:
            self._show_error("Please select a season")
            return
        
        reply = QMessageBox.question(
            self,
            "Confirm Export",
            f"Export candidate set from season '{season_id}'?\n\n"
            "This will create a portfolio candidate set artifact.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if reply != QMessageBox.StandardButton.Yes:
            return
        
        self._set_status(f"Exporting candidate set from season {season_id}...")
        
        try:
            response = export_candidates_from_season_ssot(season_id)
            
            export_id = response.get("export_id", "")
            candidate_count = response.get("candidate_count", 0)
            artifact_path = response.get("artifact_path", "")
            
            self._show_success(
                f"Candidate set exported successfully:\n"
                f"- Export ID: {export_id}\n"
                f"- Candidates: {candidate_count}\n"
                f"- Artifact: {artifact_path}"
            )
            
            self._set_status(f"Candidate set exported: {candidate_count} candidates")
            
        except SupervisorClientError as e:
            if e.status_code == 403:
                self._show_error(f"Cannot export candidates: {e.message}")
            elif e.status_code == 404:
                self._show_error(f"Season not found: {e.message}")
            else:
                self._show_error(f"Failed to export candidates: {e.message}")
            self._set_status("Failed to export candidates")
        except Exception as e:
            logger.exception(f"Unexpected error exporting candidates: {e}")
            self._show_error(f"Unexpected error: {e}")
            self._set_status("Failed to export candidates")

    def _set_status(self, message: str):
        """Set status message."""
        self.status_label.setText(message)
    
    def _show_error(self, message: str):
        """Show error message."""
        QMessageBox.critical(self, "Error", message)
    
    def _show_success(self, message: str):
        """Show success message."""
        QMessageBox.information(self, "Success", message)


def show_season_ssot_dialog(parent: Optional[QWidget] = None):
    """Show the Season SSOT dialog."""
    dialog = SeasonSSOTDialog(parent)
    dialog.exec()