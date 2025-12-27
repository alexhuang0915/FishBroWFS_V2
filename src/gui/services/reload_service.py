"""
Reload service stub for FishBroWFS_V2.

This module provides file signature computation and system snapshot utilities.
Originally part of the UI layer, now kept for compatibility with control modules.
"""

import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Any


def compute_file_signature(file_path: Path, max_size_mb: int = 50) -> str:
    """Compute signature for a file.
    
    For small files (< max_size_mb): compute sha256
    For large files: use stat-hash (path + size + mtime)
    """
    try:
        if not file_path.exists():
            return "missing"
        
        stat = file_path.stat()
        file_size_mb = stat.st_size / (1024 * 1024)
        
        if file_size_mb < max_size_mb:
            # Small file: compute actual hash
            hasher = hashlib.sha256()
            with open(file_path, 'rb') as f:
                # Read in chunks to handle large files
                chunk_size = 8192
                while chunk := f.read(chunk_size):
                    hasher.update(chunk)
            return f"sha256:{hasher.hexdigest()[:16]}"
        else:
            # Large file: use stat-hash
            return f"stat:{file_path.name}:{stat.st_size}:{stat.st_mtime}"
    except Exception as e:
        return f"error:{str(e)[:50]}"


def get_system_snapshot() -> Dict[str, Any]:
    """Return a minimal system snapshot summary.
    
    Returns:
        Dictionary with snapshot fields expected by input_manifest.
    """
    from datetime import datetime, timezone
    return {
        "created_at": datetime.now(timezone.utc),
        "total_datasets": 0,
        "total_strategies": 0,
        "notes": [],
        "errors": []
    }


# For backward compatibility, also export a class if needed
class ReloadService:
    """Stub class for compatibility with tests."""
    
    @staticmethod
    def compute_file_signature(file_path: Path) -> str:
        return compute_file_signature(file_path)
    
    @staticmethod
    def get_system_snapshot() -> Dict[str, Any]:
        return get_system_snapshot()