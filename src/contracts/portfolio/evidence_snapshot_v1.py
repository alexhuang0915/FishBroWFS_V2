"""
Evidence Snapshot v1 - SSOT contract for time-consistent evidence capture.

This module defines the Evidence Snapshot Index v1 contract, which guarantees
that gate summary/explanation interprets only the evidence that existed at verdict time.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class EvidenceFileV1(BaseModel):
    """Metadata for a single evidence file captured at snapshot time."""
    
    model_config = ConfigDict(frozen=True, extra="forbid")
    
    relpath: str = Field(
        ...,
        description="Relative path from evidence_root to this file"
    )
    sha256: str = Field(
        ...,
        description="SHA256 hash of file content at capture time"
    )
    size_bytes: int = Field(
        ...,
        description="File size in bytes at capture time"
    )
    created_at_iso: str = Field(
        ...,
        description="File creation timestamp (ISO 8601) captured at snapshot time"
    )
    mime: str = Field(
        default="application/octet-stream",
        description="MIME type of the file"
    )


class EvidenceSnapshotV1(BaseModel):
    """Complete evidence snapshot for a job at verdict time."""
    
    model_config = ConfigDict(frozen=True, extra="forbid")
    
    schema_version: Literal["v1.0"] = Field(
        default="v1.0",
        description="Evidence snapshot schema version"
    )
    job_id: str = Field(
        ...,
        description="Job identifier this snapshot belongs to"
    )
    captured_at_iso: str = Field(
        ...,
        description="Timestamp when snapshot was captured (ISO 8601)"
    )
    evidence_root: str = Field(
        ...,
        description="Absolute or canonical base path for evidence files"
    )
    files: list[EvidenceFileV1] = Field(
        default_factory=list,
        description="List of evidence files captured at verdict time"
    )
    
    @classmethod
    def create_for_job(
        cls,
        job_id: str,
        evidence_root: str,
        file_paths: list[str],
    ) -> "EvidenceSnapshotV1":
        """
        Create evidence snapshot by scanning files in evidence root.
        
        Args:
            job_id: Job identifier
            evidence_root: Base directory for evidence files
            file_paths: List of relative file paths to include
            
        Returns:
            EvidenceSnapshotV1 with captured metadata
        """
        import hashlib
        from pathlib import Path
        
        root_path = Path(evidence_root)
        files = []
        
        # Sort file paths for consistent ordering
        sorted_paths = sorted(file_paths)
        
        for relpath in sorted_paths:
            file_path = root_path / relpath
            if not file_path.exists():
                continue
                
            # Compute SHA256
            sha256_hash = hashlib.sha256()
            with open(file_path, "rb") as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    sha256_hash.update(chunk)
            
            # Get file metadata
            stat = file_path.stat()
            
            files.append(
                EvidenceFileV1(
                    relpath=relpath,
                    sha256=sha256_hash.hexdigest(),
                    size_bytes=stat.st_size,
                    created_at_iso=datetime.fromtimestamp(
                        stat.st_ctime
                    ).isoformat(),
                )
            )
        
        return cls(
            job_id=job_id,
            captured_at_iso=datetime.now().isoformat(),
            evidence_root=evidence_root,
            files=files,
        )
    
    def validate_file(self, relpath: str, file_path: str) -> tuple[bool, str]:
        """
        Validate that a file matches the snapshot.
        
        Args:
            relpath: Relative path of file to validate
            file_path: Absolute path to current file
            
        Returns:
            Tuple of (is_valid, reason)
        """
        import hashlib
        from pathlib import Path
        
        # Find the snapshot entry
        snapshot_file = None
        for f in self.files:
            if f.relpath == relpath:
                snapshot_file = f
                break
        
        if not snapshot_file:
            return False, f"File not in snapshot: {relpath}"
        
        # Check if file exists
        current_path = Path(file_path)
        if not current_path.exists():
            return False, f"File missing: {relpath}"
        
        # Compute current SHA256
        sha256_hash = hashlib.sha256()
        try:
            with open(current_path, "rb") as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    sha256_hash.update(chunk)
        except (OSError, IOError) as e:
            return False, f"Cannot read file: {relpath} ({e})"
        
        current_sha256 = sha256_hash.hexdigest()
        
        if current_sha256 != snapshot_file.sha256:
            return False, (
                f"SHA256 mismatch for {relpath}: "
                f"expected {snapshot_file.sha256[:16]}..., "
                f"got {current_sha256[:16]}..."
            )
        
        return True, "OK"


# Version constant for evidence snapshot schema
EVIDENCE_SNAPSHOT_SCHEMA_VERSION = "v1.0"