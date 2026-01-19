"""
BAR PREPARE Tab - SSOT Integrated Version

Single entry point for RAW → PARQUET data preparation with:
1. Registry SSOT integration (instrument registry as source of truth)
2. Runtime index tracking (machine-readable index of prepared data)
3. AI-assisted registration workflow for new instrument discovery
4. System sync with runtime index

LEFT PANEL Components:
- RAW selector: Shows available raw files from data/raw/
- TIME selector: Shows available timeframes from registry
- BUILD button: Triggers build process for selected instruments/timeframes

RIGHT PANEL Components:
- Inventory + Status: Shows instrument inventory with status badges
- Build progress: Shows build queue status
- Validation status: Shows bars contract validation results
"""

import logging
import json
import shutil
from pathlib import Path
from typing import List, Dict, Any, Optional, Set
from datetime import datetime

from PySide6.QtCore import Qt, Signal, Slot, QTimer, QThread, pyqtSignal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QGroupBox, QFrame, QSizePolicy, QSpacerItem, QProgressBar,
    QListWidget, QListWidgetItem, QCheckBox, QScrollArea,
    QSplitter, QTreeWidget, QTreeWidgetItem, QHeaderView,
    QMessageBox, QComboBox, QLineEdit, QTextEdit, QFileDialog
)

from ..state.bar_prepare_state import bar_prepare_state
from ..services.supervisor_client import submit_job, SupervisorClientError
from core.bars_contract import derive_instruments_from_raw, validate_bars
from config.registry.instruments import load_instruments, InstrumentRegistry
from core.season_context import outputs_root
from config.registry.timeframes import load_timeframes

logger = logging.getLogger(__name__)


