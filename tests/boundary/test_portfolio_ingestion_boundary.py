"""
Phase 17‑C: Portfolio Ingestion Boundary Tests.

Contracts:
- Portfolio ingestion must NOT read from artifacts/ directory (only exports/).
- Must NOT write outside outputs/portfolio/plans/{plan_id}/.
- Must NOT mutate any existing files (except the new plan directory).
"""

import json
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from FishBroWFS_V2.contracts.portfolio.plan_payloads import PlanCreatePayload
from FishBroWFS_V2.portfolio.plan_builder import (
    build_portfolio_plan_from_export,
    write_plan_package,
)


def test_no_artifacts_access():
    """Plan builder must not read from artifacts/ directory."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        # Create exports directory
        exports_root = tmp_path / "exports"
        exports_root.mkdir()
        export_dir = exports_root / "seasons" / "season1" / "export1"
        export_dir.mkdir(parents=True)
        (export_dir / "manifest.json").write_text("{}")
        (export_dir / "candidates.json").write_text(json.dumps([
            {
                "candidate_id": "cand1",
                "strategy_id": "stratA",
                "dataset_id": "ds1",
                "params": {},
                "score": 1.0,
                "season": "season1",
                "source_batch": "batch1",
                "source_export": "export1",
            },
            {
                "candidate_id": "cand2",
                "strategy_id": "stratA",
                "dataset_id": "ds2",
                "params": {},
                "score": 0.9,
                "season": "season1",
                "source_batch": "batch1",
                "source_export": "export1",
            }
        ], sort_keys=True))

        # Create artifacts directory with some files
        artifacts_root = tmp_path / "artifacts"
        artifacts_root.mkdir()
        batch_dir = artifacts_root / "batch1"
        batch_dir.mkdir(parents=True)
        (batch_dir / "execution.json").write_text('{"state": "RUNNING"}')

        # Mock os.listdir to detect any reads from artifacts
        original_listdir = os.listdir
        accessed_paths = []

        def spy_listdir(path):
            accessed_paths.append(path)
            return original_listdir(path)

        with patch("os.listdir", spy_listdir):
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

        # Ensure no path under artifacts was listed
        for p in accessed_paths:
            assert "artifacts" not in str(p), f"Unexpected access to artifacts: {p}"


def test_write_only_under_plan_directory():
    """write_plan_package must not create files outside outputs/portfolio/plans/{plan_id}/."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        # Create a dummy plan
        from FishBroWFS_V2.contracts.portfolio.plan_models import (
            ConstraintsReport,
            PlanSummary,
            PlannedCandidate,
            PlannedWeight,
            PortfolioPlan,
            SourceRef,
        )
        from datetime import datetime, timezone

        source = SourceRef(
            season="season1",
            export_name="export1",
            export_manifest_sha256="sha256_manifest",
            candidates_sha256="sha256_candidates",
        )
        config = PlanCreatePayload(
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
        universe = [
            PlannedCandidate(
                candidate_id="cand1",
                strategy_id="stratA",
                dataset_id="ds1",
                params={},
                score=0.9,
                season="season1",
                source_batch="batch1",
                source_export="export1",
            )
        ]
        weights = [
            PlannedWeight(candidate_id="cand1", weight=1.0, reason="bucket_equal")
        ]
        summaries = PlanSummary(
            total_candidates=1,
            total_weight=1.0,
            bucket_counts={"ds1": 1},
            bucket_weights={"ds1": 1.0},
            concentration_herfindahl=1.0,
        )
        constraints = ConstraintsReport()
        plan = PortfolioPlan(
            plan_id="plan_test123",
            generated_at_utc=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            source=source,
            config=config,
            universe=universe,
            weights=weights,
            summaries=summaries,
            constraints_report=constraints,
        )

        outputs_root = tmp_path / "outputs"
        plan_dir = write_plan_package(outputs_root=outputs_root, plan=plan)

        # Ensure plan_dir is under outputs/portfolio/plans/
        assert plan_dir.is_relative_to(outputs_root / "portfolio" / "plans")

        # Ensure no other directories were created under outputs
        for child in outputs_root.iterdir():
            if child.name == "portfolio":
                continue
            # Should be no other top‑level directories
            assert False, f"Unexpected directory under outputs: {child}"

        # Ensure no files outside plan_dir
        for root, dirs, files in os.walk(outputs_root):
            if root == str(plan_dir):
                continue
            if files:
                assert False, f"Unexpected files outside plan directory: {root} {files}"


def test_no_mutation_of_existing_files():
    """Plan creation must not modify any existing files (including exports)."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        exports_root = tmp_path / "exports"
        exports_root.mkdir()
        export_dir = exports_root / "seasons" / "season1" / "export1"
        export_dir.mkdir(parents=True)
        manifest_path = export_dir / "manifest.json"
        manifest_path.write_text('{"original": true}')
        candidates_path = export_dir / "candidates.json"
        candidates_path.write_text(json.dumps([
            {
                "candidate_id": "cand1",
                "strategy_id": "stratA",
                "dataset_id": "ds1",
                "params": {},
                "score": 1.0,
                "season": "season1",
                "source_batch": "batch1",
                "source_export": "export1",
            },
            {
                "candidate_id": "cand2",
                "strategy_id": "stratA",
                "dataset_id": "ds2",
                "params": {},
                "score": 0.9,
                "season": "season1",
                "source_batch": "batch1",
                "source_export": "export1",
            }
        ], sort_keys=True))

        # Record modification times
        manifest_mtime = manifest_path.stat().st_mtime_ns
        candidates_mtime = candidates_path.stat().st_mtime_ns

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

        # Verify files unchanged
        assert manifest_path.stat().st_mtime_ns == manifest_mtime
        assert candidates_path.stat().st_mtime_ns == candidates_mtime
        assert manifest_path.read_text() == '{"original": true}'
        # candidates.json should remain unchanged (the same two candidates)
        expected_candidates = json.dumps([
            {
                "candidate_id": "cand1",
                "strategy_id": "stratA",
                "dataset_id": "ds1",
                "params": {},
                "score": 1.0,
                "season": "season1",
                "source_batch": "batch1",
                "source_export": "export1",
            },
            {
                "candidate_id": "cand2",
                "strategy_id": "stratA",
                "dataset_id": "ds2",
                "params": {},
                "score": 0.9,
                "season": "season1",
                "source_batch": "batch1",
                "source_export": "export1",
            }
        ], sort_keys=True)
        assert candidates_path.read_text() == expected_candidates


def test_plan_id_depends_only_on_export_and_payload():
    """Plan ID must be independent of artifacts, outputs, or any external state."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        exports_root = tmp_path / "exports"
        exports_root.mkdir()
        export_dir = exports_root / "seasons" / "season1" / "export1"
        export_dir.mkdir(parents=True)
        (export_dir / "manifest.json").write_text('{"key": "value"}')
        (export_dir / "candidates.json").write_text(json.dumps([
            {
                "candidate_id": "cand1",
                "strategy_id": "stratA",
                "dataset_id": "ds1",
                "params": {},
                "score": 1.0,
                "season": "season1",
                "source_batch": "batch1",
                "source_export": "export1",
            },
            {
                "candidate_id": "cand2",
                "strategy_id": "stratA",
                "dataset_id": "ds2",
                "params": {},
                "score": 0.9,
                "season": "season1",
                "source_batch": "batch1",
                "source_export": "export1",
            }
        ], sort_keys=True))

        # Create artifacts directory with different content
        artifacts_root = tmp_path / "artifacts"
        artifacts_root.mkdir()
        batch_dir = artifacts_root / "batch1"
        batch_dir.mkdir(parents=True)
        (batch_dir / "execution.json").write_text('{"state": "RUNNING"}')

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

        plan1 = build_portfolio_plan_from_export(
            exports_root=exports_root,
            season="season1",
            export_name="export1",
            payload=payload,
        )

        # Change artifacts (should not affect plan ID)
        (artifacts_root / "batch1" / "execution.json").write_text('{"state": "DONE"}')

        plan2 = build_portfolio_plan_from_export(
            exports_root=exports_root,
            season="season1",
            export_name="export1",
            payload=payload,
        )

        assert plan1.plan_id == plan2.plan_id


# Helper import
import os