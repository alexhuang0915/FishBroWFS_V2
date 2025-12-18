"""Artifact reader for UI layer.

Reads JSON/YAML/MD files and returns data with metadata.
Never throws KeyError - returns ReadResult for upper layer validation.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False


@dataclass(frozen=True)
class ReadMeta:
    """Metadata about the read operation."""
    source_path: str  # Absolute path to source file
    sha256: str  # SHA256 hash of file content
    mtime_s: float  # Modification time in seconds since epoch


@dataclass(frozen=True)
class ReadResult:
    """
    Result of reading an artifact file.
    
    Contains raw data (dict/list/str) and metadata.
    Upper layer uses pydantic for validation.
    """
    raw: Any  # dict/list/str - raw parsed data
    meta: ReadMeta


@dataclass(frozen=True)
class ReadError:
    """Error information for failed read operations."""
    error_code: str  # "FILE_NOT_FOUND", "UNSUPPORTED_FORMAT", "YAML_NOT_AVAILABLE", "JSON_DECODE_ERROR", "IO_ERROR"
    message: str
    source_path: str


@dataclass(frozen=True)
class SafeReadResult:
    """
    Safe read result that never raises.
    
    Either contains ReadResult (success) or ReadError (failure).
    """
    result: Optional[ReadResult] = None
    error: Optional[ReadError] = None
    
    @property
    def is_ok(self) -> bool:
        """Check if read was successful."""
        return self.result is not None and self.error is None
    
    @property
    def is_error(self) -> bool:
        """Check if read failed."""
        return self.error is not None


def _compute_sha256(file_path: Path) -> str:
    """Compute SHA256 hash of file content."""
    sha256_hash = hashlib.sha256()
    with file_path.open("rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            sha256_hash.update(chunk)
    return sha256_hash.hexdigest()


def read_artifact(file_path: Path | str) -> ReadResult:
    """
    Read artifact file (JSON/YAML/MD) and return ReadResult.
    
    Args:
        file_path: Path to artifact file
        
    Returns:
        ReadResult with raw data and metadata
        
    Raises:
        FileNotFoundError: If file does not exist
        ValueError: If file format is not supported
    """
    path = Path(file_path).resolve()
    
    if not path.exists():
        raise FileNotFoundError(f"Artifact file not found: {path}")
    
    # Get metadata
    mtime_s = path.stat().st_mtime
    sha256 = _compute_sha256(path)
    
    # Read based on extension
    suffix = path.suffix.lower()
    
    if suffix == ".json":
        with path.open("r", encoding="utf-8") as f:
            raw = json.load(f)
    elif suffix in (".yaml", ".yml"):
        if not HAS_YAML:
            raise ValueError(f"YAML support not available. Install pyyaml to read {path}")
        with path.open("r", encoding="utf-8") as f:
            raw = yaml.safe_load(f)
    elif suffix == ".md":
        with path.open("r", encoding="utf-8") as f:
            raw = f.read()  # Return as string for markdown
    else:
        raise ValueError(f"Unsupported file format: {suffix}. Supported: .json, .yaml, .yml, .md")
    
    meta = ReadMeta(
        source_path=str(path),
        sha256=sha256,
        mtime_s=mtime_s,
    )
    
    return ReadResult(raw=raw, meta=meta)


def try_read_artifact(file_path: Path | str) -> SafeReadResult:
    """
    Safe version of read_artifact that never raises.
    
    All UI/VM code should use this function instead of read_artifact()
    to ensure no exceptions are thrown.
    
    Args:
        file_path: Path to artifact file
        
    Returns:
        SafeReadResult with either ReadResult (success) or ReadError (failure)
    """
    path = Path(file_path).resolve()
    
    # Check if file exists
    if not path.exists():
        return SafeReadResult(
            error=ReadError(
                error_code="FILE_NOT_FOUND",
                message=f"Artifact file not found: {path}",
                source_path=str(path),
            )
        )
    
    try:
        # Get metadata
        mtime_s = path.stat().st_mtime
        sha256 = _compute_sha256(path)
    except OSError as e:
        return SafeReadResult(
            error=ReadError(
                error_code="IO_ERROR",
                message=f"Failed to read file metadata: {e}",
                source_path=str(path),
            )
        )
    
    # Read based on extension
    suffix = path.suffix.lower()
    
    try:
        if suffix == ".json":
            with path.open("r", encoding="utf-8") as f:
                raw = json.load(f)
        elif suffix in (".yaml", ".yml"):
            if not HAS_YAML:
                return SafeReadResult(
                    error=ReadError(
                        error_code="YAML_NOT_AVAILABLE",
                        message=f"YAML support not available. Install pyyaml to read {path}",
                        source_path=str(path),
                    )
                )
            with path.open("r", encoding="utf-8") as f:
                raw = yaml.safe_load(f)
        elif suffix == ".md":
            with path.open("r", encoding="utf-8") as f:
                raw = f.read()  # Return as string for markdown
        else:
            return SafeReadResult(
                error=ReadError(
                    error_code="UNSUPPORTED_FORMAT",
                    message=f"Unsupported file format: {suffix}. Supported: .json, .yaml, .yml, .md",
                    source_path=str(path),
                )
            )
    except json.JSONDecodeError as e:
        return SafeReadResult(
            error=ReadError(
                error_code="JSON_DECODE_ERROR",
                message=f"JSON decode error: {e}",
                source_path=str(path),
            )
        )
    except OSError as e:
        return SafeReadResult(
            error=ReadError(
                error_code="IO_ERROR",
                message=f"Failed to read file: {e}",
                source_path=str(path),
            )
        )
    except Exception as e:
        return SafeReadResult(
            error=ReadError(
                error_code="UNKNOWN_ERROR",
                message=f"Unexpected error: {e}",
                source_path=str(path),
            )
        )
    
    meta = ReadMeta(
        source_path=str(path),
        sha256=sha256,
        mtime_s=mtime_s,
    )
    
    return SafeReadResult(result=ReadResult(raw=raw, meta=meta))
