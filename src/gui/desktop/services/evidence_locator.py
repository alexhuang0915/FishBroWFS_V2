"""
Evidence Locator Service – Unified API for locating evidence files.

Provides structured navigation of job evidence files (manifest.json, runtime_metrics.json,
policy_check.json, reports, logs, etc.) with human‑readable labels and icons.

Design principles:
- Evidence‑first: prioritize evidence over raw logs.
- Categorized: group files by semantic type.
- Safe: never expose paths outside approved evidence directories.
- Lazy: only list files when requested.
"""

import os
import logging
import fnmatch
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from pathlib import Path

from .supervisor_client import get_reveal_evidence_path, SupervisorClientError

logger = logging.getLogger(__name__)


@dataclass
class EvidenceFile:
    """Represents a single evidence file."""
    path: Path                     # Absolute path to the file
    relative_path: str             # Path relative to evidence root
    category: str                  # "manifest", "metrics", "policy", "report", "log", "other"
    display_name: str              # Human‑readable name for UI
    description: str               # Short description of the file's purpose
    icon: str = "📄"               # Emoji icon for UI (optional)
    size_bytes: Optional[int] = None


class EvidenceLocator:
    """Service that locates and categorizes evidence files for a job."""

    _CATEGORY_PATTERNS = {
        "manifest": ["manifest.json"],
        "metrics": ["runtime_metrics.json", "*_perf.json"],
        "policy": ["policy_check.json"],
        "report": ["*report*.json", "*report*.html"],
        "log": ["*.log", "stdout*", "stderr*"],
    }
    
    # Mapping from SSOT category to UI category, icon, description
    _SSOT_TO_UI_CATEGORY = {
        "manifest": "manifest",
        "metrics": "metrics",
        "policy": "policy",
        "reports": "report",
        "logs": "log",
        "artifacts": "other",
        "other": "other",
    }
    
    _UI_CATEGORY_INFO = {
        "manifest": ("📋", "Strategy manifest"),
        "metrics": ("📊", "Runtime performance metrics"),
        "policy": ("🛡️", "Policy gate results"),
        "report": ("📈", "Strategy performance report"),
        "log": ("📝", "Process logs"),
        "other": ("📄", "Other artifact"),
    }
    
    @staticmethod
    def get_evidence_root(job_id: str) -> Optional[Path]:
        """Get the evidence root directory for a job.
        
        Returns None if the path is not available or invalid.
        """
        try:
            result = get_reveal_evidence_path(job_id)
            if isinstance(result, dict):
                path_str = result.get("path")
                if path_str:
                    path = Path(path_str).resolve()
                    if path.exists():
                        return path
                    else:
                        logger.warning(f"Evidence path does not exist: {path}")
            return None
        except SupervisorClientError as e:
            logger.error(f"Failed to get evidence path for job {job_id}: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error getting evidence path for job {job_id}: {e}")
            return None
    
    @staticmethod
    def list_evidence_files(job_id: str) -> List[EvidenceFile]:
        """List all evidence files for a job, categorized."""
        root = EvidenceLocator.get_evidence_root(job_id)
        if not root:
            return []
        
        evidence_files = []
        
        # Walk the evidence directory recursively
        for dirpath, dirnames, filenames in os.walk(root):
            for filename in filenames:
                file_path = Path(dirpath) / filename
                rel_path = file_path.relative_to(root)
                
                # Determine category
                category, icon, description = EvidenceLocator._categorize_file(str(rel_path))
                
                # Get file size
                try:
                    size = file_path.stat().st_size
                except OSError:
                    size = None
                
                evidence_files.append(EvidenceFile(
                    path=file_path,
                    relative_path=str(rel_path),
                    category=category,
                    display_name=EvidenceLocator._humanize_filename(filename),
                    description=description,
                    icon=icon,
                    size_bytes=size,
                ))
        
        # Sort by category, then by filename
        category_order = {"manifest": 0, "metrics": 1, "policy": 2, "report": 3, "log": 4, "other": 5}
        evidence_files.sort(key=lambda f: (category_order.get(f.category, 99), f.relative_path))
        
        return evidence_files
    
    @staticmethod
    def _categorize_file(rel_path: str) -> Tuple[str, str, str]:
        """Categorize a file based on its relative path using patterns."""
        filename = Path(rel_path).name
        
        for category, patterns in EvidenceLocator._CATEGORY_PATTERNS.items():
            for pattern in patterns:
                if fnmatch.fnmatch(filename, pattern):
                    icon, description = EvidenceLocator._UI_CATEGORY_INFO[category]
                    return category, icon, description
        
        # Default
        return "other", "📄", "Other artifact"
    
    @staticmethod
    def _matches_pattern(filename: str, pattern: str) -> bool:
        """Simple glob pattern matching (supports * and ?)."""
        import fnmatch
        return fnmatch.fnmatch(filename, pattern)
    
    @staticmethod
    def _humanize_filename(filename: str) -> str:
        """Convert a filename to a human‑readable display name."""
        # Remove extensions
        name = filename.rsplit('.', 1)[0] if '.' in filename else filename
        # Replace underscores with spaces
        name = name.replace('_', ' ')
        # Capitalize each word
        name = ' '.join(word.capitalize() for word in name.split())
        return name
    
    @staticmethod
    def get_file_content(job_id: str, relative_path: str) -> Optional[bytes]:
        """Read the content of an evidence file."""
        root = EvidenceLocator.get_evidence_root(job_id)
        if not root:
            return None
        
        file_path = root / relative_path
        if not file_path.exists() or not file_path.is_file():
            logger.warning(f"Evidence file not found: {file_path}")
            return None
        
        try:
            return file_path.read_bytes()
        except OSError as e:
            logger.error(f"Failed to read evidence file {relative_path}: {e}")
            return None
    
    @staticmethod
    def get_structured_evidence(job_id: str) -> Dict[str, Any]:
        """Get structured evidence summary for a job.
        
        Returns a dict with categories and file lists, suitable for UI display.
        """
        files = EvidenceLocator.list_evidence_files(job_id)
        
        # Group by category
        categories = {}
        for file in files:
            categories.setdefault(file.category, []).append({
                "relative_path": file.relative_path,
                "display_name": file.display_name,
                "description": file.description,
                "icon": file.icon,
                "size_bytes": file.size_bytes,
            })
        
        return {
            "job_id": job_id,
            "evidence_root": str(EvidenceLocator.get_evidence_root(job_id)),
            "categories": categories,
            "total_files": len(files),
        }


# Convenience functions for easy import
def list_evidence_files(job_id: str) -> List[EvidenceFile]:
    """List all evidence files for a job."""
    return EvidenceLocator.list_evidence_files(job_id)


def get_structured_evidence(job_id: str) -> Dict[str, Any]:
    """Get structured evidence summary."""
    return EvidenceLocator.get_structured_evidence(job_id)


def get_evidence_root(job_id: str) -> Optional[Path]:
    """Get evidence root directory."""
    return EvidenceLocator.get_evidence_root(job_id)