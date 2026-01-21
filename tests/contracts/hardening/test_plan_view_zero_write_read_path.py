
"""Test that render_plan_view (pure read) does not write anything."""
import pytest
import tempfile
import json
from pathlib import Path

from utils.fs_snapshot import snapshot_tree, diff_snap
from contracts.portfolio.plan_models import (
    PortfolioPlan, SourceRef, PlannedCandidate, PlannedWeight,
    PlanSummary, ConstraintsReport
)
from portfolio.plan_view_renderer import render_plan_view


def test_plan_view_zero_write_read_path():
    """render_plan_view (pure read) should not write any files."""
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
            plan_id="test_plan_zero_write",
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
        
        # Take snapshot before render
        snap_before = snapshot_tree(plan_dir, include_sha256=True)
        
        # Call render_plan_view (pure function, should not write)
        view = render_plan_view(plan, top_n=5)
        
        # Take snapshot after render
        snap_after = snapshot_tree(plan_dir, include_sha256=True)
        
        # Verify no changes
        diff = diff_snap(snap_before, snap_after)
        assert diff["added"] == [], f"Files added during render: {diff['added']}"
        assert diff["removed"] == [], f"Files removed during render: {diff['removed']}"
        assert diff["changed"] == [], f"Files changed during render: {diff['changed']}"
        
        # Verify view was created correctly
        assert view.plan_id == "test_plan_zero_write"
        assert len(view.top_candidates) == 5
        assert view.universe_stats["total_candidates"] == 10


