
"""Test that plan quality grading (GREEN/YELLOW/RED) follows thresholds."""
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


def create_test_plan(plan_id: str, top1_score: float, effective_n: float, bucket_coverage: float):
    """Helper to create a plan with specific metrics."""
    source = SourceRef(
        season="test_season",
        export_name="test_export",
        export_manifest_sha256="a" * 64,
        candidates_sha256="b" * 64,
    )
    
    # Create candidates with varying scores
    candidates = []
    for i in range(20):
        score = 0.5 + i * 0.02  # scores from 0.5 to 0.9
        candidates.append(
            PlannedCandidate(
                candidate_id=f"cand_{i}",
                strategy_id=f"strategy_{i % 3}",
                dataset_id=f"dataset_{i % 2}",
                params={"param": 1.0},
                score=score,
                season="test_season",
                source_batch="batch_1",
                source_export="export_1",
            )
        )
    
    # Adjust top candidate score
    if candidates:
        candidates[0].score = top1_score
    
    # Create weights (simulate concentration)
    weights = []
    total_weight = 0.0
    for i, cand in enumerate(candidates):
        # Simulate concentration: first few candidates get most weight
        if i < int(effective_n):
            weight = 1.0 / effective_n
        else:
            weight = 0.001
        weights.append(
            PlannedWeight(
                candidate_id=cand.candidate_id,
                weight=weight,
                reason="test",
            )
        )
        total_weight += weight
    
    # Normalize weights
    for w in weights:
        w.weight /= total_weight
    
    # Create bucket coverage
    bucket_counts = {}
    bucket_weights = {}
    for i, cand in enumerate(candidates):
        bucket = f"bucket_{i % 5}"
        bucket_counts[bucket] = bucket_counts.get(bucket, 0) + 1
        bucket_weights[bucket] = bucket_weights.get(bucket, 0.0) + weights[i].weight
    
    # Adjust bucket coverage
    covered_buckets = int(bucket_coverage * 5)
    for bucket in list(bucket_counts.keys())[covered_buckets:]:
        bucket_counts.pop(bucket, None)
        bucket_weights.pop(bucket, None)
    
    summaries = PlanSummary(
        total_candidates=len(candidates),
        total_weight=1.0,
        bucket_counts=bucket_counts,
        bucket_weights=bucket_weights,
        concentration_herfindahl=1.0 / effective_n,  # approximate
        bucket_coverage=bucket_coverage,
        bucket_coverage_ratio=bucket_coverage,
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
    return plan


def test_plan_quality_grading_thresholds():
    """Verify grading follows defined thresholds."""
    test_cases = [
        # (top1_score, effective_n, bucket_coverage, expected_grade, description)
        (0.95, 8.0, 1.0, "GREEN", "excellent on all dimensions"),
        (0.85, 6.0, 0.8, "YELLOW", "good but not excellent"),
        (0.75, 4.0, 0.6, "RED", "poor metrics"),
        (0.95, 3.0, 1.0, "RED", "low effective_n despite high top1"),
        (0.95, 8.0, 0.4, "RED", "low bucket coverage"),
        (0.82, 7.0, 0.9, "YELLOW", "borderline top1"),
        (0.78, 7.0, 0.9, "RED", "top1 below yellow threshold"),
    ]
    
    for i, (top1, eff_n, bucket_cov, expected_grade, desc) in enumerate(test_cases):
        with tempfile.TemporaryDirectory() as tmpdir:
            plan_dir = Path(tmpdir) / f"plan_{i}"
            plan_dir.mkdir()
            
            plan = create_test_plan(f"plan_{i}", top1, eff_n, bucket_cov)
            
            # Write plan files
            plan_data = plan.model_dump()
            (plan_dir / "portfolio_plan.json").write_text(
                json.dumps(plan_data, indent=2)
            )
            (plan_dir / "plan_manifest.json").write_text('{"test": "manifest"}')
            (plan_dir / "plan_metadata.json").write_text('{"test": "metadata"}')
            (plan_dir / "plan_checksums.json").write_text('{"test": "checksums"}')
            
            # Compute quality
            report, inputs = compute_quality_from_plan_dir(plan_dir)
            
            # Verify grade matches expectation
            assert report.grade == expected_grade, (
                f"Test '{desc}': expected {expected_grade}, got {report.grade}. "
                f"Metrics: top1={report.metrics.top1_score:.3f}, "
                f"effective_n={report.metrics.effective_n:.3f}, "
                f"bucket_coverage={report.metrics.bucket_coverage:.3f}"
            )
            
            # Verify metrics are within reasonable bounds
            assert 0.0 <= report.metrics.top1_score <= 1.0
            assert 1.0 <= report.metrics.effective_n <= report.metrics.total_candidates
            assert 0.0 <= report.metrics.bucket_coverage <= 1.0
            assert 0.0 <= report.metrics.concentration_herfindahl <= 1.0
            assert report.metrics.constraints_pressure >= 0.0
            
            print(f"✓ {desc}: {report.grade} "
                  f"(top1={report.metrics.top1_score:.3f}, "
                  f"eff_n={report.metrics.effective_n:.3f}, "
                  f"bucket={report.metrics.bucket_coverage:.3f})")


def test_plan_quality_reasons():
    """Verify reasons are generated for YELLOW/RED grades."""
    with tempfile.TemporaryDirectory() as tmpdir:
        plan_dir = Path(tmpdir) / "plan_reasons"
        plan_dir.mkdir()
        
        # Create a RED plan (low top1, low effective_n, low bucket coverage)
        plan = create_test_plan("plan_red", top1_score=0.7, effective_n=3.0, bucket_coverage=0.3)
        
        # Write plan files
        plan_data = plan.model_dump()
        (plan_dir / "portfolio_plan.json").write_text(
            json.dumps(plan_data, indent=2)
        )
        (plan_dir / "plan_manifest.json").write_text('{"test": "manifest"}')
        (plan_dir / "plan_metadata.json").write_text('{"test": "metadata"}')
        (plan_dir / "plan_checksums.json").write_text('{"test": "checksums"}')
        
        # Compute quality
        report, inputs = compute_quality_from_plan_dir(plan_dir)
        
        # RED plan should have reasons
        if report.grade == "RED":
            assert report.reasons is not None
            assert len(report.reasons) > 0
            print(f"RED plan reasons: {report.reasons}")
        
        # Verify reasons are sorted alphabetically
        if report.reasons:
            assert report.reasons == sorted(report.reasons), "Reasons must be sorted"


def test_plan_quality_deterministic():
    """Same plan → same quality report (including reasons order)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        plan_dir = Path(tmpdir) / "plan_det"
        plan_dir.mkdir()
        
        plan = create_test_plan("plan_det", top1_score=0.9, effective_n=7.0, bucket_coverage=0.8)
        
        # Write plan files
        plan_data = plan.model_dump()
        (plan_dir / "portfolio_plan.json").write_text(
            json.dumps(plan_data, indent=2)
        )
        (plan_dir / "plan_manifest.json").write_text('{"test": "manifest"}')
        (plan_dir / "plan_metadata.json").write_text('{"test": "metadata"}')
        (plan_dir / "plan_checksums.json").write_text('{"test": "checksums"}')
        
        # Compute twice
        report1, inputs1 = compute_quality_from_plan_dir(plan_dir)
        report2, inputs2 = compute_quality_from_plan_dir(plan_dir)
        
        # Should be identical
        assert report1.model_dump() == report2.model_dump()
        
        # Specifically check reasons order
        if report1.reasons:
            assert report1.reasons == report2.reasons


