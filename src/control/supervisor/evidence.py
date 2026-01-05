"""
Evidence Enforcement - Non-bypassable runtime audit artifacts.
"""
from __future__ import annotations
import json
import hashlib
import os
from pathlib import Path
from typing import Dict, Any, List, Optional
from dataclasses import asdict
import tempfile
import shutil

from src.contracts.supervisor.evidence_schemas import (
    PolicyCheckBundle,
    FingerprintBundle,
    RuntimeMetrics,
    stable_params_hash,
    now_iso,
)


def job_evidence_dir(base_dir: Path, job_id: str) -> Path:
    """Get the evidence directory for a job."""
    return base_dir / job_id


def atomic_write_json(path: Path, data: Dict[str, Any]) -> None:
    """Atomically write JSON data to a file."""
    # Write to temp file then rename
    temp = path.with_suffix('.tmp')
    with open(temp, 'w') as f:
        json.dump(data, f, indent=2, sort_keys=True)
    temp.rename(path)


def compute_file_fingerprint(file_path: Path) -> str:
    """Compute SHA256 hash of a file."""
    sha256 = hashlib.sha256()
    with open(file_path, 'rb') as f:
        for chunk in iter(lambda: f.read(4096), b''):
            sha256.update(chunk)
    return sha256.hexdigest()


def discover_outputs(output_dir: Path) -> Dict[str, str]:
    """Discover output files and compute their fingerprints."""
    outputs = {}
    for root, _, files in os.walk(output_dir):
        for file in files:
            file_path = Path(root) / file
            rel_path = file_path.relative_to(output_dir)
            fingerprint = compute_file_fingerprint(file_path)
            outputs[str(rel_path)] = fingerprint
    return outputs


def write_manifest(
    evidence_dir: Path,
    job_id: str,
    job_type: str,
    state: str,
    start_time: str,
    end_time: str,
    additional_info: Optional[Dict[str, Any]] = None
) -> None:
    """Write manifest.json file."""
    manifest = {
        "job_id": job_id,
        "job_type": job_type,
        "state": state,
        "start_time": start_time,
        "end_time": end_time,
        "evidence_files": [
            "manifest.json",
            "policy_check.json",
            "inputs_fingerprint.json",
            "outputs_fingerprint.json",
            "runtime_metrics.json",
            "stdout_tail.log"
        ]
    }
    if additional_info:
        manifest.update(additional_info)
    
    atomic_write_json(evidence_dir / "manifest.json", manifest)


def write_policy_check(
    evidence_dir: Path,
    bundle: PolicyCheckBundle
) -> None:
    """Write policy_check.json file."""
    atomic_write_json(evidence_dir / "policy_check.json", asdict(bundle))


def write_inputs_fingerprint(
    evidence_dir: Path,
    params_hash: str,
    dependencies: Dict[str, str],
    code_fingerprint: str,
    hash_version: str = "v1"
) -> None:
    """Write inputs_fingerprint.json file."""
    fingerprint = {
        "params_hash": params_hash,
        "dependencies": dependencies,
        "code_fingerprint": code_fingerprint,
        "hash_version": hash_version
    }
    atomic_write_json(evidence_dir / "inputs_fingerprint.json", fingerprint)


def write_outputs_fingerprint(
    evidence_dir: Path,
    outputs: Dict[str, str]
) -> None:
    """Write outputs_fingerprint.json file."""
    atomic_write_json(evidence_dir / "outputs_fingerprint.json", {"outputs": outputs})


def write_runtime_metrics(
    evidence_dir: Path,
    metrics: RuntimeMetrics
) -> None:
    """Write runtime_metrics.json file."""
    atomic_write_json(evidence_dir / "runtime_metrics.json", asdict(metrics))


def capture_stdout_tail(
    evidence_dir: Path,
    stdout_content: str,
    max_lines: int = 100
) -> None:
    """Capture tail of stdout to stdout_tail.log."""
    lines = stdout_content.splitlines()
    tail = lines[-max_lines:] if len(lines) > max_lines else lines
    with open(evidence_dir / "stdout_tail.log", 'w') as f:
        f.write('\n'.join(tail))


def get_code_fingerprint() -> str:
    """
    Get git commit hash as code fingerprint.
    Falls back to 'unknown' if not in git repo.
    """
    import subprocess
    try:
        result = subprocess.run(
            ['git', 'rev-parse', 'HEAD'],
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent.parent.parent
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return "unknown"


def get_dependencies_fingerprint() -> Dict[str, str]:
    """
    Get fingerprint of dependencies (requirements.txt, pyproject.toml, etc.)
    Returns dict of {filename: hash}
    """
    deps = {}
    root_dir = Path(__file__).parent.parent.parent.parent
    
    for dep_file in ["requirements.txt", "pyproject.toml"]:
        file_path = root_dir / dep_file
        if file_path.exists():
            deps[dep_file] = compute_file_fingerprint(file_path)
    
    return deps