"""Contract tests for governance writer.

Tests that governance writer creates expected directory structure and files.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from datetime import datetime, timezone

from FishBroWFS_V2.core.governance_schema import (
    Decision,
    EvidenceRef,
    GovernanceItem,
    GovernanceReport,
)
from FishBroWFS_V2.core.governance_writer import write_governance_artifacts


def test_governance_writer_creates_expected_tree() -> None:
    """
    Test that governance writer creates expected directory structure.
    
    Expected:
    - governance.json (machine-readable)
    - README.md (human-readable)
    - evidence_index.json (optional but recommended)
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        governance_dir = Path(tmpdir) / "governance" / "test-123"
        
        # Create sample report
        evidence = [
            EvidenceRef(
                run_id="stage1-123",
                stage_name="stage1_topk",
                artifact_paths=["manifest.json", "metrics.json", "winners.json"],
                key_metrics={
                    "param_id": 0,
                    "net_profit": 100.0,
                    "stage_planned_subsample": 0.1,
                    "param_subsample_rate": 0.1,
                    "params_effective": 100,
                },
            ),
        ]
        
        item = GovernanceItem(
            candidate_id="donchian_atr:abc123def456",
            decision=Decision.KEEP,
            reasons=[],
            evidence=evidence,
            created_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            git_sha="abc123def456",
        )
        
        report = GovernanceReport(
            items=[item],
            metadata={
                "governance_id": "gov-123",
                "season": "test_season",
                "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                "git_sha": "abc123def456",
                "decisions": {"KEEP": 1, "FREEZE": 0, "DROP": 0},
            },
        )
        
        # Write artifacts
        write_governance_artifacts(governance_dir, report)
        
        # Verify files exist
        assert governance_dir.exists()
        assert (governance_dir / "governance.json").exists()
        assert (governance_dir / "README.md").exists()
        assert (governance_dir / "evidence_index.json").exists()
        
        # Verify governance.json is valid JSON
        with (governance_dir / "governance.json").open("r", encoding="utf-8") as f:
            governance_dict = json.load(f)
        
        assert "items" in governance_dict
        assert "metadata" in governance_dict
        assert len(governance_dict["items"]) == 1
        
        # Verify README.md contains key information
        readme_text = (governance_dir / "README.md").read_text(encoding="utf-8")
        assert "Governance Report" in readme_text
        assert "governance_id" in readme_text
        assert "Decision Summary" in readme_text
        assert "KEEP" in readme_text
        
        # Verify evidence_index.json is valid JSON
        with (governance_dir / "evidence_index.json").open("r", encoding="utf-8") as f:
            evidence_index = json.load(f)
        
        assert "governance_id" in evidence_index
        assert "evidence_by_candidate" in evidence_index


def test_governance_json_contains_subsample_fields_in_evidence() -> None:
    """
    Test that governance.json contains subsample fields in evidence.
    
    Critical requirement: subsample info must be in evidence chain.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        governance_dir = Path(tmpdir) / "governance" / "test-123"
        
        # Create report with subsample fields in evidence
        evidence = [
            EvidenceRef(
                run_id="stage1-123",
                stage_name="stage1_topk",
                artifact_paths=["manifest.json", "metrics.json", "winners.json"],
                key_metrics={
                    "param_id": 0,
                    "net_profit": 100.0,
                    "stage_planned_subsample": 0.1,
                    "param_subsample_rate": 0.1,
                    "params_effective": 100,
                },
            ),
        ]
        
        item = GovernanceItem(
            candidate_id="donchian_atr:abc123def456",
            decision=Decision.KEEP,
            reasons=[],
            evidence=evidence,
            created_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            git_sha="abc123def456",
        )
        
        report = GovernanceReport(
            items=[item],
            metadata={
                "governance_id": "gov-123",
                "season": "test_season",
                "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                "git_sha": "abc123def456",
                "decisions": {"KEEP": 1, "FREEZE": 0, "DROP": 0},
            },
        )
        
        # Write artifacts
        write_governance_artifacts(governance_dir, report)
        
        # Verify subsample fields are in governance.json
        with (governance_dir / "governance.json").open("r", encoding="utf-8") as f:
            governance_dict = json.load(f)
        
        item_dict = governance_dict["items"][0]
        evidence_dict = item_dict["evidence"][0]
        key_metrics = evidence_dict["key_metrics"]
        
        assert "stage_planned_subsample" in key_metrics
        assert "param_subsample_rate" in key_metrics
        assert "params_effective" in key_metrics


def test_readme_contains_freeze_reasons() -> None:
    """
    Test that README.md contains FREEZE reasons.
    
    Requirement: README must list FREEZE reasons (concise).
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        governance_dir = Path(tmpdir) / "governance" / "test-123"
        
        # Create report with FREEZE item
        evidence = [
            EvidenceRef(
                run_id="stage1-123",
                stage_name="stage1_topk",
                artifact_paths=["manifest.json", "metrics.json", "winners.json"],
                key_metrics={"param_id": 0, "net_profit": 100.0},
            ),
        ]
        
        freeze_item = GovernanceItem(
            candidate_id="donchian_atr:abc123def456",
            decision=Decision.FREEZE,
            reasons=["R3: density_5_over_threshold_3"],
            evidence=evidence,
            created_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            git_sha="abc123def456",
        )
        
        report = GovernanceReport(
            items=[freeze_item],
            metadata={
                "governance_id": "gov-123",
                "season": "test_season",
                "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                "git_sha": "abc123def456",
                "decisions": {"KEEP": 0, "FREEZE": 1, "DROP": 0},
            },
        )
        
        # Write artifacts
        write_governance_artifacts(governance_dir, report)
        
        # Verify README contains FREEZE reasons
        readme_text = (governance_dir / "README.md").read_text(encoding="utf-8")
        assert "FREEZE Reasons" in readme_text
        assert "donchian_atr:abc123def456" in readme_text
        assert "density" in readme_text
