
"""File system snapshot utilities for hardening tests.

Provides deterministic snapshot of file trees with mtime and SHA256.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, Optional


@dataclass(frozen=True)
class FileSnap:
    """Immutable snapshot of a single file."""
    rel_path: str  # POSIX-style relative path using '/'
    size: int
    mtime_ns: int
    sha256: str


def compute_sha256(path: Path) -> str:
    """Compute SHA256 hash of file content.
    
    Uses existing compute_sha256 from control.artifacts if available,
    otherwise implements directly.
    """
    try:
        from control.artifacts import compute_sha256 as cs
        return cs(path.read_bytes())
    except ImportError:
        # Fallback implementation
        return hashlib.sha256(path.read_bytes()).hexdigest()


def snapshot_tree(root: Path, *, include_sha256: bool = True) -> Dict[str, FileSnap]:
    """
    Deterministic snapshot of all files under root.
    
    Args:
        root: Directory root to snapshot.
        include_sha256: Whether to compute SHA256 hash (expensive for large files).
    
    Returns:
        Dictionary mapping relative path (POSIX-style) to FileSnap.
        Paths are sorted in stable alphabetical order.
    """
    snapshots: Dict[str, FileSnap] = {}
    
    # Walk through all files recursively
    for file_path in sorted(root.rglob("*")):
        if not file_path.is_file():
            continue
        
        # Get relative path and convert to POSIX style
        rel_path = file_path.relative_to(root).as_posix()
        
        # Get file stats
        stat = file_path.stat()
        size = stat.st_size
        mtime_ns = stat.st_mtime_ns
        
        # Compute SHA256 if requested
        sha256 = ""
        if include_sha256:
            sha256 = compute_sha256(file_path)
        
        snapshots[rel_path] = FileSnap(
            rel_path=rel_path,
            size=size,
            mtime_ns=mtime_ns,
            sha256=sha256,
        )
    
    return snapshots


def diff_snap(a: Dict[str, FileSnap], b: Dict[str, FileSnap]) -> dict:
    """
    Compare two snapshots and return differences.
    
    Args:
        a: First snapshot.
        b: Second snapshot.
    
    Returns:
        Dictionary with keys:
          - added: list of paths present in b but not in a
          - removed: list of paths present in a but not in b
          - changed: list of paths present in both but with different
                     size, mtime_ns, or sha256
    """
    a_keys = set(a.keys())
    b_keys = set(b.keys())
    
    added = sorted(b_keys - a_keys)
    removed = sorted(a_keys - b_keys)
    
    changed = []
    for key in sorted(a_keys & b_keys):
        snap_a = a[key]
        snap_b = b[key]
        if (snap_a.size != snap_b.size or 
            snap_a.mtime_ns != snap_b.mtime_ns or 
            snap_a.sha256 != snap_b.sha256):
            changed.append(key)
    
    return {
        "added": added,
        "removed": removed,
        "changed": changed,
    }


