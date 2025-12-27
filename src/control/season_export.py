
"""
Phase 15.3: Season freeze package / export pack.

Contracts:
- Controlled mutation: writes only under exports root (default outputs/exports).
- Does NOT modify artifacts/ or season_index/ trees.
- Requires season is frozen (governance hardening).
- Deterministic:
  - batches sorted by batch_id asc
  - manifest files sorted by rel_path asc
- Auditable:
  - package_manifest.json includes sha256 for each exported file
  - includes manifest_sha256 (sha of the manifest bytes)
"""

from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from control.artifacts import compute_sha256, write_atomic_json
from control.season_api import SeasonStore
from control.batch_api import read_summary, read_index
from utils.write_scope import WriteScope


def get_exports_root() -> Path:
    return Path(os.environ.get("FISHBRO_EXPORTS_ROOT", "outputs/exports"))


def _copy_file(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def _file_sha256(path: Path) -> str:
    return compute_sha256(path.read_bytes())


@dataclass(frozen=True)
class ExportResult:
    season: str
    export_dir: Path
    manifest_path: Path
    manifest_sha256: str
    exported_files: list[dict[str, Any]]
    missing_files: list[str]


def export_season_package(
    *,
    season: str,
    artifacts_root: Path,
    season_index_root: Path,
    exports_root: Optional[Path] = None,
) -> ExportResult:
    """
    Export a frozen season into an immutable, auditable package directory.

    Package layout:
      exports/seasons/{season}/
        package_manifest.json
        season_index.json
        season_metadata.json
        batches/{batch_id}/metadata.json
        batches/{batch_id}/index.json (optional if missing)
        batches/{batch_id}/summary.json (optional if missing)
    """
    exports_root = exports_root or get_exports_root()
    store = SeasonStore(season_index_root)

    if not store.is_frozen(season):
        raise PermissionError("Season must be frozen before export")

    # must have season index
    season_index = store.read_index(season)  # FileNotFoundError surfaces to API as 404

    season_dir = exports_root / "seasons" / season
    batches_dir = season_dir / "batches"
    season_dir.mkdir(parents=True, exist_ok=True)
    batches_dir.mkdir(parents=True, exist_ok=True)

    # Build the set of allowed relative paths according to export‑pack spec.
    # We'll collect them as we go, then create a WriteScope that permits exactly those paths.
    allowed_rel_files: set[str] = set()
    exported_files: list[dict[str, Any]] = []
    missing: list[str] = []

    # Helper to record an allowed file and copy it
    def copy_and_allow(src: Path, dst: Path, rel: str) -> None:
        _copy_file(src, dst)
        allowed_rel_files.add(rel)
        exported_files.append({"path": rel, "sha256": _file_sha256(dst)})

    # 1) copy season_index.json + season_metadata.json (metadata may not exist; if missing -> we still record missing)
    src_index = season_index_root / season / "season_index.json"
    dst_index = season_dir / "season_index.json"
    copy_and_allow(src_index, dst_index, "season_index.json")

    src_meta = season_index_root / season / "season_metadata.json"
    dst_meta = season_dir / "season_metadata.json"
    if src_meta.exists():
        copy_and_allow(src_meta, dst_meta, "season_metadata.json")
    else:
        missing.append("season_metadata.json")

    # 2) copy batch files referenced by season index
    batches = season_index.get("batches", [])
    if not isinstance(batches, list):
        raise ValueError("season_index.batches must be a list")

    batch_ids = sorted(
        {str(b["batch_id"]) for b in batches if isinstance(b, dict) and "batch_id" in b}
    )

    for batch_id in batch_ids:
        # metadata.json is the anchor
        src_batch_meta = artifacts_root / batch_id / "metadata.json"
        rel_meta = str(Path("batches") / batch_id / "metadata.json")
        dst_batch_meta = batches_dir / batch_id / "metadata.json"
        if src_batch_meta.exists():
            copy_and_allow(src_batch_meta, dst_batch_meta, rel_meta)
        else:
            missing.append(rel_meta)

        # index.json optional
        src_idx = artifacts_root / batch_id / "index.json"
        rel_idx = str(Path("batches") / batch_id / "index.json")
        dst_idx = batches_dir / batch_id / "index.json"
        if src_idx.exists():
            copy_and_allow(src_idx, dst_idx, rel_idx)
        else:
            missing.append(rel_idx)

        # summary.json optional
        src_sum = artifacts_root / batch_id / "summary.json"
        rel_sum = str(Path("batches") / batch_id / "summary.json")
        dst_sum = batches_dir / batch_id / "summary.json"
        if src_sum.exists():
            copy_and_allow(src_sum, dst_sum, rel_sum)
        else:
            missing.append(rel_sum)

    # 3) build deterministic manifest (sort by path)
    exported_files_sorted = sorted(exported_files, key=lambda x: x["path"])

    manifest_obj = {
        "season": season,
        "generated_at": season_index.get("generated_at", ""),
        "source_roots": {
            "artifacts_root": str(artifacts_root),
            "season_index_root": str(season_index_root),
        },
        "deterministic_order": {
            "batches": "batch_id asc",
            "files": "path asc",
        },
        "files": exported_files_sorted,
        "missing_files": sorted(set(missing)),
    }

    manifest_path = season_dir / "package_manifest.json"
    allowed_rel_files.add("package_manifest.json")
    write_atomic_json(manifest_path, manifest_obj)

    manifest_sha256 = compute_sha256(manifest_path.read_bytes())

    # write back manifest hash (2nd pass) for self-audit (still deterministic because it depends on bytes)
    manifest_obj2 = dict(manifest_obj)
    manifest_obj2["manifest_sha256"] = manifest_sha256
    write_atomic_json(manifest_path, manifest_obj2)
    manifest_sha2562 = compute_sha256(manifest_path.read_bytes())

    # 4) create replay_index.json for compare replay without artifacts
    replay_index_path = season_dir / "replay_index.json"
    allowed_rel_files.add("replay_index.json")
    replay_index = _build_replay_index(
        season=season,
        season_index=season_index,
        artifacts_root=artifacts_root,
        batches_dir=batches_dir,
    )
    write_atomic_json(replay_index_path, replay_index)
    exported_files_sorted.append(
        {
            "path": str(Path("replay_index.json")),
            "sha256": _file_sha256(replay_index_path),
        }
    )

    # Now create a WriteScope that permits exactly the files we have written.
    # This scope will be used to validate any future writes (none in this function).
    # We also add a guard for the manifest write (already done) and replay_index write.
    scope = WriteScope(
        root_dir=season_dir,
        allowed_rel_files=frozenset(allowed_rel_files),
        allowed_rel_prefixes=(),
    )
    # Verify that all exported files are allowed (should be true by construction)
    for ef in exported_files_sorted:
        scope.assert_allowed_rel(ef["path"])

    return ExportResult(
        season=season,
        export_dir=season_dir,
        manifest_path=manifest_path,
        manifest_sha256=manifest_sha2562,
        exported_files=exported_files_sorted,
        missing_files=sorted(set(missing)),
    )


def _build_replay_index(
    season: str,
    season_index: dict[str, Any],
    artifacts_root: Path,
    batches_dir: Path,
) -> dict[str, Any]:
    """
    Build replay index for compare replay without artifacts.
    
    Contains:
    - season metadata
    - batch summaries (topk, metrics)
    - batch indices (job list)
    - deterministic ordering
    """
    batches = season_index.get("batches", [])
    if not isinstance(batches, list):
        raise ValueError("season_index.batches must be a list")

    batch_ids = sorted(
        {str(b["batch_id"]) for b in batches if isinstance(b, dict) and "batch_id" in b}
    )

    replay_batches: list[dict[str, Any]] = []
    for batch_id in batch_ids:
        batch_info: dict[str, Any] = {"batch_id": batch_id}
        
        # Try to read summary.json
        summary_path = artifacts_root / batch_id / "summary.json"
        if summary_path.exists():
            try:
                summary = read_summary(artifacts_root, batch_id)
                batch_info["summary"] = {
                    "topk": summary.get("topk", []),
                    "metrics": summary.get("metrics", {}),
                }
            except Exception:
                batch_info["summary"] = None
        else:
            batch_info["summary"] = None
        
        # Try to read index.json
        index_path = artifacts_root / batch_id / "index.json"
        if index_path.exists():
            try:
                index = read_index(artifacts_root, batch_id)
                batch_info["index"] = index
            except Exception:
                batch_info["index"] = None
        else:
            batch_info["index"] = None
        
        replay_batches.append(batch_info)

    return {
        "season": season,
        "generated_at": season_index.get("generated_at", ""),
        "batches": replay_batches,
        "deterministic_order": {
            "batches": "batch_id asc",
            "files": "path asc",
        },
    }


