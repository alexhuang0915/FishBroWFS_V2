
"""Test that plan quality contract (schema, thresholds, grading) is locked."""
import pytest
import tempfile
import json
from pathlib import Path

from contracts.portfolio.plan_models import (
    PortfolioPlan, SourceRef, PlannedCandidate, PlannedWeight,
    PlanSummary, ConstraintsReport
)
from contracts.portfolio.plan_quality_models import (
    PlanQualityReport, QualityMetrics, QualitySourceRef, QualityThresholds
)
from portfolio.plan_quality import compute_quality_from_plan_dir
from portfolio.plan_quality_writer import write_plan_quality_files


def test_plan_quality_contract_lock():
    """Quality contract (schema, thresholds, grading) must be deterministic and locked."""
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
            plan_id="test_plan_contract_lock",
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
        
        # Compute quality report
        quality_report, inputs = compute_quality_from_plan_dir(plan_dir)
        
        # Write quality files
        write_plan_quality_files(plan_dir, quality_report)
        
        # 1. Verify plan_quality.json schema matches PlanQualityReport
        quality_json = json.loads((plan_dir / "plan_quality.json").read_text())
        parsed_report = PlanQualityReport.model_validate(quality_json)
        assert parsed_report.plan_id == "test_plan_contract_lock"
        
        # 2. Verify plan_quality_checksums.json is flat dict with exactly one key
        checksums = json.loads((plan_dir / "plan_quality_checksums.json").read_text())
        assert isinstance(checksums, dict)
        assert len(checksums) == 1
        assert "plan_quality.json" in checksums
        assert isinstance(checksums["plan_quality.json"], str)
        assert len(checksums["plan_quality.json"]) == 64  # SHA256 hex length
        
        # 3. Verify plan_quality_manifest.json contains required fields
        manifest = json.loads((plan_dir / "plan_quality_manifest.json").read_text())
        required_fields = {
            "plan_id",
            "generated_at_utc",
            "source",
            "inputs",
            "view_checksums",
            "manifest_sha256",
        }
        for field in required_fields:
            assert field in manifest, f"Missing required field {field} in manifest"
        
        # 4. Verify manifest_sha256 matches canonical JSON of manifest (excluding that field)
        from control.artifacts import canonical_json_bytes, compute_sha256
        
        # Create a copy without manifest_sha256
        manifest_copy = manifest.copy()
        manifest_sha256 = manifest_copy.pop("manifest_sha256")
        
        # Compute canonical JSON and hash
        canonical = canonical_json_bytes(manifest_copy)
        computed_hash = compute_sha256(canonical)
        
        assert manifest_sha256 == computed_hash, "manifest_sha256 mismatch"
        
        # 5. Verify view_checksums matches plan_quality_checksums.json
        assert manifest["view_checksums"] == checksums
        
        # 6. Verify inputs contains at least portfolio_plan.json
        assert "portfolio_plan.json" in manifest["inputs"]
        assert isinstance(manifest["inputs"]["portfolio_plan.json"], str)
        assert len(manifest["inputs"]["portfolio_plan.json"]) == 64
        
        # 7. Verify grading logic is deterministic (run twice, get same result)
        report2, inputs2 = compute_quality_from_plan_dir(plan_dir)
        assert report2.model_dump() == quality_report.model_dump()
        
        # 8. Verify thresholds are applied correctly (just check that grade is one of three)
        assert quality_report.grade in ["GREEN", "YELLOW", "RED"]
        
        # 9. Verify reasons are sorted (as per contract)
        if quality_report.reasons:
            reasons = quality_report.reasons
            assert reasons == sorted(reasons), "Reasons must be sorted alphabetically"
        
        print(f"Quality grade: {quality_report.grade}")
        print(f"Metrics: {quality_report.metrics}")
        if quality_report.reasons:
            print(f"Reasons: {quality_report.reasons}")


