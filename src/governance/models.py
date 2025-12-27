#!/usr/bin/env python3
"""
Governance data models for Season Freeze (Phase 3B).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional


@dataclass(frozen=True)
class SeasonManifest:
    """
    Immutable snapshot of a research season.

    Once frozen, the manifest must never be modified. Any change requires a new season.
    """

    # Identification
    season_id: str  # e.g., "2026Q1_abc123"
    timestamp: str  # ISO 8601 UTC freeze time

    # Ground references (hashes of immutable inputs)
    universe_ref: str  # SHA256 of universe definition (universe.yaml)
    dataset_ref: str  # SHA256 of derived dataset registry entry (dataset.json)
    strategy_spec_hash: str  # SHA256 of strategy spec (strategy_spec.json) or content-addressed ID
    plateau_ref: str  # SHA256 of plateau_report.json
    engine_version: str  # Git commit hash or version tag

    # Chosen parameters (copy of selected main/backup)
    chosen_params_snapshot: Dict[str, Any]  # keys: "main", "backups"

    # Optional metadata
    notes: str = ""
    tags: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        d = asdict(self)
        # Ensure deterministic ordering of tags
        if "tags" in d:
            d["tags"] = sorted(d["tags"])
        return d

    def to_json(self, indent: int = 2) -> str:
        """Return JSON string with deterministic key order."""
        import json
        return json.dumps(self.to_dict(), indent=indent, sort_keys=True, ensure_ascii=False)

    def save(self, path: Path) -> None:
        """Save manifest to file (atomic write)."""
        temp = path.with_suffix(".tmp")
        temp.write_text(self.to_json(), encoding="utf-8")
        temp.replace(path)

    @classmethod
    def load(cls, path: Path) -> SeasonManifest:
        """Load manifest from file."""
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls(**data)

    @classmethod
    def compute_file_hash(cls, path: Path) -> str:
        """Compute SHA256 hash of a file."""
        sha256 = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                sha256.update(chunk)
        return sha256.hexdigest()

    @classmethod
    def compute_dict_hash(cls, obj: Dict[str, Any]) -> str:
        """Compute SHA256 hash of a dict using stable JSON serialization."""
        json_str = json.dumps(obj, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(json_str.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class FreezeContext:
    """All inputs required to freeze a season."""

    # Paths to referenced files (must exist)
    universe_path: Path
    dataset_registry_path: Path
    strategy_spec_path: Path
    plateau_report_path: Path
    chosen_params_path: Path

    # Engine version (commit hash)
    engine_version: str

    # Optional
    season_id: Optional[str] = None
    notes: str = ""

    def compute_hashes(self) -> Dict[str, str]:
        """Compute SHA256 hashes of all referenced files."""
        return {
            "universe": self.compute_file_hash(self.universe_path),
            "dataset": self.compute_file_hash(self.dataset_registry_path),
            "strategy_spec": self.compute_file_hash(self.strategy_spec_path),
            "plateau": self.compute_file_hash(self.plateau_report_path),
        }

    def compute_file_hash(self, path: Path) -> str:
        return SeasonManifest.compute_file_hash(path)