class RuntimeIndexWorker(QThread):
    """Background worker to generate runtime index."""
    
    index_generated = pyqtSignal(dict)
    error_occurred = pyqtSignal(str)
    
    def __init__(self):
        super().__init__()
        self.raw_root = Path("data/raw")
        outputs_base = Path(outputs_root())
        self.parquet_root = outputs_base / "parquet"
        self.shared_root = outputs_base / "shared"
        self.runtime_index_path = outputs_base / "_runtime" / "bar_prepare_index.json"
        
    def run(self):
        """Generate runtime index in background thread."""
        try:
            index = self._generate_index()
            self.index_generated.emit(index)
        except Exception as e:
            self.error_occurred.emit(f"Failed to generate runtime index: {e}")
    
    def _generate_index(self) -> Dict[str, Any]:
        """Generate comprehensive runtime index."""
        # Load registry SSOT
        instrument_registry = load_instruments()
        timeframe_registry = load_timeframes()
        
        # Scan raw directory
        raw_files = self._scan_raw_directory()
        
        # Scan parquet directory
        parquet_files = self._scan_parquet_directory()
        
        # Scan shared bars cache
        shared_bars = self._scan_shared_bars()
        
        # Build instrument index
        instruments_index = {}
        for instrument_spec in instrument_registry.instruments:
            instrument_id = instrument_spec.id
            display_name = instrument_spec.display_name
            
            # Find raw files for this instrument
            instrument_raw_files = []
            for raw_file in raw_files:
                if instrument_id in raw_file["name"]:
                    instrument_raw_files.append(raw_file)
            
            # Find parquet status
            parquet_status = self._get_parquet_status(instrument_id, parquet_files)
            
            # Find timeframe status
            timeframe_status = self._get_timeframe_status(instrument_id, shared_bars)
            
            # Build validation status
            validation_status = self._get_validation_status(
                instrument_id, instrument_raw_files, parquet_status
            )
            
            instruments_index[instrument_id] = {
                "instrument_id": instrument_id,
                "display_name": display_name,
                "registry_present": True,
                "raw_files": instrument_raw_files,
                "parquet_status": parquet_status,
                "timeframes": timeframe_status,
                "last_checked_utc": datetime.utcnow().isoformat() + "Z",
                "validation_status": validation_status
            }
        
        # Check for raw files without registry entries (potential new instruments)
        orphan_raw = self._find_orphan_raw_files(raw_files, instrument_registry)
        
        index = {
            "version": "1.0",
            "generated_at_utc": datetime.utcnow().isoformat() + "Z",
            "raw_data_root": str(self.raw_root.absolute()),
            "parquet_data_root": str(self.parquet_root.absolute()),
            "instruments": instruments_index,
            "timeframes": timeframe_registry.allowed_timeframes,
            "orphan_raw_files": orphan_raw,
            "last_sync_utc": datetime.utcnow().isoformat() + "Z"
        }
        
        # Write index atomically
        self._write_index_atomic(index)
        
        return index
    
    def _scan_raw_directory(self) -> List[Dict[str, Any]]:
        """Scan raw directory for TXT files."""
        raw_files = []
        if self.raw_root.exists():
            for txt_path in self.raw_root.glob("**/*.txt"):
                try:
                    stat = txt_path.stat()
                    raw_files.append({
                        "path": str(txt_path),
                        "name": txt_path.name,
                        "size_bytes": stat.st_size,
                        "modified_utc": datetime.fromtimestamp(stat.st_mtime).isoformat() + "Z",
                        "instrument_candidate": self._extract_instrument_candidate(txt_path.name)
                    })
                except Exception as e:
                    logger.warning(f"Failed to stat raw file {txt_path}: {e}")
        return sorted(raw_files, key=lambda x: x["name"])
    
    def _scan_parquet_directory(self) -> List[Dict[str, Any]]:
        """Scan parquet directory for built data."""
        parquet_files = []
        if self.parquet_root.exists():
            for parquet_path in self.parquet_root.glob("**/*.parquet"):
                try:
                    stat = parquet_path.stat()
                    # Extract instrument ID from path
                    rel_path = parquet_path.relative_to(self.parquet_root)
                    instrument_id = rel_path.parts[0].replace("_", ".")
                    
                    parquet_files.append({
                        "path": str(parquet_path),
                        "instrument_id": instrument_id,
                        "size_bytes": stat.st_size,
                        "modified_utc": datetime.fromtimestamp(stat.st_mtime).isoformat() + "Z"
                    })
                except Exception as e:
                    logger.warning(f"Failed to stat parquet file {parquet_path}: {e}")
        return parquet_files
    
    def _scan_shared_bars(self) -> List[Dict[str, Any]]:
        """Scan shared bars cache for resampled bars."""
        shared_bars = []
        if self.shared_root.exists():
            for season_dir in self.shared_root.iterdir():
                if season_dir.is_dir():
                    for dataset_dir in season_dir.iterdir():
                        if dataset_dir.is_dir():
                            # Look for resampled bars
                            for npz_path in dataset_dir.glob("resampled_*.npz"):
                                try:
                                    # Extract timeframe from filename
                                    tf_str = npz_path.stem.replace("resampled_", "").replace("m", "")
                                    timeframe = int(tf_str)
                                    
                                    stat = npz_path.stat()
                                    shared_bars.append({
                                        "path": str(npz_path),
                                        "season": season_dir.name,
                                        "dataset_id": dataset_dir.name,
                                        "timeframe": timeframe,
                                        "size_bytes": stat.st_size,
                                        "modified_utc": datetime.fromtimestamp(stat.st_mtime).isoformat() + "Z"
                                    })
                                except Exception as e:
                                    logger.warning(f"Failed to process shared bar {npz_path}: {e}")
        return shared_bars
    
    def _extract_instrument_candidate(self, filename: str) -> Optional[str]:
        """Extract potential instrument ID from filename."""
        # Use bars contract derivation logic
        result = derive_instruments_from_raw([filename])
        if result.instruments:
            return result.instruments[0]
        return None
    
    def _get_parquet_status(self, instrument_id: str, parquet_files: List[Dict]) -> Dict[str, Any]:
        """Get parquet status for instrument."""
        instrument_parquet = [
            p for p in parquet_files 
            if p["instrument_id"] == instrument_id
        ]
        
        if not instrument_parquet:
            return {
                "exists": False,
                "path": None,
                "status": "raw_only"
            }
        
        # For now, just return the first parquet file
        parquet = instrument_parquet[0]
        return {
            "exists": True,
            "path": parquet["path"],
            "size_bytes": parquet["size_bytes"],
            "status": "parquet_built",
            "built_at_utc": parquet["modified_utc"]
        }
    
    def _get_timeframe_status(self, instrument_id: str, shared_bars: List[Dict]) -> Dict[str, Any]:
        """Get timeframe status for instrument."""
        timeframe_status = {}
        
        # Find shared bars for this instrument
        instrument_bars = [
            b for b in shared_bars 
            if b["dataset_id"] == instrument_id
        ]
        
        # Group by timeframe
        for bar in instrument_bars:
            tf = str(bar["timeframe"])
            timeframe_status[tf] = {
                "status": "built",
                "path": bar["path"],
                "bars_count": None,  # Would need to read NPZ to get count
                "built_at_utc": bar["modified_utc"]
            }
        
        return timeframe_status
    
    def _get_validation_status(self, instrument_id: str, raw_files: List[Dict], 
                              parquet_status: Dict) -> Dict[str, Any]:
        """Get validation status for instrument."""
        validation = {
            "raw_valid": len(raw_files) > 0,
            "parquet_valid": parquet_status.get("exists", False),
            "gates_passed": [],
            "last_validation_utc": None
        }
        
        # If parquet exists, validate it
        if parquet_status.get("exists") and parquet_status.get("path"):
            try:
                result = validate_bars(parquet_status["path"])
                if result.gate_a_passed:
                    validation["gates_passed"].append("A")
                if result.gate_b_passed:
                    validation["gates_passed"].append("B")
                if result.gate_c_passed:
                    validation["gates_passed"].append("C")
                validation["last_validation_utc"] = datetime.utcnow().isoformat() + "Z"
            except Exception as e:
                logger.warning(f"Failed to validate parquet for {instrument_id}: {e}")
        
        return validation
    
    def _find_orphan_raw_files(self, raw_files: List[Dict], 
                              registry: InstrumentRegistry) -> List[Dict[str, Any]]:
        """Find raw files that don't match any registry instrument."""
        orphan_files = []
        registry_ids = {inst.id for inst in registry.instruments}
        
        for raw_file in raw_files:
            candidate = raw_file.get("instrument_candidate")
            if candidate and candidate not in registry_ids:
                orphan_files.append({
                    "path": raw_file["path"],
                    "name": raw_file["name"],
                    "instrument_candidate": candidate,
                    "size_bytes": raw_file["size_bytes"]
                })
        
        return orphan_files
    
    def _write_index_atomic(self, index: Dict[str, Any]):
        """Write index atomically using rename."""
        self.runtime_index_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = self.runtime_index_path.with_suffix('.tmp')
        
        try:
            with open(temp_path, 'w') as f:
                json.dump(index, f, indent=2, sort_keys=True)
            temp_path.rename(self.runtime_index_path)
            logger.info(f"Runtime index written to {self.runtime_index_path}")
        except Exception as e:
            logger.error(f"Failed to write runtime index: {e}")
            if temp_path.exists():
                temp_path.unlink()


