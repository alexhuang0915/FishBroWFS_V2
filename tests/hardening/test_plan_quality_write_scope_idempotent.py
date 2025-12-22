
"""Test that write_plan_quality_files writes only three files and is idempotent."""
import pytest
import tempfile
import json
from pathlib import Path
import time

from FishBroWFS_V2.utils.fs_snapshot import snapshot_tree, diff_snap
from FishBroWFS_V2.contracts.portfolio.plan_models import (
    PortfolioPlan, SourceRef, PlannedCandidate, PlannedWeight,
    PlanSummary, ConstraintsReport
)
from FishBroWFS_V2.contracts.portfolio.plan_quality_models import (
    PlanQualityReport, QualityMetrics, QualitySourceRef, QualityThresholds
)
from FishBroWFS_V2.portfolio.plan_quality import compute_quality_from_plan_dir
from FishBroWFS_V2.portfolio.plan_quality_writer import write_plan_quality_files


def test_plan_quality_write_scope_and_idempotent():
    """write_plan_quality_files should write only three files and be idempotent."""
    with tempfile.TemporaryDirectory() as tmpdir:
        plan_dir = Path(tmpdir) / "test_plan"
        plan_dir.mkdir()
        
        # Create a minimal valid portfolio plan
        source = SourceRef(
            season="test_season",
            export_name="test_export",
            export_manifest_sha256="a" * 64,
            candidates_sha256="b" * 64,
        )
        
        candidates = [
            PlannedCandidate(
                candidate_id=f"cand_{i}",
                strategy_id="strategy_1",
                dataset_id="dataset_1",
                params={"param": 1.0},
                score=0.8 + i * 0.01,
                season="test_season",
                source_batch="batch_1",
                source_export="export_1",
            )
            for i in range(10)
        ]
        
        weights = [
            PlannedWeight(
                candidate_id=f"cand_{i}",
                weight=0.1,  # Equal weights sum to 1.0
                reason="test",
            )
            for i in range(10)
        ]
        
        summaries = PlanSummary(
            total_candidates=10,
            total_weight=1.0,
            bucket_counts={},
            bucket_weights={},
            concentration_herfindahl=0.1,
        )
        
        constraints = ConstraintsReport(
            max_per_strategy_truncated={},
            max_per_dataset_truncated={},
            max_weight_clipped=[],
            min_weight_clipped=[],
            renormalization_applied=False,
        )
        
        plan = PortfolioPlan(
            plan_id="test_plan_write_scope",
            generated_at_utc="2025-01-01T00:00:00Z",
            source=source,
            config={"max_per_strategy": 5, "max_per_dataset": 3},
            universe=candidates,
            weights=weights,
            summaries=summaries,
            constraints_report=constraints,
        )
        
        # Write plan files (simulating existing plan package)
        plan_data = plan.model_dump()
        (plan_dir / "portfolio_plan.json").write_text(
            json.dumps(plan_data, indent=2)
        )
        (plan_dir / "plan_manifest.json").write_text('{"test": "manifest"}')
        (plan_dir / "plan_metadata.json").write_text('{"test": "metadata"}')
        (plan_dir / "plan_checksums.json").write_text('{"test": "checksums"}')
        
        # Compute quality report
        quality_report, inputs = compute_quality_from_plan_dir(plan_dir)
        
        # Take snapshot before write
        snap_before = snapshot_tree(plan_dir, include_sha256=True)
        
        # First write
        write_plan_quality_files(plan_dir, quality_report)
        
        # Take snapshot after first write
        snap_after_1 = snapshot_tree(plan_dir, include_sha256=True)
        
        # Verify only three files were added
        diff_1 = diff_snap(snap_before, snap_after_1)
        assert diff_1["removed"] == [], f"Files removed during write: {diff_1['removed']}"
        assert diff_1["changed"] == [], f"Existing files changed during write: {diff_1['changed']}"
        
        added = sorted(diff_1["added"])
        expected_files = [
            "plan_quality.json",
            "plan_quality_checksums.json",
            "plan_quality_manifest.json",
        ]
        assert added == expected_files, f"Added files mismatch: {added} vs {expected_files}"
        
        # Record mtime_ns of the three files
        mtimes = {}
        for fname in expected_files:
            snap = snap_after_1[fname]
            mtimes[fname] = snap.mtime_ns
        
        # Wait a tiny bit to ensure mtime would change if file were rewritten
        time.sleep(0.001)
        
        # Second write (identical content)
        write_plan_quality_files(plan_dir, quality_report)
        
        # Take snapshot after second write
        snap_after_2 = snapshot_tree(plan_dir, include_sha256=True)
        
        # Verify no changes (idempotent)
        diff_2 = diff_snap(snap_after_1, snap_after_2)
        assert diff_2["added"] == [], f"Files added during second write: {diff_2['added']}"
        assert diff_2["removed"] == [], f"Files removed during second write: {diff_2['removed']}"
        assert diff_2["changed"] == [], f"Files changed during second write: {diff_2['changed']}"
        
        # Verify mtime_ns unchanged (idempotent at filesystem level)
        for fname in expected_files:
            snap = snap_after_2[fname]
            assert snap.mtime_ns == mtimes[fname], f"mtime changed for {fname}"
        
        # Verify file contents are correct
        quality_json = json.loads((plan_dir / "plan_quality.json").read_text())
        assert quality_json["plan_id"] == "test_plan_write_scope"
        assert quality_json["grade"] in ["GREEN", "YELLOW", "RED"]
        
        checksums = json.loads((plan_dir / "plan_quality_checksums.json").read_text())
        assert set(checksums.keys()) == {"plan_quality.json"}
        
        manifest = json.loads((plan_dir / "plan_quality_manifest.json").read_text())
        assert manifest["plan_id"] == "test_plan_write_scope"
        assert "view_checksums" in manifest
        assert "manifest_sha256" in manifest


