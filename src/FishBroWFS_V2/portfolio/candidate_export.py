"""
Phase Portfolio Bridge: Export candidates.json from Research OS.

Exports CandidateSpecs to a deterministic, auditable JSON file
that can be consumed by Market OS without boundary violations.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from FishBroWFS_V2.portfolio.candidate_spec import CandidateSpec, CandidateExport
from FishBroWFS_V2.portfolio.hash_utils import stable_json_dumps


def export_candidates(
    candidates: List[CandidateSpec],
    *,
    export_id: str,
    season: str,
    exports_root: Optional[Path] = None,
) -> Path:
    """
    Export candidates to a deterministic JSON file.
    
    File layout:
        exports/candidates/{season}/{export_id}/candidates.json
        exports/candidates/{season}/{export_id}/manifest.json
    
    Returns:
        Path to the exported candidates.json file
    """
    if exports_root is None:
        exports_root = Path("outputs/exports")
    
    # Create export directory
    export_dir = exports_root / "candidates" / season / export_id
    export_dir.mkdir(parents=True, exist_ok=True)
    
    # Create CandidateExport with timezone-aware timestamp
    generated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat() + "Z"
    candidate_export = CandidateExport(
        export_id=export_id,
        generated_at=generated_at,
        season=season,
        candidates=sorted(candidates, key=lambda c: c.candidate_id),
        deterministic_order="candidate_id asc",
    )
    
    # Build base dict without hash fields
    base_dict = {
        "export_id": export_id,
        "generated_at": generated_at,
        "season": season,
        "deterministic_order": "candidate_id asc",
        "candidates": [_candidate_spec_to_dict(c) for c in candidate_export.candidates],
    }
    
    # Compute candidates_sha256 (hash of base dict)
    candidates_sha256 = _compute_dict_sha256(base_dict)
    
    # Add candidates_sha256 to dict (no manifest_sha256 in candidates.json)
    final_dict = dict(base_dict)
    final_dict["candidates_sha256"] = candidates_sha256
    
    # Write candidates.json
    candidates_path = export_dir / "candidates.json"
    candidates_path.write_text(
        stable_json_dumps(final_dict),
        encoding="utf-8",
    )
    
    # Compute file hash of candidates.json
    candidates_file_sha256 = _compute_file_sha256(candidates_path)
    
    # Build manifest dict (without manifest_sha256)
    manifest_base = {
        "export_id": export_id,
        "season": season,
        "generated_at": generated_at,
        "candidates_count": len(candidates),
        "candidates_file": str(candidates_path.relative_to(export_dir)),
        "deterministic_order": "candidate_id asc",
        "candidates_sha256": candidates_sha256,
        "candidates_file_sha256": candidates_file_sha256,
    }
    
    # Compute manifest_sha256 (hash of manifest_base)
    manifest_sha256 = _compute_dict_sha256(manifest_base)
    manifest_base["manifest_sha256"] = manifest_sha256
    
    # Write manifest.json
    manifest_path = export_dir / "manifest.json"
    manifest_path.write_text(
        stable_json_dumps(manifest_base),
        encoding="utf-8",
    )
    
    return candidates_path


def _candidate_export_to_dict(export: CandidateExport) -> dict:
    """Convert CandidateExport to dict for JSON serialization."""
    return {
        "export_id": export.export_id,
        "generated_at": export.generated_at,
        "season": export.season,
        "deterministic_order": export.deterministic_order,
        "candidates": [_candidate_spec_to_dict(c) for c in export.candidates],
    }


def _candidate_spec_to_dict(candidate: CandidateSpec) -> dict:
    """Convert CandidateSpec to dict for JSON serialization."""
    return {
        "candidate_id": candidate.candidate_id,
        "strategy_id": candidate.strategy_id,
        "param_hash": candidate.param_hash,
        "research_score": candidate.research_score,
        "research_confidence": candidate.research_confidence,
        "season": candidate.season,
        "batch_id": candidate.batch_id,
        "job_id": candidate.job_id,
        "tags": candidate.tags,
        "metadata": candidate.metadata,
    }


def _compute_file_sha256(path: Path) -> str:
    """Compute SHA256 hash of a file."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _compute_dict_sha256(obj: dict) -> str:
    """Compute SHA256 hash of a dict using stable JSON serialization."""
    json_str = stable_json_dumps(obj)
    return hashlib.sha256(json_str.encode("utf-8")).hexdigest()


def load_candidates(candidates_path: Path) -> CandidateExport:
    """
    Load candidates from a candidates.json file.
    
    Raises:
        FileNotFoundError: if file does not exist
        ValueError: if JSON is invalid
    """
    if not candidates_path.exists():
        raise FileNotFoundError(f"Candidates file not found: {candidates_path}")
    
    data = json.loads(candidates_path.read_text(encoding="utf-8"))
    
    # Remove hash fields if present (they are for audit only)
    data.pop("candidates_sha256", None)
    
    # Convert dicts back to CandidateSpec objects
    candidates = []
    for c_dict in data.get("candidates", []):
        candidate = CandidateSpec(
            candidate_id=c_dict["candidate_id"],
            strategy_id=c_dict["strategy_id"],
            param_hash=c_dict["param_hash"],
            research_score=c_dict["research_score"],
            research_confidence=c_dict.get("research_confidence", 1.0),
            season=c_dict.get("season"),
            batch_id=c_dict.get("batch_id"),
            job_id=c_dict.get("job_id"),
            tags=c_dict.get("tags", []),
            metadata=c_dict.get("metadata", {}),
        )
        candidates.append(candidate)
    
    return CandidateExport(
        export_id=data["export_id"],
        generated_at=data["generated_at"],
        season=data["season"],
        candidates=candidates,
        deterministic_order=data.get("deterministic_order", "candidate_id asc"),
    )