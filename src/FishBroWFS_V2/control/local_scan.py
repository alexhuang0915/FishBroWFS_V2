#!/usr/bin/env python3
"""
Local-Strict filesystem scanner (NOT Git).

Mission: Enumerate files based on filesystem truth, ignoring .gitignore,
respecting allowlist/denylist + caps to prevent explosion.

Contract:
- MUST NOT rely on git ls-files or tracked-only enumeration.
- MUST include untracked files in allowed roots.
- MUST ignore .gitignore (gitignore_respected=false).
- MUST enforce allowlist + denylist + caps to prevent explosion.
- MUST write audit rules to outputs/snapshots/full/LOCAL_SCAN_RULES.json.
"""

from __future__ import annotations
from dataclasses import dataclass
from fnmatch import fnmatch
import hashlib
import json
from pathlib import Path
from typing import Iterator, Tuple, List, Set, Optional
import os


@dataclass(frozen=True)
class LocalScanPolicy:
    """Policy for local-strict filesystem scanning."""
    allowed_roots: tuple[str, ...]
    allowed_root_files_glob: tuple[str, ...]
    deny_segments: tuple[str, ...]
    outputs_allow: tuple[str, ...]
    max_files: int
    max_bytes: int
    gitignore_respected: bool


def default_local_strict_policy() -> LocalScanPolicy:
    """Return policy with the defaults defined in the spec."""
    return LocalScanPolicy(
        allowed_roots=("src", "tests", "scripts", "docs"),
        allowed_root_files_glob=(
            "Makefile",
            "pyproject.toml",
            "README*",
            ".python-version",
            "requirements*.txt",
            "uv.lock",
            "poetry.lock",
        ),
        deny_segments=(
            ".git",
            ".venv",
            "venv",
            "node_modules",
            "__pycache__",
            ".pytest_cache",
            ".mypy_cache",
            ".ruff_cache",
            ".cache",
            ".idea",
            ".vscode",
            "outputs",  # will be handled by outputs exception rule
        ),
        outputs_allow=("outputs/snapshots",),
        max_files=20000,
        max_bytes=2_000_000,  # 2MB
        gitignore_respected=False,
    )


def _has_deny_segment(rel: Path, deny: tuple[str, ...]) -> bool:
    """Check if any path segment matches a deny segment."""
    parts = rel.parts
    return any(seg in parts for seg in deny)


def should_include_file(rel_path: Path, policy: LocalScanPolicy) -> bool:
    """
    Pure include/exclude decision.
    
    Returns True if the file should be included in the scan.
    """
    p = rel_path.as_posix()
    
    # Root allowlist - files directly in repo root
    if "/" not in p:
        return any(fnmatch(rel_path.name, g) for g in policy.allowed_root_files_glob)
    
    top = rel_path.parts[0]
    
    # outputs exception rule
    if top == "outputs":
        # Check if path starts with any allowed outputs subdirectory
        return any(p.startswith(allowed + "/") or p == allowed 
                   for allowed in policy.outputs_allow)
    
    # allowed roots only
    if top not in policy.allowed_roots:
        return False
    
    # deny segments anywhere in path
    if _has_deny_segment(rel_path, policy.deny_segments):
        return False
    
    return True


def iter_repo_files_local_strict(
    repo_root: Path,
    policy: LocalScanPolicy,
) -> List[Path]:
    """
    Return deterministic sorted list of included files, relative to repo_root.
    
    Walks the filesystem, applies include/exclude rules, respects caps.
    """
    included: List[Path] = []
    
    # Walk through all allowed roots and root files
    candidates: Set[Path] = set()
    
    # Add root files
    for pattern in policy.allowed_root_files_glob:
        for path in repo_root.glob(pattern):
            if path.is_file():
                rel = path.relative_to(repo_root)
                candidates.add(rel)
    
    # Add files from allowed roots
    for root_dir in policy.allowed_roots:
        root_path = repo_root / root_dir
        if not root_path.exists():
            continue
        for path in root_path.rglob("*"):
            if not path.is_file():
                continue
            rel = path.relative_to(repo_root)
            candidates.add(rel)
    
    # Add outputs exception files
    for allowed_output in policy.outputs_allow:
        output_path = repo_root / allowed_output
        if not output_path.exists():
            continue
        for path in output_path.rglob("*"):
            if not path.is_file():
                continue
            rel = path.relative_to(repo_root)
            candidates.add(rel)
    
    # Apply include/exclude filter
    for rel in candidates:
        if should_include_file(rel, policy):
            included.append(rel)
    
    # Sort deterministically
    included.sort(key=lambda p: p.as_posix())
    
    # Apply max_files cap
    if len(included) > policy.max_files:
        included = included[:policy.max_files]
    
    return included


def write_local_scan_rules(
    policy: LocalScanPolicy,
    output_path: Path,
    repo_root: Optional[Path] = None,
) -> Path:
    """
    Write LOCAL_SCAN_RULES.json with policy and metadata.
    
    Args:
        policy: The scan policy to serialize.
        output_path: Where to write the JSON file.
        repo_root: Optional repo root for computing relative paths.
    
    Returns:
        Path to the written file.
    """
    import datetime
    
    data = {
        "mode": "local-strict",
        "generated_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "allowed_roots": list(policy.allowed_roots),
        "allowed_root_files_glob": list(policy.allowed_root_files_glob),
        "deny_segments": list(policy.deny_segments),
        "outputs_allow": list(policy.outputs_allow),
        "max_files": policy.max_files,
        "max_bytes": policy.max_bytes,
        "gitignore_respected": policy.gitignore_respected,
    }
    
    if repo_root:
        data["repo_root"] = str(repo_root.absolute())
    
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    
    return output_path


def compute_policy_hash(policy_path: Path) -> str:
    """
    Compute SHA256 hash of LOCAL_SCAN_RULES.json.
    
    Returns "UNKNOWN" if file doesn't exist or can't be read.
    """
    if not policy_path.exists():
        return "UNKNOWN"
    
    try:
        with open(policy_path, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()
    except Exception:
        return "UNKNOWN"


if __name__ == "__main__":
    # Simple test when run directly
    import sys
    repo = Path.cwd()
    policy = default_local_strict_policy()
    files = iter_repo_files_local_strict(repo, policy)
    print(f"Found {len(files)} files with local-strict policy")
    for f in files[:10]:
        print(f"  {f}")
    if len(files) > 10:
        print(f"  ... and {len(files) - 10} more")