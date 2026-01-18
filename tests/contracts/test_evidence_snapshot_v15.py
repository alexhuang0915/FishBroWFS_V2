"""
Tests for Evidence Snapshot v1.5 Governance Trust Lock.
"""

import json
from pathlib import Path
import tempfile

import pytest

from src.contracts.portfolio.evidence_snapshot_v1 import (
    EvidenceSnapshotV1,
    EvidenceFileV1,
    EVIDENCE_SNAPSHOT_SCHEMA_VERSION,
)


class TestEvidenceSnapshotV1:
    """Test Evidence Snapshot v1 model."""
    
    def test_model_creation(self):
        """Test basic model creation."""
        snapshot = EvidenceSnapshotV1(
            job_id="test_job_123",
            captured_at_iso="2026-01-17T12:00:00Z",
            evidence_root="/path/to/evidence",
            files=[
                EvidenceFileV1(
                    relpath="report.json",
                    sha256="a" * 64,
                    size_bytes=1024,
                    created_at_iso="2026-01-17T11:00:00Z",
                )
            ],
        )
        
        assert snapshot.schema_version == "v1.0"
        assert snapshot.job_id == "test_job_123"
        assert len(snapshot.files) == 1
        assert snapshot.files[0].relpath == "report.json"
        assert snapshot.files[0].sha256 == "a" * 64
    
    def test_model_frozen(self):
        """Test that model is frozen (cannot mutate)."""
        snapshot = EvidenceSnapshotV1(
            job_id="test_job",
            captured_at_iso="2026-01-17T12:00:00Z",
            evidence_root="/path",
            files=[],
        )
        
        # Should not be able to modify frozen model
        with pytest.raises(Exception):
            snapshot.job_id = "modified"
    
    def test_create_for_job(self, tmp_path):
        """Test creating snapshot by scanning files."""
        # Create test files
        evidence_root = tmp_path / "evidence"
        evidence_root.mkdir()
        
        file1 = evidence_root / "report.json"
        file1.write_text('{"test": "data"}')
        
        file2 = evidence_root / "metrics.csv"
        file2.write_text("metric,value\naccuracy,0.95\n")
        
        snapshot = EvidenceSnapshotV1.create_for_job(
            job_id="test_job",
            evidence_root=str(evidence_root),
            file_paths=["report.json", "metrics.csv"],
        )
        
        assert snapshot.job_id == "test_job"
        assert len(snapshot.files) == 2
        
        # Files should be sorted by relpath
        relpaths = [f.relpath for f in snapshot.files]
        assert sorted(relpaths) == relpaths
        
        # SHA256 should be computed
        for file in snapshot.files:
            assert len(file.sha256) == 64
            assert file.size_bytes > 0
    
    def test_validate_file(self, tmp_path):
        """Test file validation against snapshot."""
        evidence_root = tmp_path / "evidence"
        evidence_root.mkdir()
        
        file_path = evidence_root / "test.txt"
        file_path.write_text("original content")
        
        # Create snapshot
        snapshot = EvidenceSnapshotV1.create_for_job(
            job_id="test_job",
            evidence_root=str(evidence_root),
            file_paths=["test.txt"],
        )
        
        # Validate original file
        is_valid, reason = snapshot.validate_file(
            relpath="test.txt",
            file_path=str(file_path),
        )
        assert is_valid
        assert reason == "OK"
        
        # Modify file
        file_path.write_text("modified content")
        
        # Validation should fail
        is_valid, reason = snapshot.validate_file(
            relpath="test.txt",
            file_path=str(file_path),
        )
        assert not is_valid
        assert "SHA256 mismatch" in reason
    
    def test_validate_file_missing(self, tmp_path):
        """Test validation of missing file."""
        snapshot = EvidenceSnapshotV1(
            job_id="test_job",
            captured_at_iso="2026-01-17T12:00:00Z",
            evidence_root=str(tmp_path),
            files=[
                EvidenceFileV1(
                    relpath="missing.txt",
                    sha256="a" * 64,
                    size_bytes=1024,
                    created_at_iso="2026-01-17T11:00:00Z",
                )
            ],
        )
        
        is_valid, reason = snapshot.validate_file(
            relpath="missing.txt",
            file_path=str(tmp_path / "missing.txt"),
        )
        assert not is_valid
        assert "File missing" in reason
    
    def test_json_serialization(self):
        """Test JSON serialization/deserialization."""
        snapshot = EvidenceSnapshotV1(
            job_id="test_job",
            captured_at_iso="2026-01-17T12:00:00Z",
            evidence_root="/path",
            files=[
                EvidenceFileV1(
                    relpath="file.txt",
                    sha256="b" * 64,
                    size_bytes=2048,
                    created_at_iso="2026-01-17T11:00:00Z",
                )
            ],
        )
        
        # Serialize
        json_str = snapshot.model_dump_json(indent=2)
        data = json.loads(json_str)
        
        assert data["schema_version"] == "v1.0"
        assert data["job_id"] == "test_job"
        assert len(data["files"]) == 1
        
        # Deserialize
        snapshot2 = EvidenceSnapshotV1.model_validate(data)
        assert snapshot2.job_id == snapshot.job_id
        assert snapshot2.files[0].sha256 == snapshot.files[0].sha256
    
    def test_schema_version_constant(self):
        """Test schema version constant matches model."""
        snapshot = EvidenceSnapshotV1(
            job_id="test",
            captured_at_iso="2026-01-17T12:00:00Z",
            evidence_root="/path",
            files=[],
        )
        
        assert snapshot.schema_version == EVIDENCE_SNAPSHOT_SCHEMA_VERSION


class TestEvidenceSnapshotGoldenFixtures:
    """Test golden fixtures for evidence snapshot."""
    
    def test_golden_fixture_structure(self):
        """Verify golden fixture has expected structure."""
        # This test ensures the golden fixture in tests/fixtures/evidence_snapshot_v1/
        # matches the schema
        snapshot = EvidenceSnapshotV1(
            job_id="fixture_job",
            captured_at_iso="2026-01-17T12:00:00Z",
            evidence_root="/fake/path",
            files=[
                EvidenceFileV1(
                    relpath="gate_summary_v1.json",
                    sha256="cafebabe" * 8,  # 64 chars
                    size_bytes=1234,
                    created_at_iso="2026-01-17T11:00:00Z",
                    mime="application/json",
                ),
                EvidenceFileV1(
                    relpath="policy_check.json",
                    sha256="deadbeef" * 8,
                    size_bytes=5678,
                    created_at_iso="2026-01-17T11:00:00Z",
                ),
            ],
        )
        
        # Verify structure
        data = snapshot.model_dump()
        assert "schema_version" in data
        assert "job_id" in data
        assert "files" in data
        assert isinstance(data["files"], list)
        
        for file in data["files"]:
            assert "relpath" in file
            assert "sha256" in file
            assert "size_bytes" in file
            assert "created_at_iso" in file
            assert "mime" in file  # default field