class SystemSyncWorker(QThread):
    """Background worker to perform system sync operations."""
    
    sync_completed = pyqtSignal(dict)
    sync_progress = pyqtSignal(str, int)  # message, percentage
    sync_error = pyqtSignal(str)
    
    def __init__(self, operation: str, source_path: Optional[Path] = None, 
                 target_path: Optional[Path] = None):
        super().__init__()
        self.operation = operation  # "backup", "restore", "cleanup", "validate"
        self.source_path = source_path
        self.target_path = target_path
        self.runtime_index_path = Path(outputs_root()) / "_runtime" / "bar_prepare_index.json"
        
    def run(self):
        """Perform system sync operation in background thread."""
        try:
            if self.operation == "backup":
                result = self._perform_backup()
            elif self.operation == "restore":
                result = self._perform_restore()
            elif self.operation == "cleanup":
                result = self._perform_cleanup()
            elif self.operation == "validate":
                result = self._perform_validation()
            else:
                raise ValueError(f"Unknown operation: {self.operation}")
            
            self.sync_completed.emit(result)
        except Exception as e:
            self.sync_error.emit(f"System sync failed: {e}")
    
    def _perform_backup(self) -> Dict[str, Any]:
        """Backup runtime index and critical data."""
        self.sync_progress.emit("Starting backup...", 10)
        
        # Create backup directory
        backup_dir = Path(outputs_root()) / "_backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_name = f"bar_prepare_backup_{timestamp}"
        backup_path = backup_dir / backup_name
        
        self.sync_progress.emit("Creating backup directory...", 20)
        backup_path.mkdir(parents=True, exist_ok=True)
        
        # Backup runtime index
        if self.runtime_index_path.exists():
            self.sync_progress.emit("Backing up runtime index...", 40)
            shutil.copy2(self.runtime_index_path, backup_path / "bar_prepare_index.json")
        
        # Backup registry files
        self.sync_progress.emit("Backing up registry files...", 60)
        registry_files = [
            Path("configs/registry/instruments.yaml"),
            Path("configs/registry/timeframes.yaml"),
            Path("configs/registry/datasets.yaml")
        ]
        
        registry_backup_dir = backup_path / "registry"
        registry_backup_dir.mkdir(parents=True, exist_ok=True)
        
        for reg_file in registry_files:
            if reg_file.exists():
                shutil.copy2(reg_file, registry_backup_dir / reg_file.name)
        
        # Create backup manifest
        self.sync_progress.emit("Creating backup manifest...", 80)
        manifest = {
            "backup_name": backup_name,
            "created_at_utc": datetime.utcnow().isoformat() + "Z",
            "operation": "backup",
            "contents": {
                "runtime_index": self.runtime_index_path.exists(),
                "registry_files": [str(f) for f in registry_files if f.exists()],
                "backup_path": str(backup_path.absolute())
            }
        }
        
        manifest_path = backup_path / "manifest.json"
        with open(manifest_path, 'w') as f:
            json.dump(manifest, f, indent=2)
        
        self.sync_progress.emit("Backup completed successfully", 100)
        
        return {
            "operation": "backup",
            "success": True,
            "backup_path": str(backup_path.absolute()),
            "manifest": manifest
        }
    
    def _perform_restore(self) -> Dict[str, Any]:
        """Restore from backup."""
        if not self.source_path or not self.source_path.exists():
            raise ValueError(f"Source backup path does not exist: {self.source_path}")
        
        self.sync_progress.emit("Starting restore...", 10)
        
        # Read backup manifest
        manifest_path = self.source_path / "manifest.json"
        if not manifest_path.exists():
            raise ValueError("Backup manifest not found")
        
        with open(manifest_path, 'r') as f:
            manifest = json.load(f)
        
        self.sync_progress.emit("Validating backup...", 20)
        
        # Restore runtime index
        backup_index = self.source_path / "bar_prepare_index.json"
        if backup_index.exists():
            self.sync_progress.emit("Restoring runtime index...", 40)
            shutil.copy2(backup_index, self.runtime_index_path)
        
        # Restore registry files
        registry_backup_dir = self.source_path / "registry"
        if registry_backup_dir.exists():
            self.sync_progress.emit("Restoring registry files...", 60)
            for reg_file in registry_backup_dir.iterdir():
                if reg_file.is_file():
                    target_path = Path("configs/registry") / reg_file.name
                    target_path.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(reg_file, target_path)
        
        self.sync_progress.emit("Restore completed successfully", 100)
        
        return {
            "operation": "restore",
            "success": True,
            "restored_from": str(self.source_path.absolute()),
            "manifest": manifest
        }
    
    def _perform_cleanup(self) -> Dict[str, Any]:
        """Clean up orphaned data files."""
        self.sync_progress.emit("Starting cleanup...", 10)
        
        # Load runtime index
