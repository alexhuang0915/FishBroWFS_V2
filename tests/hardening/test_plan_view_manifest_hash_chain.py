
"""Test tamper evidence via hash chain in view manifest."""
import pytest
import tempfile
import json
import hashlib
from pathlib import Path

from FishBroWFS_V2.contracts.portfolio.plan_models import (
    PortfolioPlan, SourceRef, PlannedCandidate, PlannedWeight,
    PlanSummary, ConstraintsReport
)
from FishBroWFS_V2.portfolio.plan_view_renderer import render_plan_view, write_plan_view_files
from FishBroWFS_V2.control.artifacts import canonical_json_bytes, compute_sha256


def test_plan_view_manifest_hash_chain():
    """Tamper evidence: manifest hash chain should detect modifications."""
    with tempfile.TemporaryDirectory() as tmpdir:
        plan_dir = Path(tmpdir) / "test_plan_tamper"
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
                candidate_id="cand_1",
                strategy_id="strategy_1",
                dataset_id="dataset_1",
                params={"param": 1.0},
                score=0.9,
                season="test_season",
                source_batch="batch_1",
                source_export="export_1",
            )
        ]
        
        weights = [
            PlannedWeight(
                candidate_id="cand_1",
                weight=1.0,
                reason="test",
            )
        ]
        
        summaries = PlanSummary(
            total_candidates=1,
            total_weight=1.0,
            bucket_counts={},
            bucket_weights={},
            concentration_herfindahl=1.0,
        )
        
        constraints = ConstraintsReport(
            max_per_strategy_truncated={},
            max_per_dataset_truncated={},
            max_weight_clipped=[],
            min_weight_clipped=[],
            renormalization_applied=False,
        )
        
        plan = PortfolioPlan(
            plan_id="test_plan_tamper",
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
        
        # Render and write view files
        view = render_plan_view(plan, top_n=5)
        write_plan_view_files(plan_dir, view)
        
        # 1. Verify plan_view_checksums.json structure
        checksums_path = plan_dir / "plan_view_checksums.json"
        checksums = json.loads(checksums_path.read_text())
        
        assert set(checksums.keys()) == {"plan_view.json", "plan_view.md"}, \
            f"checksums keys should be exactly plan_view.json and plan_view.md, got {checksums.keys()}"
        
        # Verify checksums are valid SHA256
        for filename, hash_val in checksums.items():
            assert isinstance(hash_val, str) and len(hash_val) == 64, \
                f"Invalid SHA256 for {filename}: {hash_val}"
            # Verify it matches actual file
            file_path = plan_dir / filename
            actual_hash = compute_sha256(file_path.read_bytes())
            assert actual_hash == hash_val, \
                f"checksum mismatch for {filename}"
        
        # 2. Verify plan_view_manifest.json structure
        manifest_path = plan_dir / "plan_view_manifest.json"
        manifest = json.loads(manifest_path.read_text())
        
        required_keys = {
            "plan_id", "generated_at_utc", "source", "inputs",
            "view_checksums", "manifest_sha256", "view_files",
            "manifest_version"
        }
        assert required_keys.issubset(manifest.keys()), \
            f"Missing keys in manifest: {required_keys - set(manifest.keys())}"
        
        # Verify view_checksums matches checksums file
        assert manifest["view_checksums"] == checksums, \
            "manifest.view_checksums should equal checksums file content"
        
        # Verify inputs contains portfolio_plan.json
        assert "portfolio_plan.json" in manifest["inputs"], \
            "inputs should contain portfolio_plan.json"
        
        # 3. Verify manifest_sha256 is correct
        # Remove the hash field to compute hash
        manifest_without_hash = {k: v for k, v in manifest.items() if k != "manifest_sha256"}
        canonical = canonical_json_bytes(manifest_without_hash)
        expected_hash = compute_sha256(canonical)
        
        assert manifest["manifest_sha256"] == expected_hash, \
            "manifest_sha256 does not match computed hash"
        
        # 4. Tamper test: modify plan_view.md and verify detection
        md_path = plan_dir / "plan_view.md"
        original_md = md_path.read_text()
        tampered_md = original_md + "\n<!-- TAMPERED -->\n"
        md_path.write_text(tampered_md)
        
        # Recompute hash of tampered file
        tampered_hash = compute_sha256(md_path.read_bytes())
        
        # Verify checksums no longer match
        assert tampered_hash != checksums["plan_view.md"], \
            "Tampered file hash should differ from original checksum"
        
        # Verify manifest view_checksums no longer matches
        assert manifest["view_checksums"]["plan_view.md"] != tampered_hash, \
            "Manifest checksum should not match tampered file"
        
        # 5. Optional: verify loader can detect tampering
        from FishBroWFS_V2.portfolio.plan_view_loader import verify_view_integrity
        assert not verify_view_integrity(plan_dir), \
            "verify_view_integrity should return False for tampered files"


