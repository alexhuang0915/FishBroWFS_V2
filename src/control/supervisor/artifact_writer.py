#!/usr/bin/env python3
"""
Canonical artifact writer for supervisor jobs.

Writes spec.json, state.json, result.json, stdout.log, stderr.log
under the canonical job artifact directory (outputs/artifacts/jobs/<job_id>/).
"""

from __future__ import annotations

import json
import sys
import io
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, TextIO

from .models import JobSpec, JobStatus, now_iso
from ..artifacts import write_json_atomic, canonical_json_bytes


class CanonicalArtifactWriter:
    """Writes canonical job artifacts and captures stdout/stderr."""
    
    def __init__(self, job_id: str, spec: JobSpec, artifacts_dir: Path):
        self.job_id: str  # type annotation for Pylance
        setattr(self, 'job_id', job_id)
        self.spec = spec
        self.artifacts_dir = artifacts_dir
        self._stdout_capture: Optional[TextIO] = None
        self._stderr_capture: Optional[TextIO] = None
        self._original_stdout: Optional[TextIO] = None
        self._original_stderr: Optional[TextIO] = None
        
    def start_capture(self) -> None:
        """Start capturing stdout/stderr to log files."""
        # Ensure directory exists
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)
        
        # Open log files
        stdout_path = self.artifacts_dir / "stdout.log"
        stderr_path = self.artifacts_dir / "stderr.log"
        self._stdout_capture = open(stdout_path, "w", encoding="utf-8")
        self._stderr_capture = open(stderr_path, "w", encoding="utf-8")
        
        # Redirect sys.stdout and sys.stderr
        self._original_stdout = sys.stdout
        self._original_stderr = sys.stderr
        sys.stdout = self._stdout_capture
        sys.stderr = self._stderr_capture
        
    def stop_capture(self) -> None:
        """Stop capturing and restore original stdout/stderr."""
        if self._stdout_capture:
            sys.stdout = self._original_stdout or sys.__stdout__
            self._stdout_capture.close()
            self._stdout_capture = None
        if self._stderr_capture:
            sys.stderr = self._original_stderr or sys.__stderr__
            self._stderr_capture.close()
            self._stderr_capture = None
    
    def write_spec(self) -> None:
        """Write spec.json."""
        spec_dict = self.spec.model_dump(mode="json")
        spec_path = self.artifacts_dir / "spec.json"
        write_json_atomic(spec_path, spec_dict)
    
    def write_state(self, status: JobStatus, progress: Optional[float] = None,
                    phase: Optional[str] = None, error: Optional[str] = None) -> None:
        """Write state.json snapshot."""
        state = {
            "job_id": self.job_id,
            "status": status.value,
            "progress": progress,
            "phase": phase,
            "error": error,
            "timestamp": now_iso(),
        }
        state_path = self.artifacts_dir / "state.json"
        write_json_atomic(state_path, state)
    
    def write_result(self, result: Dict[str, Any]) -> None:
        """Write result.json."""
        result_path = self.artifacts_dir / "result.json"
        write_json_atomic(result_path, result)

    def write_manifest(
        self,
        *,
        job_type: str,
        state: str,
        start_time: str,
        end_time: str,
        additional_info: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Write a local receipt manifest (no HTTP assumptions)."""
        evidence_files = []
        try:
            for p in sorted(self.artifacts_dir.iterdir(), key=lambda x: x.name):
                if p.is_file():
                    evidence_files.append(p.name)
        except Exception:
            evidence_files = []

        manifest: Dict[str, Any] = {
            "job_id": self.job_id,
            "job_type": str(job_type),
            "state": state,
            "start_time": start_time,
            "end_time": end_time,
            "evidence_files": evidence_files,
        }
        if additional_info:
            manifest.update(additional_info)

        # Write both generic + typed receipt for stable discovery.
        write_json_atomic(self.artifacts_dir / "manifest.json", manifest)
        normalized = str(job_type).strip().lower()
        if normalized:
            receipt = self.artifacts_dir / f"{normalized}_manifest.json"
            if receipt.name != "manifest.json":
                write_json_atomic(receipt, manifest)
    
    def write_all(self, status: JobStatus, result: Optional[Dict[str, Any]] = None,
                  progress: Optional[float] = None, phase: Optional[str] = None,
                  error: Optional[str] = None) -> None:
        """Write spec, state, result (if any) in one call."""
        self.write_spec()
        self.write_state(status, progress, phase, error)
        if result is not None:
            self.write_result(result)
    
    def __enter__(self):
        self.start_capture()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop_capture()


def write_canonical_artifacts(job_id: str, spec: JobSpec, artifacts_dir: Path,
                              status: JobStatus, result: Optional[Dict[str, Any]] = None,
                              progress: Optional[float] = None, phase: Optional[str] = None,
                              error: Optional[str] = None) -> None:
    """Convenience function to write all canonical artifacts."""
    writer = CanonicalArtifactWriter(job_id, spec, artifacts_dir)
    writer.write_all(status, result, progress, phase, error)
