
"""Test that write_plan_view_files only writes the 4 view files and is idempotent."""
import pytest
import tempfile
import json
from pathlib import Path

from utils.fs_snapshot import snapshot_tree, diff_snap
from contracts.portfolio.plan_models import (
    PortfolioPlan, SourceRef, PlannedCandidate, PlannedWeight,
    PlanSummary, ConstraintsReport
)
from portfolio.plan_view_renderer import render_plan_view, write_plan_view_files


def test_plan_view_write_scope_and_idempotent():
    """write_plan_view_files should only create/update 4 view files and be idempotent."""
    with tempfile.TemporaryDirectory() as tmpdir:
        plan_dir = Path(tmpdir) / "test_plan_write"
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
            for i in range(5)
        ]
        
        weights = [
            PlannedWeight(
                candidate_id=f"cand_{i}",
                weight=0.2,  # 5 * 0.2 = 1.0
                reason="test",
            )
            for i in range(5)
        ]
        
        summaries = PlanSummary(
            total_candidates=5,
            total_weight=1.0,
            bucket_counts={},
            bucket_weights={},
            concentration_herfindahl=0.2,
        )
        
        constraints = ConstraintsReport(
            max_per_strategy_truncated={},
            max_per_dataset_truncated={},
            max_weight_clipped=[],
            min_weight_clipped=[],
            renormalization_applied=False,
        )
        
        plan = PortfolioPlan(
            plan_id="test_plan_write",
            generated_at_utc="2025-01-01T00:00:00Z",
            source=source,
            config={"max_per_strategy": 5},
            universe=candidates,
            weights=weights,
            summaries=summaries,
            constraints_report=constraints,
        )
        
        # Write plan package files
        plan_data = plan.model_dump()
        (plan_dir / "portfolio_plan.json").write_text(
            json.dumps(plan_data, indent=2)
        )
        (plan_dir / "plan_manifest.json").write_text('{"test": "manifest"}')
        (plan_dir / "plan_metadata.json").write_text('{"test": "metadata"}')
        (plan_dir / "plan_checksums.json").write_text('{"test": "checksums"}')
        
        # Render view
        view = render_plan_view(plan, top_n=5)
        
        # Take snapshot before first write
        snap_before = snapshot_tree(plan_dir, include_sha256=True)
        
        # First write
        write_plan_view_files(plan_dir, view)
        
        # Take snapshot after first write
        snap_after_1 = snapshot_tree(plan_dir, include_sha256=True)
        
        # Check diff: only 4 view files should be added
        diff_1 = diff_snap(snap_before, snap_after_1)
        expected_files = {
            "plan_view.json",
            "plan_view.md",
            "plan_view_checksums.json",
            "plan_view_manifest.json",
        }
        
        assert set(diff_1["added"]) == expected_files, \
            f"Expected {expected_files}, got {diff_1['added']}"
        assert diff_1["removed"] == [], f"Files removed: {diff_1['removed']}"
        assert diff_1["changed"] == [], f"Files changed: {diff_1['changed']}"
        
        # Record mtimes of the 4 view files
        view_file_mtimes = {}
        for filename in expected_files:
            file_path = plan_dir / filename
            view_file_mtimes[filename] = file_path.stat().st_mtime_ns
        
        # Second write (idempotent test)
        write_plan_view_files(plan_dir, view)
        
        # Take snapshot after second write
        snap_after_2 = snapshot_tree(plan_dir, include_sha256=True)
        
        # Check diff: should be empty (no changes)
        diff_2 = diff_snap(snap_after_1, snap_after_2)
        assert diff_2["added"] == [], f"Files added on second write: {diff_2['added']}"
        assert diff_2["removed"] == [], f"Files removed on second write: {diff_2['removed']}"
        assert diff_2["changed"] == [], f"Files changed on second write: {diff_2['changed']}"
        
        # Verify mtimes unchanged (idempotent)
        for filename in expected_files:
            file_path = plan_dir / filename
            new_mtime = file_path.stat().st_mtime_ns
            assert new_mtime == view_file_mtimes[filename], \
                f"mtime changed for {filename} on second write"
        
        # Verify no other files were touched
        all_files = {p.relative_to(plan_dir).as_posix() for p in plan_dir.rglob("*") if p.is_file()}
        expected_all = expected_files | {
            "portfolio_plan.json",
            "plan_manifest.json",
            "plan_metadata.json",
            "plan_checksums.json",
        }
        assert all_files == expected_all, f"Unexpected files: {all_files - expected_all}"
        
        # Verify checksums file structure
        checksums_path = plan_dir / "plan_view_checksums.json"
        checksums = json.loads(checksums_path.read_text())
        assert set(checksums.keys()) == {"plan_view.json", "plan_view.md"}
        assert all(isinstance(v, str) and len(v) == 64 for v in checksums.values())
        
        # Verify manifest structure
        manifest_path = plan_dir / "plan_view_manifest.json"
        manifest = json.loads(manifest_path.read_text())
        assert manifest["plan_id"] == "test_plan_write"
        assert "inputs" in manifest
        assert "view_checksums" in manifest
        assert "manifest_sha256" in manifest
        assert manifest["view_checksums"] == checksums


