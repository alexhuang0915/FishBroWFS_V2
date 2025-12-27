#!/usr/bin/env python3
"""
Season Freeze – Phase 3B.

Freeze a research cycle into an immutable Season Manifest.
"""

from __future__ import annotations

import json
import hashlib
import tempfile
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, Optional

from .models import SeasonManifest, FreezeContext


class SeasonAlreadyFrozenError(RuntimeError):
    """Raised when attempting to freeze a season that already exists."""
    pass


def freeze_season(
    ctx: FreezeContext,
    outputs_root: Path = Path("outputs"),
    force: bool = False,
) -> SeasonManifest:
    """
    Freeze a season, producing an immutable manifest.

    Args:
        ctx: FreezeContext with all required input paths and version.
        outputs_root: Root directory where seasons are stored.
        force: If True, allow overwriting an existing season (dangerous).

    Returns:
        SeasonManifest instance.

    Raises:
        SeasonAlreadyFrozenError: If season_id already exists and force is False.
        FileNotFoundError: If any referenced input file is missing.
        ValueError: If any hash cannot be computed.
    """
    # Validate input files exist
    for name, path in [
        ("universe", ctx.universe_path),
        ("dataset_registry", ctx.dataset_registry_path),
        ("strategy_spec", ctx.strategy_spec_path),
        ("plateau_report", ctx.plateau_report_path),
        ("chosen_params", ctx.chosen_params_path),
    ]:
        if not path.exists():
            raise FileNotFoundError(f"Required input file missing: {name} at {path}")

    # Compute hashes
    hashes = ctx.compute_hashes()

    # Load chosen_params snapshot
    chosen_params = json.loads(ctx.chosen_params_path.read_text(encoding="utf-8"))

    # Determine season_id
    if ctx.season_id is None:
        # Generate deterministic ID from hash of combined inputs
        combined = "|".join(sorted(hashes.values()))
        season_id = hashlib.sha256(combined.encode("utf-8")).hexdigest()[:12]
        season_id = f"season_{season_id}"
    else:
        season_id = ctx.season_id

    # Check if season already exists
    season_dir = outputs_root / "seasons" / season_id
    manifest_path = season_dir / "season_manifest.json"
    if manifest_path.exists() and not force:
        raise SeasonAlreadyFrozenError(
            f"Season '{season_id}' already frozen at {manifest_path}. "
            "Use --force to overwrite (not recommended)."
        )

    # Create season directory
    season_dir.mkdir(parents=True, exist_ok=True)

    # Freeze timestamp
    timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    # Build manifest
    manifest = SeasonManifest(
        season_id=season_id,
        timestamp=timestamp,
        universe_ref=hashes["universe"],
        dataset_ref=hashes["dataset"],
        strategy_spec_hash=hashes["strategy_spec"],
        plateau_ref=hashes["plateau"],
        engine_version=ctx.engine_version,
        chosen_params_snapshot=chosen_params,
        notes=ctx.notes,
    )

    # Write manifest (atomic)
    manifest.save(manifest_path)

    # Copy referenced files into season directory for audit (optional)
    _copy_reference_files(ctx, season_dir)

    print(f"Season frozen: {season_id}")
    print(f"  manifest: {manifest_path}")
    print(f"  universe hash: {hashes['universe'][:16]}...")
    print(f"  dataset hash: {hashes['dataset'][:16]}...")
    print(f"  strategy spec hash: {hashes['strategy_spec'][:16]}...")
    print(f"  plateau hash: {hashes['plateau'][:16]}...")
    print(f"  engine version: {ctx.engine_version}")

    return manifest


def _copy_reference_files(ctx: FreezeContext, season_dir: Path) -> None:
    """Copy referenced input files into season directory for audit trail."""
    refs_dir = season_dir / "references"
    refs_dir.mkdir(exist_ok=True)

    mapping = {
        "universe.yaml": ctx.universe_path,
        "dataset_registry.json": ctx.dataset_registry_path,
        "strategy_spec.json": ctx.strategy_spec_path,
        "plateau_report.json": ctx.plateau_report_path,
        "chosen_params.json": ctx.chosen_params_path,
    }

    for dest_name, src_path in mapping.items():
        dest = refs_dir / dest_name
        if src_path.exists():
            shutil.copy2(src_path, dest)


def load_season_manifest(season_id: str, outputs_root: Path = Path("outputs")) -> SeasonManifest:
    """Load a frozen season manifest."""
    manifest_path = outputs_root / "seasons" / season_id / "season_manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"No frozen season found with id '{season_id}'")
    return SeasonManifest.load(manifest_path)


def list_frozen_seasons(outputs_root: Path = Path("outputs")) -> Dict[str, Path]:
    """Return mapping of season_id -> manifest path for all frozen seasons."""
    seasons_dir = outputs_root / "seasons"
    if not seasons_dir.exists():
        return {}

    mapping = {}
    for subdir in seasons_dir.iterdir():
        if subdir.is_dir():
            manifest = subdir / "season_manifest.json"
            if manifest.exists():
                mapping[subdir.name] = manifest
    return mapping