
"""
Phase 16.5: Data Snapshot Core (controlled mutation, deterministic).

Contracts:
- Writes only under outputs/datasets/snapshots/{snapshot_id}/
- Deterministic normalization & checksums
- Immutable snapshots (never overwrite)
- Timezone‑aware UTC timestamps
"""

from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from contracts.data.snapshot_models import SnapshotMetadata, SnapshotStats
from control.artifacts import canonical_json_bytes, compute_sha256, write_atomic_json


def write_json_atomic_any(path: Path, obj: Any) -> None:
    """
    Atomically write any JSON‑serializable object to file.

    Uses the same atomic rename technique as write_atomic_json.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.tmp.",
        delete=False,
    ) as f:
        json.dump(
            obj,
            f,
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        )
        tmp_path = Path(f.name)
    try:
        tmp_path.replace(path)
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise


def compute_snapshot_id(
    raw_bars: list[dict[str, Any]],
    symbol: str,
    timeframe: str,
    transform_version: str = "v1",
) -> str:
    """
    Deterministic snapshot identifier.

    Format: {symbol}_{timeframe}_{raw_sha256[:12]}_{transform_version}
    """
    # Compute raw SHA256 from canonical JSON of raw_bars
    raw_canonical = canonical_json_bytes(raw_bars)
    raw_sha256 = compute_sha256(raw_canonical)
    raw_prefix = raw_sha256[:12]

    # Normalize symbol and timeframe (remove special chars)
    symbol_norm = symbol.replace("/", "_").upper()
    tf_norm = timeframe.replace("/", "_").lower()
    return f"{symbol_norm}_{tf_norm}_{raw_prefix}_{transform_version}"


def normalize_bars(
    raw_bars: list[dict[str, Any]],
    transform_version: str = "v1",
) -> tuple[list[dict[str, Any]], str]:
    """
    Normalize raw bars to canonical form (deterministic).

    Returns:
        (normalized_bars, normalized_sha256)
    """
    # Ensure each bar has required fields
    required = {"timestamp", "open", "high", "low", "close", "volume"}
    normalized = []
    for bar in raw_bars:
        # Validate types
        ts = bar["timestamp"]
        # Ensure timestamp is ISO 8601 string; if not, attempt conversion
        if isinstance(ts, datetime):
            ts = ts.isoformat().replace("+00:00", "Z")
        elif not isinstance(ts, str):
            raise ValueError(f"Invalid timestamp type: {type(ts)}")

        # Ensure numeric fields are float
        open_ = float(bar["open"])
        high = float(bar["high"])
        low = float(bar["low"])
        close = float(bar["close"])
        volume = float(bar["volume"]) if isinstance(bar["volume"], (int, float)) else 0.0

        # Build canonical dict with fixed key order
        canonical = {
            "timestamp": ts,
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
        }
        normalized.append(canonical)

    # Sort by timestamp ascending
    normalized.sort(key=lambda b: b["timestamp"])

    # Compute SHA256 of canonical JSON
    canonical_bytes = canonical_json_bytes(normalized)
    sha = compute_sha256(canonical_bytes)
    return normalized, sha


def compute_stats(normalized_bars: list[dict[str, Any]]) -> SnapshotStats:
    """Compute basic statistics from normalized bars."""
    if not normalized_bars:
        raise ValueError("normalized_bars cannot be empty")

    timestamps = [b["timestamp"] for b in normalized_bars]
    lows = [b["low"] for b in normalized_bars]
    highs = [b["high"] for b in normalized_bars]
    volumes = [b["volume"] for b in normalized_bars]

    return SnapshotStats(
        count=len(normalized_bars),
        min_timestamp=min(timestamps),
        max_timestamp=max(timestamps),
        min_price=min(lows),
        max_price=max(highs),
        total_volume=sum(volumes),
    )


def create_snapshot(
    snapshots_root: Path,
    raw_bars: list[dict[str, Any]],
    symbol: str,
    timeframe: str,
    transform_version: str = "v1",
) -> SnapshotMetadata:
    """
    Controlled‑mutation: create a data snapshot.

    Writes only under snapshots_root/{snapshot_id}/
    Deterministic normalization & checksums.
    """
    if not raw_bars:
        raise ValueError("raw_bars cannot be empty")

    # 1. Compute raw SHA256
    raw_canonical = canonical_json_bytes(raw_bars)
    raw_sha256 = compute_sha256(raw_canonical)

    # 2. Normalize bars
    normalized_bars, normalized_sha256 = normalize_bars(raw_bars, transform_version)

    # 3. Compute snapshot ID
    snapshot_id = compute_snapshot_id(raw_bars, symbol, timeframe, transform_version)

    # 4. Create snapshot directory (atomic)
    snapshot_dir = snapshots_root / snapshot_id
    if snapshot_dir.exists():
        raise FileExistsError(
            f"Snapshot {snapshot_id} already exists; immutable rule violated"
        )

    # Write files via temporary directory to ensure atomicity
    with tempfile.TemporaryDirectory(prefix=f"snapshot_{snapshot_id}_") as tmp:
        tmp_path = Path(tmp)

        # raw.json
        raw_path = tmp_path / "raw.json"
        write_json_atomic_any(raw_path, raw_bars)

        # normalized.json
        norm_path = tmp_path / "normalized.json"
        write_json_atomic_any(norm_path, normalized_bars)

        # Compute stats
        stats = compute_stats(normalized_bars)

        # manifest.json (without manifest_sha256 field)
        manifest = {
            "snapshot_id": snapshot_id,
            "symbol": symbol,
            "timeframe": timeframe,
            "transform_version": transform_version,
            "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "raw_sha256": raw_sha256,
            "normalized_sha256": normalized_sha256,
            "stats": stats.model_dump(mode="json"),
        }
        manifest_path = tmp_path / "manifest.json"
        write_json_atomic_any(manifest_path, manifest)

        # Compute manifest SHA256 (hash of manifest without manifest_sha256)
        manifest_canonical = canonical_json_bytes(manifest)
        manifest_sha256 = compute_sha256(manifest_canonical)

        # Add manifest_sha256 to manifest
        manifest["manifest_sha256"] = manifest_sha256
        write_json_atomic_any(manifest_path, manifest)

        # Create snapshot directory
        snapshot_dir.mkdir(parents=True, exist_ok=False)

        # Move files into place (atomic rename)
        shutil.move(str(raw_path), str(snapshot_dir / "raw.json"))
        shutil.move(str(norm_path), str(snapshot_dir / "normalized.json"))
        shutil.move(str(manifest_path), str(snapshot_dir / "manifest.json"))

    # Build metadata
    meta = SnapshotMetadata(
        snapshot_id=snapshot_id,
        symbol=symbol,
        timeframe=timeframe,
        transform_version=transform_version,
        created_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        raw_sha256=raw_sha256,
        normalized_sha256=normalized_sha256,
        manifest_sha256=manifest_sha256,
        stats=stats,
    )
    return meta


