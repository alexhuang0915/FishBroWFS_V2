"""
Phase 17‑C: Portfolio Plan Hash Chain Tests.

Contracts:
- plan_manifest.json includes SHA256 of itself (two‑phase write).
- All files under plan directory have checksums recorded.
- Hash chain ensures immutability and auditability.
"""

import json
import tempfile
from pathlib import Path

import pytest

from FishBroWFS_V2.contracts.portfolio.plan_payloads import PlanCreatePayload
from FishBroWFS_V2.portfolio.plan_builder import (
    build_portfolio_plan_from_export,
    write_plan_package,
)


def _create_mock_export(tmp_path: Path, season: str, export_name: str) -> Path:
    """Create a minimal export."""
    export_dir = tmp_path / "seasons" / season / export_name
    export_dir.mkdir(parents=True)

    (export_dir / "manifest.json").write_text(json.dumps({}, separators=(",", ":")))
    candidates = [
        {
            "candidate_id": "cand1",
            "strategy_id": "stratA",
            "dataset_id": "ds1",
            "params": {},
            "score": 1.0,
            "season": season,
            "source_batch": "batch1",
            "source_export": export_name,
        }
    ]
    (export_dir / "candidates.json").write_text(json.dumps(candidates, separators=(",", ":")))
    return tmp_path


def test_plan_manifest_includes_self_hash():
    """plan_manifest.json must contain a manifest_sha256 field that matches its own hash."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        exports_root = _create_mock_export(tmp_path, "season1", "export1")

        payload = PlanCreatePayload(
            season="season1",
            export_name="export1",
            top_n=10,
            max_per_strategy=5,
            max_per_dataset=5,
            weighting="bucket_equal",
            bucket_by=["dataset_id"],
            max_weight=0.2,
            min_weight=0.0,
        )

        plan = build_portfolio_plan_from_export(
            exports_root=exports_root,
            season="season1",
            export_name="export1",
            payload=payload,
        )

        outputs_root = tmp_path / "outputs"
        plan_dir = write_plan_package(outputs_root=outputs_root, plan=plan)

        manifest_path = plan_dir / "plan_manifest.json"
        assert manifest_path.exists()

        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert "manifest_sha256" in manifest

        # Compute SHA256 of manifest excluding the manifest_sha256 field
        from FishBroWFS_V2.control.artifacts import canonical_json_bytes, compute_sha256

        manifest_without_hash = {k: v for k, v in manifest.items() if k != "manifest_sha256"}
        canonical = canonical_json_bytes(manifest_without_hash)
        expected_hash = compute_sha256(canonical)

        assert manifest["manifest_sha256"] == expected_hash


def test_checksums_file_exists():
    """plan_checksums.json must exist and contain SHA256 of all other files."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        exports_root = _create_mock_export(tmp_path, "season1", "export1")

        payload = PlanCreatePayload(
            season="season1",
            export_name="export1",
            top_n=10,
            max_per_strategy=5,
            max_per_dataset=5,
            weighting="bucket_equal",
            bucket_by=["dataset_id"],
            max_weight=0.2,
            min_weight=0.0,
        )

        plan = build_portfolio_plan_from_export(
            exports_root=exports_root,
            season="season1",
            export_name="export1",
            payload=payload,
        )

        outputs_root = tmp_path / "outputs"
        plan_dir = write_plan_package(outputs_root=outputs_root, plan=plan)

        checksums_path = plan_dir / "plan_checksums.json"
        assert checksums_path.exists()

        checksums = json.loads(checksums_path.read_text(encoding="utf-8"))
        assert isinstance(checksums, dict)
        expected_files = {"plan_metadata.json", "portfolio_plan.json"}
        assert set(checksums.keys()) == expected_files

        # Verify each checksum matches file content
        import hashlib
        for filename, expected_sha in checksums.items():
            file_path = plan_dir / filename
            data = file_path.read_bytes()
            actual_sha = hashlib.sha256(data).hexdigest()
            assert actual_sha == expected_sha, f"Checksum mismatch for {filename}"


def test_manifest_includes_checksums():
    """plan_manifest.json must include the checksums dictionary."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        exports_root = _create_mock_export(tmp_path, "season1", "export1")

        payload = PlanCreatePayload(
            season="season1",
            export_name="export1",
            top_n=10,
            max_per_strategy=5,
            max_per_dataset=5,
            weighting="bucket_equal",
            bucket_by=["dataset_id"],
            max_weight=0.2,
            min_weight=0.0,
        )

        plan = build_portfolio_plan_from_export(
            exports_root=exports_root,
            season="season1",
            export_name="export1",
            payload=payload,
        )

        outputs_root = tmp_path / "outputs"
        plan_dir = write_plan_package(outputs_root=outputs_root, plan=plan)

        manifest_path = plan_dir / "plan_manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

        assert "checksums" in manifest
        assert isinstance(manifest["checksums"], dict)
        assert set(manifest["checksums"].keys()) == {"plan_metadata.json", "portfolio_plan.json"}


def test_plan_directory_immutable():
    """Plan directory must not be overwritten (idempotent write)."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        exports_root = _create_mock_export(tmp_path, "season1", "export1")

        payload = PlanCreatePayload(
            season="season1",
            export_name="export1",
            top_n=10,
            max_per_strategy=5,
            max_per_dataset=5,
            weighting="bucket_equal",
            bucket_by=["dataset_id"],
            max_weight=0.2,
            min_weight=0.0,
        )

        plan = build_portfolio_plan_from_export(
            exports_root=exports_root,
            season="season1",
            export_name="export1",
            payload=payload,
        )

        outputs_root = tmp_path / "outputs"
        plan_dir1 = write_plan_package(outputs_root=outputs_root, plan=plan)

        # Attempt to write same plan again should be idempotent (no error, same directory)
        plan_dir2 = write_plan_package(outputs_root=outputs_root, plan=plan)
        assert plan_dir1 == plan_dir2
        # Ensure no new files were created (directory contents unchanged)
        files1 = sorted(f.name for f in plan_dir1.iterdir())
        files2 = sorted(f.name for f in plan_dir2.iterdir())
        assert files1 == files2


def test_plan_metadata_includes_source_sha256():
    """plan_metadata.json must include source export and candidates SHA256."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        exports_root = _create_mock_export(tmp_path, "season1", "export1")

        payload = PlanCreatePayload(
            season="season1",
            export_name="export1",
            top_n=10,
            max_per_strategy=5,
            max_per_dataset=5,
            weighting="bucket_equal",
            bucket_by=["dataset_id"],
            max_weight=0.2,
            min_weight=0.0,
        )

        plan = build_portfolio_plan_from_export(
            exports_root=exports_root,
            season="season1",
            export_name="export1",
            payload=payload,
        )

        outputs_root = tmp_path / "outputs"
        plan_dir = write_plan_package(outputs_root=outputs_root, plan=plan)

        metadata_path = plan_dir / "plan_metadata.json"
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))

        assert "source" in metadata
        source = metadata["source"]
        assert "export_manifest_sha256" in source
        assert "candidates_sha256" in source
        # SHA256 values should be strings (could be fake in this test)
        assert isinstance(source["export_manifest_sha256"], str)
        assert isinstance(source["candidates_sha256"], str)