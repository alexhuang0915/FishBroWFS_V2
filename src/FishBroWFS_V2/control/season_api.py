"""
Phase 15.0: Season-level governance and index builder (Research OS).

Contracts:
- Do NOT modify Engine / JobSpec / batch artifacts content.
- Season index is a separate tree (season_index/{season}/...).
- Rebuild index is deterministic: stable ordering by batch_id.
- Only reads JSON from artifacts/{batch_id}/metadata.json, index.json, summary.json.
- Writes season_index.json and season_metadata.json using atomic write.

Environment overrides:
- FISHBRO_SEASON_INDEX_ROOT (default: outputs/season_index)
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from FishBroWFS_V2.control.artifacts import compute_sha256, write_json_atomic


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def get_season_index_root() -> Path:
    import os
    return Path(os.environ.get("FISHBRO_SEASON_INDEX_ROOT", "outputs/season_index"))


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(str(path))
    return json.loads(path.read_text(encoding="utf-8"))


def _file_sha256(path: Path) -> Optional[str]:
    if not path.exists():
        return None
    return compute_sha256(path.read_bytes())


@dataclass
class SeasonMetadata:
    season: str
    frozen: bool = False
    tags: list[str] = field(default_factory=list)
    note: str = ""
    created_at: str = ""
    updated_at: str = ""


class SeasonStore:
    """
    Store for season_index/{season}/season_index.json and season_metadata.json
    """

    def __init__(self, season_index_root: Path):
        self.root = season_index_root
        self.root.mkdir(parents=True, exist_ok=True)

    def season_dir(self, season: str) -> Path:
        return self.root / season

    def index_path(self, season: str) -> Path:
        return self.season_dir(season) / "season_index.json"

    def metadata_path(self, season: str) -> Path:
        return self.season_dir(season) / "season_metadata.json"

    # ---------- metadata ----------
    def get_metadata(self, season: str) -> Optional[SeasonMetadata]:
        path = self.metadata_path(season)
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        tags = data.get("tags", [])
        if not isinstance(tags, list):
            raise ValueError("season_metadata.tags must be a list")
        return SeasonMetadata(
            season=data["season"],
            frozen=bool(data.get("frozen", False)),
            tags=list(tags),
            note=data.get("note", ""),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
        )

    def set_metadata(self, season: str, meta: SeasonMetadata) -> None:
        path = self.metadata_path(season)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "season": season,
            "frozen": bool(meta.frozen),
            "tags": list(meta.tags),
            "note": meta.note,
            "created_at": meta.created_at,
            "updated_at": meta.updated_at,
        }
        write_json_atomic(path, payload)

    def update_metadata(
        self,
        season: str,
        *,
        tags: Optional[list[str]] = None,
        note: Optional[str] = None,
        frozen: Optional[bool] = None,
    ) -> SeasonMetadata:
        now = _utc_now_iso()
        existing = self.get_metadata(season)
        if existing is None:
            existing = SeasonMetadata(season=season, created_at=now, updated_at=now)

        if existing.frozen and frozen is False:
            raise ValueError("Cannot unfreeze a frozen season")

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
                # allowed only when not already frozen
                existing.frozen = False

        existing.updated_at = now
        self.set_metadata(season, existing)
        return existing

    def freeze(self, season: str) -> None:
        meta = self.get_metadata(season)
        if meta is None:
            # create metadata on freeze if it doesn't exist
            now = _utc_now_iso()
            meta = SeasonMetadata(season=season, created_at=now, updated_at=now, frozen=True)
            self.set_metadata(season, meta)
            return

        if not meta.frozen:
            meta.frozen = True
            meta.updated_at = _utc_now_iso()
            self.set_metadata(season, meta)

    def is_frozen(self, season: str) -> bool:
        meta = self.get_metadata(season)
        return bool(meta and meta.frozen)

    # ---------- index ----------
    def read_index(self, season: str) -> dict[str, Any]:
        return _read_json(self.index_path(season))

    def write_index(self, season: str, index_obj: dict[str, Any]) -> None:
        path = self.index_path(season)
        path.parent.mkdir(parents=True, exist_ok=True)
        write_json_atomic(path, index_obj)

    def rebuild_index(self, artifacts_root: Path, season: str) -> dict[str, Any]:
        """
        Scan artifacts_root/*/metadata.json to collect batches where metadata.season == season.
        Then attach hashes for index.json and summary.json (if present).
        Deterministic: sort by batch_id.
        """
        if not artifacts_root.exists():
            # no artifacts root -> empty index
            artifacts_root.mkdir(parents=True, exist_ok=True)

        batches: list[dict[str, Any]] = []

        # deterministic: sorted by directory name
        for batch_dir in sorted([p for p in artifacts_root.iterdir() if p.is_dir()], key=lambda p: p.name):
            batch_id = batch_dir.name
            meta_path = batch_dir / "metadata.json"
            if not meta_path.exists():
                continue

            # Do NOT swallow corruption: index build should surface errors
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            if meta.get("season", "") != season:
                continue

            idx_hash = _file_sha256(batch_dir / "index.json")
            sum_hash = _file_sha256(batch_dir / "summary.json")

            batches.append(
                {
                    "batch_id": batch_id,
                    "frozen": bool(meta.get("frozen", False)),
                    "tags": sorted(set(meta.get("tags", []) or [])),
                    "note": meta.get("note", "") or "",
                    "index_hash": idx_hash,
                    "summary_hash": sum_hash,
                }
            )

        out = {
            "season": season,
            "generated_at": _utc_now_iso(),
            "batches": batches,
        }
        self.write_index(season, out)
        return out