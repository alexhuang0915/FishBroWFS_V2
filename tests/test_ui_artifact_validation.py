"""Tests for UI artifact validation.

Tests verify:
1. MISSING status when file does not exist
2. INVALID status when schema validation fails (with readable error messages)
3. DIRTY status when config_hash mismatch
4. OK status when validation passes
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# Add repo root to path for ui module
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ui.core.artifact_reader import ReadResult, SafeReadResult, try_read_artifact
from ui.core.evidence import EvidenceLink
from ui.core.status import (
    ArtifactStatus,
    ValidationResult,
    validate_governance_status,
    validate_manifest_status,
    validate_winners_v2_status,
)
from ui.core.schemas.governance import GovernanceReport
from ui.core.schemas.manifest import RunManifest
from ui.core.schemas.winners_v2 import WinnersV2


# Fixtures
@pytest.fixture
def fixtures_dir() -> Path:
    """Return path to test fixtures directory."""
    return Path(__file__).parent / "fixtures" / "artifacts"


@pytest.fixture
def temp_dir(tmp_path: Path) -> Path:
    """Return temporary directory for test artifacts."""
    return tmp_path


# Test: MISSING status
def test_manifest_missing_file(temp_dir: Path) -> None:
    """Test that missing manifest.json returns MISSING status."""
    manifest_path = temp_dir / "manifest.json"
    
    result = validate_manifest_status(str(manifest_path))
    
    assert result.status == ArtifactStatus.MISSING
    assert "不存在" in result.message or "not found" in result.message.lower()


def test_winners_v2_missing_file(temp_dir: Path) -> None:
    """Test that missing winners_v2.json returns MISSING status."""
    winners_path = temp_dir / "winners_v2.json"
    
    result = validate_winners_v2_status(str(winners_path))
    
    assert result.status == ArtifactStatus.MISSING
    assert "不存在" in result.message or "not found" in result.message.lower()


def test_governance_missing_file(temp_dir: Path) -> None:
    """Test that missing governance.json returns MISSING status."""
    governance_path = temp_dir / "governance.json"
    
    result = validate_governance_status(str(governance_path))
    
    assert result.status == ArtifactStatus.MISSING
    assert "不存在" in result.message or "not found" in result.message.lower()


# Test: INVALID status (schema validation errors)
def test_manifest_invalid_missing_field(fixtures_dir: Path) -> None:
    """Test that manifest with missing required field returns INVALID."""
    manifest_path = fixtures_dir / "manifest_missing_field.json"
    
    # Load data
    with manifest_path.open("r", encoding="utf-8") as f:
        manifest_data = json.load(f)
    
    result = validate_manifest_status(str(manifest_path), manifest_data=manifest_data)
    
    assert result.status == ArtifactStatus.INVALID
    assert "缺少欄位" in result.message or "missing" in result.message.lower() or "required" in result.message.lower()
    # Should mention config_hash or season (required fields)
    assert "config_hash" in result.message or "season" in result.message or "run_id" in result.message


def test_winners_v2_invalid_missing_field(fixtures_dir: Path) -> None:
    """Test that winners_v2 with missing required field returns INVALID."""
    winners_path = fixtures_dir / "winners_v2_missing_field.json"
    
    # Load data
    with winners_path.open("r", encoding="utf-8") as f:
        winners_data = json.load(f)
    
    result = validate_winners_v2_status(str(winners_path), winners_data=winners_data)
    
    assert result.status == ArtifactStatus.INVALID
    assert "缺少欄位" in result.message or "missing" in result.message.lower() or "required" in result.message.lower()
    # Should mention net_profit, max_drawdown, or trades (required in WinnerRow)
    assert any(field in result.message for field in ["net_profit", "max_drawdown", "trades", "metrics"])


def test_governance_invalid_missing_field(temp_dir: Path) -> None:
    """Test that governance with missing required field returns INVALID."""
    governance_path = temp_dir / "governance.json"
    
    # Create invalid governance (missing run_id)
    invalid_data = {
        "items": [
            {
                "candidate_id": "test:123",
                "decision": "KEEP",
            }
        ]
    }
    
    with governance_path.open("w", encoding="utf-8") as f:
        json.dump(invalid_data, f)
    
    result = validate_governance_status(str(governance_path), governance_data=invalid_data)
    
    assert result.status == ArtifactStatus.INVALID
    assert "缺少欄位" in result.message or "missing" in result.message.lower() or "required" in result.message.lower()


# Test: DIRTY status (config_hash mismatch)
def test_manifest_dirty_config_hash(fixtures_dir: Path) -> None:
    """Test that manifest with mismatched config_hash returns DIRTY."""
    manifest_path = fixtures_dir / "manifest_valid.json"
    
    # Load data
    with manifest_path.open("r", encoding="utf-8") as f:
        manifest_data = json.load(f)
    
    # Validate with different expected config_hash
    result = validate_manifest_status(
        str(manifest_path),
        manifest_data=manifest_data,
        expected_config_hash="different_hash",
    )
    
    assert result.status == ArtifactStatus.DIRTY
    assert "config_hash" in result.message.lower()


def test_winners_v2_dirty_config_hash(temp_dir: Path) -> None:
    """Test that winners_v2 with mismatched config_hash returns DIRTY."""
    winners_path = temp_dir / "winners_v2.json"
    
    # Create winners with config_hash at top level
    winners_data = {
        "config_hash": "abc123",
        "schema": "v2",
        "stage_name": "stage1_topk",
        "topk": [
            {
                "candidate_id": "donchian_atr:123",
                "strategy_id": "donchian_atr",
                "symbol": "CME.MNQ",
                "timeframe": "60m",
                "params": {},
                "metrics": {
                    "net_profit": 100.0,
                    "max_dd": -10.0,
                    "trades": 10,
                },
            }
        ],
    }
    
    with winners_path.open("w", encoding="utf-8") as f:
        json.dump(winners_data, f)
    
    result = validate_winners_v2_status(
        str(winners_path),
        winners_data=winners_data,
        expected_config_hash="different_hash",
    )
    
    assert result.status == ArtifactStatus.DIRTY
    assert "config_hash" in result.message.lower()
    assert "winners_v2.config_hash" in result.message  # Should reference top-level field


def test_governance_dirty_config_hash(temp_dir: Path) -> None:
    """Test that governance with mismatched config_hash returns DIRTY."""
    governance_path = temp_dir / "governance.json"
    
    # Create governance with config_hash at top level
    governance_data = {
        "config_hash": "abc123",
        "run_id": "test-run-123",
        "items": [
            {
                "candidate_id": "donchian_atr:123",
                "strategy_id": "donchian_atr",
                "decision": "KEEP",
                "rule_id": "R1",
                "reason": "Test",
                "run_id": "test-run-123",
                "stage": "stage1_topk",
                "evidence": [],
                "key_metrics": {},
            }
        ],
        "metadata": {},
    }
    
    with governance_path.open("w", encoding="utf-8") as f:
        json.dump(governance_data, f)
    
    result = validate_governance_status(
        str(governance_path),
        governance_data=governance_data,
        expected_config_hash="different_hash",
    )
    
    assert result.status == ArtifactStatus.DIRTY
    assert "config_hash" in result.message.lower()
    assert "governance.config_hash" in result.message  # Should reference top-level field


# Test: OK status (validation passes)
def test_manifest_ok(fixtures_dir: Path) -> None:
    """Test that valid manifest returns OK status."""
    manifest_path = fixtures_dir / "manifest_valid.json"
    
    # Load data
    with manifest_path.open("r", encoding="utf-8") as f:
        manifest_data = json.load(f)
    
    result = validate_manifest_status(
        str(manifest_path),
        manifest_data=manifest_data,
        expected_config_hash="abc123def456",
    )
    
    assert result.status == ArtifactStatus.OK
    assert "驗證通過" in result.message or "ok" in result.message.lower()


def test_winners_v2_ok(fixtures_dir: Path) -> None:
    """Test that valid winners_v2 returns OK status."""
    winners_path = fixtures_dir / "winners_v2_valid.json"
    
    # Load data
    with winners_path.open("r", encoding="utf-8") as f:
        winners_data = json.load(f)
    
    result = validate_winners_v2_status(str(winners_path), winners_data=winners_data)
    
    assert result.status == ArtifactStatus.OK
    assert "驗證通過" in result.message or "ok" in result.message.lower()


def test_governance_ok(fixtures_dir: Path) -> None:
    """Test that valid governance returns OK status."""
    governance_path = fixtures_dir / "governance_valid.json"
    
    # Load data
    with governance_path.open("r", encoding="utf-8") as f:
        governance_data = json.load(f)
    
    result = validate_governance_status(
        str(governance_path),
        governance_data=governance_data,
        expected_config_hash="abc123def456",
    )
    
    assert result.status == ArtifactStatus.OK
    assert "驗證通過" in result.message or "ok" in result.message.lower()


# Test: ArtifactReader (safe version)
def test_try_read_artifact_json(fixtures_dir: Path) -> None:
    """Test reading JSON artifact with safe version."""
    manifest_path = fixtures_dir / "manifest_valid.json"
    
    result = try_read_artifact(manifest_path)
    
    assert isinstance(result, SafeReadResult)
    assert result.is_ok
    assert result.result is not None
    assert isinstance(result.result.raw, dict)
    assert result.result.meta.source_path == str(manifest_path.resolve())
    assert len(result.result.meta.sha256) == 64  # SHA256 hex length
    assert result.result.meta.mtime_s > 0


def test_try_read_artifact_missing_file(temp_dir: Path) -> None:
    """Test that reading missing file returns error, never raises."""
    missing_path = temp_dir / "missing.json"
    
    result = try_read_artifact(missing_path)
    
    assert isinstance(result, SafeReadResult)
    assert result.is_error
    assert result.error is not None
    assert result.error.error_code == "FILE_NOT_FOUND"
    assert "not found" in result.error.message.lower()


# Test: EvidenceLink
def test_evidence_link() -> None:
    """Test EvidenceLink dataclass."""
    link = EvidenceLink(
        source_path="winners_v2.json",
        json_pointer="/rows/0/net_profit",
        note="Net profit from winners",
    )
    
    assert link.source_path == "winners_v2.json"
    assert link.json_pointer == "/rows/0/net_profit"
    assert link.note == "Net profit from winners"
    
    # Test immutability
    assert link == EvidenceLink(
        source_path="winners_v2.json",
        json_pointer="/rows/0/net_profit",
        note="Net profit from winners",
    )


# Test: Pydantic schemas can parse valid data
def test_manifest_schema_parse(fixtures_dir: Path) -> None:
    """Test that RunManifest can parse valid manifest."""
    manifest_path = fixtures_dir / "manifest_valid.json"
    
    with manifest_path.open("r", encoding="utf-8") as f:
        manifest_data = json.load(f)
    
    manifest = RunManifest(**manifest_data)
    
    assert manifest.run_id == "test-run-123"
    assert manifest.season == "2025Q4"
    assert manifest.config_hash == "abc123def456"
    assert len(manifest.stages) == 1
    assert manifest.stages[0].name == "stage0"


def test_winners_v2_schema_parse(fixtures_dir: Path) -> None:
    """Test that WinnersV2 can parse valid winners."""
    winners_path = fixtures_dir / "winners_v2_valid.json"
    
    with winners_path.open("r", encoding="utf-8") as f:
        winners_data = json.load(f)
    
    winners = WinnersV2(**winners_data)
    
    assert winners.schema_name == "v2"  # schema_name is alias for "schema" in JSON
    assert winners.stage_name == "stage1_topk"
    assert winners.topk is not None
    assert len(winners.topk) == 1


def test_governance_schema_parse(fixtures_dir: Path) -> None:
    """Test that GovernanceReport can parse valid governance."""
    governance_path = fixtures_dir / "governance_valid.json"
    
    with governance_path.open("r", encoding="utf-8") as f:
        governance_data = json.load(f)
    
    governance = GovernanceReport(**governance_data)
    
    assert governance.run_id == "test-run-123"
    assert governance.items is not None
    assert len(governance.items) == 1
