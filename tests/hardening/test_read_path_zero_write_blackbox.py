
"""PHASE C — Read‑path Zero Write Blackbox (最後一道滴水不漏)

Test that pure read paths cannot write (including mtime) under strict patch.

Covers:
- GET /portfolio/plans
- GET /portfolio/plans/{plan_id}
- Viewer import module + render_page (injected outputs_root)
- compute_quality_from_plan_dir (pure read)

Uses unified zero‑write patch and snapshot equality.
"""
import json
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from FishBroWFS_V2.control.api import app
from FishBroWFS_V2.portfolio.plan_quality import compute_quality_from_plan_dir
from FishBroWFS_V2.contracts.portfolio.plan_models import (
    PortfolioPlan, SourceRef, PlannedCandidate, PlannedWeight,
    PlanSummary, ConstraintsReport
)

from tests.hardening.zero_write_patch import ZeroWritePatch, snapshot_equality_check


def create_minimal_plan_dir(tmpdir: Path, plan_id: str = "plan_test") -> Path:
    """Create a minimal valid portfolio plan directory for testing."""
    plan_dir = tmpdir / "portfolio" / "plans" / plan_id
    plan_dir.mkdir(parents=True)
    
    # Create source
    source = SourceRef(
        season="test_season",
        export_name="test_export",
        export_manifest_sha256="a" * 64,
        candidates_sha256="b" * 64,
    )
    
    # Create candidates
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
    
    # Create weights
    weights = [
        PlannedWeight(
            candidate_id=f"cand_{i}",
            weight=0.2,  # Equal weights sum to 1.0
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
        plan_id=plan_id,
        generated_at_utc="2025-01-01T00:00:00Z",
        source=source,
        config={"max_per_strategy": 5, "max_per_dataset": 3},
        universe=candidates,
        weights=weights,
        summaries=summaries,
        constraints_report=constraints,
    )
    
    # Write plan files
    plan_data = plan.model_dump()
    (plan_dir / "portfolio_plan.json").write_text(
        json.dumps(plan_data, indent=2)
    )
    (plan_dir / "plan_manifest.json").write_text('{"test": "manifest"}')
    (plan_dir / "plan_metadata.json").write_text('{"test": "metadata"}')
    (plan_dir / "plan_checksums.json").write_text('{"test": "checksums"}')
    
    # Create a minimal plan_view.json for viewer scanning
    plan_view = {
        "plan_id": plan_id,
        "generated_at_utc": "2025-01-01T00:00:00Z",
        "source": {
            "season": "test_season",
            "export_name": "test_export",
        },
        "config_summary": {"max_per_strategy": 5, "max_per_dataset": 3},
        "universe_stats": {
            "total_candidates": 5,
            "num_selected": 5,
            "total_weight": 1.0,
            "concentration_herfindahl": 0.2,
        },
        "weight_distribution": {
            "buckets": [
                {"bucket_key": "dataset_1", "weight": 1.0, "count": 5}
            ]
        },
        "top_candidates": [
            {
                "candidate_id": f"cand_{i}",
                "strategy_id": "strategy_1",
                "dataset_id": "dataset_1",
                "score": 0.8 + i * 0.01,
                "weight": 0.2,
            }
            for i in range(5)
        ],
        "constraints_report": constraints.model_dump(),
        "metadata": {"test": "view"},
    }
    (plan_dir / "plan_view.json").write_text(json.dumps(plan_view, indent=2))
    
    return plan_dir


def test_api_get_portfolio_plans_zero_write():
    """GET /portfolio/plans must not write anything."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        outputs_root = tmp_path / "outputs"
        outputs_root.mkdir()
        
        # Create a plan directory to list
        plan_dir = create_minimal_plan_dir(outputs_root, "plan_existing")
        
        # Patch outputs root in API
        from FishBroWFS_V2.control.api import _get_outputs_root
        import FishBroWFS_V2.control.api as api_module
        
        original_get_outputs_root = api_module._get_outputs_root
        
        try:
            # Monkey-patch _get_outputs_root to return our temp outputs root
            api_module._get_outputs_root = lambda: outputs_root
            
            # Apply zero-write patch and snapshot equality
            with ZeroWritePatch():
                with snapshot_equality_check(outputs_root):
                    client = TestClient(app)
                    response = client.get("/portfolio/plans")
                    assert response.status_code == 200
                    data = response.json()
                    assert "plans" in data
                    # Should list our plan
                    assert len(data["plans"]) == 1
                    assert data["plans"][0]["plan_id"] == "plan_existing"
        finally:
            # Restore original function
            api_module._get_outputs_root = original_get_outputs_root


def test_api_get_portfolio_plan_by_id_zero_write():
    """GET /portfolio/plans/{plan_id} must not write anything."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        outputs_root = tmp_path / "outputs"
        outputs_root.mkdir()
        
        # Create a plan directory
        plan_dir = create_minimal_plan_dir(outputs_root, "plan_abc123")
        
        # Patch outputs root in API
        from FishBroWFS_V2.control.api import _get_outputs_root
        import FishBroWFS_V2.control.api as api_module
        
        original_get_outputs_root = api_module._get_outputs_root
        
        try:
            api_module._get_outputs_root = lambda: outputs_root
            
            # Apply zero-write patch and snapshot equality
            with ZeroWritePatch():
                with snapshot_equality_check(outputs_root):
                    client = TestClient(app)
                    response = client.get("/portfolio/plans/plan_abc123")
                    assert response.status_code == 200
                    data = response.json()
                    assert data["plan_id"] == "plan_abc123"
        finally:
            api_module._get_outputs_root = original_get_outputs_root


def test_viewer_import_and_render_zero_write():
    """Viewer import module and render_page must not write anything."""
    pytest.skip("UI plan viewer module deleted in Phase K-2")


def test_quality_read_compute_quality_zero_write():
    """compute_quality_from_plan_dir (pure read) must not write anything."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        plan_dir = create_minimal_plan_dir(tmp_path, "plan_quality_test")
        
        # Apply zero-write patch and snapshot equality
        with ZeroWritePatch():
            with snapshot_equality_check(plan_dir):
                # Call compute_quality_from_plan_dir (pure function, should not write)
                quality_report, inputs = compute_quality_from_plan_dir(plan_dir)
                
                # Verify quality report was created correctly
                assert quality_report.plan_id == "plan_quality_test"
                assert quality_report.grade in ["GREEN", "YELLOW", "RED"]
                assert quality_report.metrics is not None
                assert quality_report.reasons is not None


def test_all_read_paths_combined_zero_write():
    """Combined test: exercise all read paths in sequence with single patch."""
    pytest.skip("UI plan viewer module deleted in Phase K-2")


