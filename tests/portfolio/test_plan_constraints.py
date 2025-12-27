
"""
Phase 17‑C: Portfolio Plan Constraints Tests.

Contracts:
- Selection constraints: top_n, max_per_strategy, max_per_dataset.
- Weight constraints: max_weight, min_weight, renormalization.
- Constraints report must reflect truncations and clippings.
"""

import json
import tempfile
from pathlib import Path

import pytest

from contracts.portfolio.plan_payloads import PlanCreatePayload
from portfolio.plan_builder import build_portfolio_plan_from_export


def _create_mock_export_with_candidates(
    tmp_path: Path,
    season: str,
    export_name: str,
    candidates: list[dict],
) -> Path:
    """Create export with given candidates."""
    export_dir = tmp_path / "seasons" / season / export_name
    export_dir.mkdir(parents=True)

    (export_dir / "candidates.json").write_text(json.dumps(candidates, separators=(",", ":")))
    (export_dir / "manifest.json").write_text(json.dumps({}, separators=(",", ":")))
    return tmp_path


def test_top_n_selection():
    """Only top N candidates by score are selected."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        candidates = [
            {
                "candidate_id": f"cand{i}",
                "strategy_id": "stratA",
                "dataset_id": "ds1",
                "params": {},
                "score": 1.0 - i * 0.1,
                "season": "season1",
                "source_batch": "batch1",
                "source_export": "export1",
            }
            for i in range(10)
        ]
        exports_root = _create_mock_export_with_candidates(
            tmp_path, "season1", "export1", candidates
        )

        payload = PlanCreatePayload(
            season="season1",
            export_name="export1",
            top_n=5,
            max_per_strategy=100,
            max_per_dataset=100,
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

        assert len(plan.universe) == 5
        selected_scores = [c.score for c in plan.universe]
        # Should be descending order
        assert selected_scores == sorted(selected_scores, reverse=True)
        assert selected_scores[0] == 1.0  # cand0
        assert selected_scores[-1] == 0.6  # cand4


def test_max_per_strategy_truncation():
    """At most max_per_strategy candidates per strategy."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        candidates = []
        # 5 candidates for stratA, 5 for stratB
        for s in ["stratA", "stratB"]:
            for i in range(5):
                candidates.append(
                    {
                        "candidate_id": f"{s}_{i}",
                        "strategy_id": s,
                        "dataset_id": "ds1",
                        "params": {},
                        "score": 1.0 - i * 0.1,
                        "season": "season1",
                        "source_batch": "batch1",
                        "source_export": "export1",
                    }
                )
        exports_root = _create_mock_export_with_candidates(
            tmp_path, "season1", "export1", candidates
        )

        payload = PlanCreatePayload(
            season="season1",
            export_name="export1",
            top_n=100,
            max_per_strategy=2,
            max_per_dataset=100,
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

        # Should have 2 per strategy = 4 total
        assert len(plan.universe) == 4
        strat_counts = {}
        for c in plan.universe:
            strat_counts[c.strategy_id] = strat_counts.get(c.strategy_id, 0) + 1
        assert strat_counts == {"stratA": 2, "stratB": 2}
        # Check that the highest‑scoring two per strategy are selected
        assert {c.candidate_id for c in plan.universe} == {
            "stratA_0",
            "stratA_1",
            "stratB_0",
            "stratB_1",
        }

        # Constraints report should reflect truncation
        report = plan.constraints_report
        assert report.max_per_strategy_truncated == {"stratA": 3, "stratB": 3}
        assert report.max_per_dataset_truncated == {}


def test_max_per_dataset_truncation():
    """At most max_per_dataset candidates per dataset."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        candidates = []
        for d in ["ds1", "ds2"]:
            for i in range(5):
                candidates.append(
                    {
                        "candidate_id": f"{d}_{i}",
                        "strategy_id": "stratA",
                        "dataset_id": d,
                        "params": {},
                        "score": 1.0 - i * 0.1,
                        "season": "season1",
                        "source_batch": "batch1",
                        "source_export": "export1",
                    }
                )
        exports_root = _create_mock_export_with_candidates(
            tmp_path, "season1", "export1", candidates
        )

        payload = PlanCreatePayload(
            season="season1",
            export_name="export1",
            top_n=100,
            max_per_strategy=100,
            max_per_dataset=2,
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

        assert len(plan.universe) == 4  # 2 per dataset
        dataset_counts = {}
        for c in plan.universe:
            dataset_counts[c.dataset_id] = dataset_counts.get(c.dataset_id, 0) + 1
        assert dataset_counts == {"ds1": 2, "ds2": 2}
        assert plan.constraints_report.max_per_dataset_truncated == {"ds1": 3, "ds2": 3}


def test_max_weight_clipping():
    """Weights exceeding max_weight are clipped."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        # Create a single bucket with many candidates to force small weights
        candidates = [
            {
                "candidate_id": f"cand{i}",
                "strategy_id": "stratA",
                "dataset_id": "ds1",
                "params": {},
                "score": 1.0 - i * 0.1,
                "season": "season1",
                "source_batch": "batch1",
                "source_export": "export1",
            }
            for i in range(10)
        ]
        exports_root = _create_mock_export_with_candidates(
            tmp_path, "season1", "export1", candidates
        )

        payload = PlanCreatePayload(
            season="season1",
            export_name="export1",
            top_n=10,
            max_per_strategy=100,
            max_per_dataset=100,
            weighting="bucket_equal",
            bucket_by=["dataset_id"],
            max_weight=0.05,  # very low max weight
            min_weight=0.0,
        )

        plan = build_portfolio_plan_from_export(
            exports_root=exports_root,
            season="season1",
            export_name="export1",
            payload=payload,
        )

        # Clipping should be recorded (since raw weight 0.1 > 0.05)
        assert len(plan.constraints_report.max_weight_clipped) > 0
        # Renormalization should be applied because sum after clipping != 1.0
        assert plan.constraints_report.renormalization_applied is True
        assert plan.constraints_report.renormalization_factor is not None


def test_min_weight_clipping():
    """Weights below min_weight are raised."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        # Create many buckets to force tiny weights
        candidates = []
        for d in ["ds1", "ds2", "ds3", "ds4", "ds5"]:
            candidates.append(
                {
                    "candidate_id": f"cand_{d}",
                    "strategy_id": "stratA",
                    "dataset_id": d,
                    "params": {},
                    "score": 1.0,
                    "season": "season1",
                    "source_batch": "batch1",
                    "source_export": "export1",
                }
            )
        exports_root = _create_mock_export_with_candidates(
            tmp_path, "season1", "export1", candidates
        )

        payload = PlanCreatePayload(
            season="season1",
            export_name="export1",
            top_n=10,
            max_per_strategy=100,
            max_per_dataset=100,
            weighting="bucket_equal",
            bucket_by=["dataset_id"],
            max_weight=1.0,
            min_weight=0.3,  # high min weight
        )

        plan = build_portfolio_plan_from_export(
            exports_root=exports_root,
            season="season1",
            export_name="export1",
            payload=payload,
        )

        # Each bucket weight = 0.2, candidate weight = 0.2 (since one candidate per bucket)
        # That's below min_weight 0.3, so clipping should be attempted.
        # However after renormalization weights may still be below min_weight.
        # We'll check that clipping was recorded (each candidate should appear at least once).
        # Due to iterative clipping, the list may contain duplicates; we deduplicate.
        clipped_set = set(plan.constraints_report.min_weight_clipped)
        assert clipped_set == {c["candidate_id"] for c in candidates}
        # Renormalization should be applied because sum after clipping > 1.0
        assert plan.constraints_report.renormalization_applied is True
        assert plan.constraints_report.renormalization_factor is not None


def test_weight_renormalization():
    """If clipping changes total weight, renormalization brings sum back to 1.0."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        candidates = [
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
            },
        ]
        exports_root = _create_mock_export_with_candidates(
            tmp_path, "season1", "export1", candidates
        )

        payload = PlanCreatePayload(
            season="season1",
            export_name="export1",
            top_n=10,
            max_per_strategy=100,
            max_per_dataset=100,
            weighting="bucket_equal",
            bucket_by=["dataset_id"],
            max_weight=0.8,
            min_weight=0.0,
        )

        plan = build_portfolio_plan_from_export(
            exports_root=exports_root,
            season="season1",
            export_name="export1",
            payload=payload,
        )

        # Two buckets, each weight 0.5, no clipping, sum = 1.0, no renormalization
        assert plan.constraints_report.renormalization_applied is False
        assert plan.constraints_report.renormalization_factor is None
        total = sum(w.weight for w in plan.weights)
        assert abs(total - 1.0) < 1e-9

        # Now set max_weight = 0.3, which will clip both weights down to 0.3, sum = 0.6, renormalization needed
        payload2 = PlanCreatePayload(
            season="season1",
            export_name="export1",
            top_n=10,
            max_per_strategy=100,
            max_per_dataset=100,
            weighting="bucket_equal",
            bucket_by=["dataset_id"],
            max_weight=0.3,
            min_weight=0.0,
        )

        plan2 = build_portfolio_plan_from_export(
            exports_root=exports_root,
            season="season1",
            export_name="export1",
            payload=payload2,
        )

        assert plan2.constraints_report.renormalization_applied is True
        assert plan2.constraints_report.renormalization_factor is not None
        total2 = sum(w.weight for w in plan2.weights)
        assert abs(total2 - 1.0) < 1e-9


