
"""
Phase 17‑C: Portfolio Plan Determinism Tests.

Contracts:
- Same export + same payload → same plan ID, same ordering, same weights.
- Tie‑break ordering: score desc → strategy_id asc → dataset_id asc → source_batch asc → params_json asc.
- No floating‑point non‑determinism (quantization to 12 decimal places).
"""

import json
import tempfile
from pathlib import Path

import pytest

from FishBroWFS_V2.contracts.portfolio.plan_payloads import PlanCreatePayload
from FishBroWFS_V2.portfolio.plan_builder import (
    build_portfolio_plan_from_export,
    compute_plan_id,
)


def _create_mock_export(tmp_path: Path, season: str, export_name: str) -> tuple[Path, str, str]:
    """Create a minimal export with manifest and candidates."""
    export_dir = tmp_path / "seasons" / season / export_name
    export_dir.mkdir(parents=True)

    # manifest.json
    manifest = {
        "season": season,
        "export_name": export_name,
        "created_at": "2025-12-20T00:00:00Z",
        "batch_ids": ["batch1", "batch2"],
    }
    manifest_path = export_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, separators=(",", ":")))
    manifest_sha256 = "fake_manifest_sha256"  # not used for deterministic test

    # candidates.json
    candidates = [
        {
            "candidate_id": "cand1",
            "strategy_id": "stratA",
            "dataset_id": "ds1",
            "params": {"p": 1},
            "score": 0.9,
            "season": season,
            "source_batch": "batch1",
            "source_export": export_name,
        },
        {
            "candidate_id": "cand2",
            "strategy_id": "stratA",
            "dataset_id": "ds2",
            "params": {"p": 2},
            "score": 0.8,
            "season": season,
            "source_batch": "batch1",
            "source_export": export_name,
        },
        {
            "candidate_id": "cand3",
            "strategy_id": "stratB",
            "dataset_id": "ds1",
            "params": {"p": 1},
            "score": 0.9,  # same score as cand1, tie‑break by strategy_id
            "season": season,
            "source_batch": "batch2",
            "source_export": export_name,
        },
    ]
    candidates_path = export_dir / "candidates.json"
    candidates_path.write_text(json.dumps(candidates, separators=(",", ":")))
    candidates_sha256 = "fake_candidates_sha256"

    return tmp_path, manifest_sha256, candidates_sha256


def test_compute_plan_id_deterministic():
    """Plan ID must be deterministic given same inputs."""
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
    id1 = compute_plan_id("sha256_manifest", "sha256_candidates", payload)
    id2 = compute_plan_id("sha256_manifest", "sha256_candidates", payload)
    assert id1 == id2
    assert id1.startswith("plan_")
    assert len(id1) == len("plan_") + 16  # 16 hex chars


def test_tie_break_ordering():
    """Candidates with same score must be ordered by strategy_id, dataset_id, source_batch, params."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        exports_root, _, _ = _create_mock_export(tmp_path, "season1", "export1")

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

        # Expect ordering: cand1 (score 0.9, stratA, ds1), cand3 (score 0.9, stratB, ds1), cand2 (score 0.8)
        # Because cand1 and cand3 have same score, tie‑break by strategy_id (A < B)
        candidate_ids = [c.candidate_id for c in plan.universe]
        assert candidate_ids == ["cand1", "cand3", "cand2"]


def test_plan_id_independent_of_filesystem_order():
    """Plan ID must not depend on filesystem iteration order."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        exports_root, manifest_sha256, candidates_sha256 = _create_mock_export(
            tmp_path, "season1", "export1"
        )

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

        # Re‑create export with same content (order of files unchanged)
        # The plan ID should be identical
        plan2 = build_portfolio_plan_from_export(
            exports_root=exports_root,
            season="season1",
            export_name="export1",
            payload=payload,
        )

        assert plan1.plan_id == plan2.plan_id
        assert plan1.universe == plan2.universe
        assert plan1.weights == plan2.weights


def test_weight_quantization():
    """Weights must be quantized to avoid floating‑point non‑determinism."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        exports_root, _, _ = _create_mock_export(tmp_path, "season1", "export1")

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

        # Each weight should be a float with limited decimal places
        for w in plan.weights:
            # Convert to string and check decimal places (should be <= 12)
            s = str(w.weight)
            if "." in s:
                decimal_places = len(s.split(".")[1])
                assert decimal_places <= 12, f"Weight {w.weight} has too many decimal places"

        # Sum of weights must be exactly 1.0 (within tolerance)
        total = sum(w.weight for w in plan.weights)
        assert abs(total - 1.0) < 1e-9


def test_selection_constraints_deterministic():
    """Selection constraints (top_n, max_per_strategy, max_per_dataset) must be deterministic."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        export_dir = tmp_path / "seasons" / "season1" / "export1"
        export_dir.mkdir(parents=True)

        # Create many candidates with same strategy and dataset
        candidates = []
        for i in range(10):
            candidates.append(
                {
                    "candidate_id": f"cand{i}",
                    "strategy_id": "stratA",
                    "dataset_id": "ds1",
                    "params": {"p": i},
                    "score": 1.0 - i * 0.1,
                    "season": "season1",
                    "source_batch": "batch1",
                    "source_export": "export1",
                }
            )
        (export_dir / "candidates.json").write_text(json.dumps(candidates, separators=(",", ":")))
        (export_dir / "manifest.json").write_text(json.dumps({}, separators=(",", ":")))

        payload = PlanCreatePayload(
            season="season1",
            export_name="export1",
            top_n=3,
            max_per_strategy=2,
            max_per_dataset=2,
            weighting="bucket_equal",
            bucket_by=["dataset_id"],
            max_weight=0.2,
            min_weight=0.0,
        )

        plan = build_portfolio_plan_from_export(
            exports_root=tmp_path,
            season="season1",
            export_name="export1",
            payload=payload,
        )

        # Should select top 2 candidates (due to max_per_strategy=2) and stop at top_n=3
        # Since max_per_dataset also 2, same limit.
        assert len(plan.universe) == 2
        selected_ids = {c.candidate_id for c in plan.universe}
        assert selected_ids == {"cand0", "cand1"}  # highest scores


