"""Batch metadata and governance for Phase 14.

Season/tags/note/frozen metadata with immutable rules.

CRITICAL CONTRACTS:
- Metadata MUST live under: artifacts/{batch_id}/metadata.json
  (so a batch folder is fully portable for audit/replay/archive).
- Writes MUST be atomic (tmp + replace) to avoid corrupt JSON on crash.
- Tag handling MUST be deterministic (dedupe + sort).
- Corrupted metadata MUST NOT be silently treated as "not found".
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from FishBroWFS_V2.control.artifacts import write_json_atomic


def _utc_now_iso() -> str:
    # Seconds precision, UTC, Z suffix
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


@dataclass
class BatchMetadata:
    """Batch metadata (mutable only before frozen)."""
    batch_id: str
    season: str = ""
    tags: list[str] = field(default_factory=list)
    note: str = ""
    frozen: bool = False
    created_at: str = ""
    updated_at: str = ""
    created_by: str = ""


class BatchGovernanceStore:
    """Persistent store for batch metadata.

    Store root MUST be the artifacts root.
    Metadata path:
      {artifacts_root}/{batch_id}/metadata.json
    """

    def __init__(self, artifacts_root: Path):
        self.artifacts_root = artifacts_root
        self.artifacts_root.mkdir(parents=True, exist_ok=True)

    def _metadata_path(self, batch_id: str) -> Path:
        return self.artifacts_root / batch_id / "metadata.json"

    def get_metadata(self, batch_id: str) -> Optional[BatchMetadata]:
        path = self._metadata_path(batch_id)
        if not path.exists():
            return None

        # Do NOT swallow corruption; let callers handle it explicitly.
        data = json.loads(path.read_text(encoding="utf-8"))

        tags = data.get("tags", [])
        if not isinstance(tags, list):
            raise ValueError("metadata.tags must be a list")

        return BatchMetadata(
            batch_id=data["batch_id"],
            season=data.get("season", ""),
            tags=list(tags),
            note=data.get("note", ""),
            frozen=bool(data.get("frozen", False)),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
            created_by=data.get("created_by", ""),
        )

    def set_metadata(self, batch_id: str, metadata: BatchMetadata) -> None:
        path = self._metadata_path(batch_id)
        path.parent.mkdir(parents=True, exist_ok=True)

        payload = {
            "batch_id": batch_id,
            "season": metadata.season,
            "tags": list(metadata.tags),
            "note": metadata.note,
            "frozen": bool(metadata.frozen),
            "created_at": metadata.created_at,
            "updated_at": metadata.updated_at,
            "created_by": metadata.created_by,
        }
        write_json_atomic(path, payload)

    def is_frozen(self, batch_id: str) -> bool:
        meta = self.get_metadata(batch_id)
        return bool(meta and meta.frozen)

    def update_metadata(
        self,
        batch_id: str,
        *,
        season: Optional[str] = None,
        tags: Optional[list[str]] = None,
        note: Optional[str] = None,
        frozen: Optional[bool] = None,
        created_by: str = "system",
    ) -> BatchMetadata:
        """Update metadata fields (enforcing frozen rules).

        Frozen rules:
        - If batch is frozen:
          - season cannot change
          - frozen cannot be set to False
          - tags can be appended (dedupe + sort)
          - note can change
          - frozen=True again is a no-op
        """
        existing = self.get_metadata(batch_id)
        now = _utc_now_iso()

        if existing is None:
            existing = BatchMetadata(
                batch_id=batch_id,
                season="",
                tags=[],
                note="",
                frozen=False,
                created_at=now,
                updated_at=now,
                created_by=created_by,
            )

        if existing.frozen:
            if season is not None and season != existing.season:
                raise ValueError("Cannot change season of frozen batch")
            if frozen is False:
                raise ValueError("Cannot unfreeze a frozen batch")

        # Apply changes
        if (season is not None) and (not existing.frozen):
            existing.season = season

        if tags is not None:
            merged = set(existing.tags)
            merged.update(tags)
            existing.tags = sorted(merged)

        if note is not None:
            existing.note = note

        if frozen is not None:
            if frozen is True:
                existing.frozen = True
            elif frozen is False:
                # allowed only when not frozen (blocked above if frozen)
                existing.frozen = False

        existing.updated_at = now
        self.set_metadata(batch_id, existing)
        return existing

    def freeze(self, batch_id: str) -> None:
        """Freeze a batch (irreversible).

        Raises:
            ValueError: If batch metadata not found.
        """
        meta = self.get_metadata(batch_id)
        if meta is None:
            raise ValueError(f"Batch {batch_id} not found")

        if not meta.frozen:
            meta.frozen = True
            meta.updated_at = _utc_now_iso()
            self.set_metadata(batch_id, meta)

    def list_batches(
        self,
        *,
        season: Optional[str] = None,
        tag: Optional[str] = None,
        frozen: Optional[bool] = None,
    ) -> list[BatchMetadata]:
        """List batches matching filters.

        Scans artifacts root for {batch_id}/metadata.json.

        Deterministic ordering:
        - Sort by batch_id.
        """
        results: list[BatchMetadata] = []
        for batch_dir in sorted([p for p in self.artifacts_root.iterdir() if p.is_dir()], key=lambda p: p.name):
            meta_path = batch_dir / "metadata.json"
            if not meta_path.exists():
                continue
            meta = self.get_metadata(batch_dir.name)
            if meta is None:
                continue
            if season is not None and meta.season != season:
                continue
            if tag is not None and tag not in set(meta.tags):
                continue
            if frozen is not None and bool(meta.frozen) != bool(frozen):
                continue
            results.append(meta)
        return results
