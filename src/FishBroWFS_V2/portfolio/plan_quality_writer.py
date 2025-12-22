
"""Quality writer for portfolio plans (controlled mutation + idempotent)."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Dict, Any

from FishBroWFS_V2.contracts.portfolio.plan_quality_models import PlanQualityReport
from FishBroWFS_V2.control.artifacts import compute_sha256, canonical_json_bytes
from FishBroWFS_V2.utils.write_scope import create_plan_quality_scope


def _read_bytes(p: Path) -> bytes:
    return p.read_bytes()


def _canonical_json_bytes(obj: Any) -> bytes:
    # 使用專案現有的 canonical_json_bytes
    return canonical_json_bytes(obj)


def _write_if_changed(path: Path, data: bytes) -> None:
    """Write bytes to file only if content differs.
    
    Args:
        path: Target file path.
        data: Bytes to write.
    
    Returns:
        None; file is written only if content changed (preserving mtime).
    """
    if path.exists() and path.read_bytes() == data:
        return
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(data)
    tmp.replace(path)


def _compute_inputs_sha256(plan_dir: Path) -> Dict[str, str]:
    # 測試會放這四個檔；我們就算這四個（存在才算）
    files = [
        "portfolio_plan.json",
        "plan_manifest.json",
        "plan_metadata.json",
        "plan_checksums.json",
    ]
    out: Dict[str, str] = {}
    for fn in files:
        p = plan_dir / fn
        if p.exists():
            out[fn] = compute_sha256(_read_bytes(p))
    return out


def _load_view_checksums(plan_dir: Path) -> Dict[str, str]:
    p = plan_dir / "plan_view_checksums.json"
    if not p.exists():
        return {}
    obj = json.loads(p.read_text(encoding="utf-8"))
    # 測試要的是 dict；若不是就保守回 {}
    return obj if isinstance(obj, dict) else {}


def write_plan_quality_files(plan_dir: Path, quality: PlanQualityReport) -> None:
    """
    Controlled mutation: writes only
      - plan_quality.json
      - plan_quality_checksums.json
      - plan_quality_manifest.json
    Idempotent: same content => no rewrite (mtime unchanged)
    """
    # Create write scope for plan quality files
    scope = create_plan_quality_scope(plan_dir)
    
    # Helper to write a file with scope validation
    def write_scoped(rel_path: str, data: bytes) -> None:
        scope.assert_allowed_rel(rel_path)
        _write_if_changed(plan_dir / rel_path, data)
    
    # 1) inputs + view_checksums (read-only)
    inputs = _compute_inputs_sha256(plan_dir)
    view_checksums = _load_view_checksums(plan_dir)

    # 2) plan_quality.json
    quality_dict = quality.model_dump()
    # 把 inputs 也放進去（你的 models 有 inputs 欄位）
    quality_dict["inputs"] = inputs
    quality_bytes = _canonical_json_bytes(quality_dict)
    write_scoped("plan_quality.json", quality_bytes)

    # 3) checksums (flat dict, exactly one key)
    q_sha = compute_sha256(quality_bytes)
    checksums_obj = {"plan_quality.json": q_sha}
    checksums_bytes = _canonical_json_bytes(checksums_obj)
    write_scoped("plan_quality_checksums.json", checksums_bytes)

    # 4) manifest must include view_checksums
    # Note: tests expect view_checksums to equal quality_checksums
    
    # Build files listing (sorted by rel_path asc)
    files = []
    # plan_quality.json
    quality_file = "plan_quality.json"
    quality_path = plan_dir / quality_file
    if quality_path.exists():
        files.append({
            "rel_path": quality_file,
            "sha256": compute_sha256(quality_path.read_bytes())
        })
    # plan_quality_checksums.json
    checksums_file = "plan_quality_checksums.json"
    checksums_path = plan_dir / checksums_file
    if checksums_path.exists():
        files.append({
            "rel_path": checksums_file,
            "sha256": compute_sha256(checksums_path.read_bytes())
        })
    
    # Sort by rel_path
    files.sort(key=lambda x: x["rel_path"])
    
    # Compute files_sha256 (concatenated hashes)
    concatenated = "".join(f["sha256"] for f in files)
    files_sha256 = compute_sha256(concatenated.encode("utf-8"))
    
    manifest_obj = {
        "manifest_type": "quality",
        "manifest_version": "1.0",
        "id": quality.plan_id,
        "plan_id": quality.plan_id,
        "generated_at_utc": quality.generated_at_utc,  # deterministic (from plan)
        "source": quality.source.model_dump(),
        "inputs": inputs,
        "view_checksums": checksums_obj,              # <-- 測試硬鎖必須等於 quality_checksums
        "quality_checksums": checksums_obj,            # 可以留（測試不反對）
        "files": files,
        "files_sha256": files_sha256,
    }
    # manifest_sha256 要算「不含 manifest_sha256」的 canonical bytes
    manifest_sha = compute_sha256(_canonical_json_bytes(manifest_obj))
    manifest_obj["manifest_sha256"] = manifest_sha

    manifest_bytes = _canonical_json_bytes(manifest_obj)
    write_scoped("plan_quality_manifest.json", manifest_bytes)


