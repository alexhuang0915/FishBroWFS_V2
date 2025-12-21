"""
Dataset registry mutation (controlled mutation) for snapshot registration.

Phase 16.5‑B: Append‑only (or controlled mutation) registry updates.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from FishBroWFS_V2.contracts.data.snapshot_models import SnapshotMetadata
from FishBroWFS_V2.data.dataset_registry import DatasetIndex, DatasetRecord


def _get_dataset_registry_root() -> Path:
    """
    Return dataset registry root directory.

    Environment override:
      - FISHBRO_DATASET_REGISTRY_ROOT (default: outputs/datasets)
    """
    import os
    return Path(os.environ.get("FISHBRO_DATASET_REGISTRY_ROOT", "outputs/datasets"))


def _compute_dataset_id(symbol: str, timeframe: str, normalized_sha256: str) -> str:
    """
    Deterministic dataset ID for a snapshot.

    Format: snapshot_{symbol}_{timeframe}_{normalized_sha256[:12]}
    """
    symbol_norm = symbol.replace("/", "_").upper()
    tf_norm = timeframe.replace("/", "_").lower()
    return f"snapshot_{symbol_norm}_{tf_norm}_{normalized_sha256[:12]}"


def register_snapshot_as_dataset(
    snapshot_dir: Path,
    registry_root: Optional[Path] = None,
) -> DatasetRecord:
    """
    Append‑only registration of a snapshot as a dataset.

    Args:
        snapshot_dir: Path to snapshot directory (contains manifest.json)
        registry_root: Optional root directory for dataset registry.
                       Defaults to _get_dataset_registry_root().

    Returns:
        DatasetEntry for the newly registered dataset.

    Raises:
        FileNotFoundError: If manifest.json missing.
        ValueError: If snapshot already registered.
    """
    # Load manifest
    manifest_path = snapshot_dir / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"manifest.json not found in {snapshot_dir}")

    manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
    meta = SnapshotMetadata.model_validate(manifest_data)

    # Determine registry path
    if registry_root is None:
        registry_root = _get_dataset_registry_root()
    registry_path = registry_root / "datasets_index.json"

    # Ensure parent directory exists
    registry_path.parent.mkdir(parents=True, exist_ok=True)

    # Load existing registry or create empty
    if registry_path.exists():
        data = json.loads(registry_path.read_text(encoding="utf-8"))
        existing_index = DatasetIndex.model_validate(data)
    else:
        existing_index = DatasetIndex(
            generated_at=datetime.now(timezone.utc).replace(microsecond=0),
            datasets=[],
        )

    # Compute deterministic dataset ID
    dataset_id = _compute_dataset_id(meta.symbol, meta.timeframe, meta.normalized_sha256)

    # Check for duplicate (conflict)
    for rec in existing_index.datasets:
        if rec.id == dataset_id:
            raise ValueError(f"Snapshot {meta.snapshot_id} already registered as dataset {dataset_id}")

    # Build DatasetEntry
    # Use stats for start/end timestamps
    start_date = datetime.fromisoformat(meta.stats.min_timestamp.replace("Z", "+00:00")).date()
    end_date = datetime.fromisoformat(meta.stats.max_timestamp.replace("Z", "+00:00")).date()

    # Path relative to datasets root (snapshots/{snapshot_id}/normalized.json)
    rel_path = f"snapshots/{meta.snapshot_id}/normalized.json"

    entry = DatasetRecord(
        id=dataset_id,
        symbol=meta.symbol,
        exchange=meta.symbol.split(".")[0] if "." in meta.symbol else "UNKNOWN",
        timeframe=meta.timeframe,
        path=rel_path,
        start_date=start_date,
        end_date=end_date,
        fingerprint_sha1=meta.normalized_sha256[:40],  # SHA1 length is 40 hex chars
        tz_provider="UTC",
        tz_version="unknown",
    )

    # Append new record
    updated_datasets = existing_index.datasets + [entry]
    # Sort by id to maintain deterministic order
    updated_datasets.sort(key=lambda d: d.id)

    # Create updated index with new generation timestamp
    updated_index = DatasetIndex(
        generated_at=datetime.now(timezone.utc).replace(microsecond=0),
        datasets=updated_datasets,
    )

    # Write back atomically (write to temp file then rename)
    temp_path = registry_path.with_suffix(".tmp")
    temp_path.write_text(
        json.dumps(
            updated_index.model_dump(mode="json"),
            sort_keys=True,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    temp_path.replace(registry_path)

    return entry