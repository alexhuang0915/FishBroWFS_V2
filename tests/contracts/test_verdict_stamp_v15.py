"""
Tests for Verdict Stamp v1.5 Governance Trust Lock.
"""

import json
from datetime import datetime

import pytest

from src.contracts.portfolio.verdict_stamp_v1 import (
    VerdictStampV1,
    VERDICT_STAMP_SCHEMA_VERSION,
)


class TestVerdictStampV1:
    """Test Verdict Stamp v1 model."""
    
    def test_model_creation(self):
        """Test basic model creation."""
        stamp = VerdictStampV1(
            policy_version="v2.1.0",
            dictionary_version="v1.5.0",
            schema_contract_version="v1",
            evaluator_version="v1.5.0",
            created_at_iso="2026-01-17T12:00:00Z",
        )
        
        assert stamp.schema_version == "v1.0"
        assert stamp.policy_version == "v2.1.0"
        assert stamp.dictionary_version == "v1.5.0"
        assert stamp.schema_contract_version == "v1"
        assert stamp.evaluator_version == "v1.5.0"
    
    def test_model_frozen(self):
        """Test that model is frozen (cannot mutate)."""
        stamp = VerdictStampV1(
            policy_version="v1",
            dictionary_version="v1",
            schema_contract_version="v1",
            evaluator_version="v1",
            created_at_iso="2026-01-17T12:00:00Z",
        )
        
        # Should not be able to modify frozen model
        with pytest.raises(Exception):
            stamp.policy_version = "modified"
    
    def test_create_for_job(self):
        """Test creating stamp with automatic version detection."""
        stamp = VerdictStampV1.create_for_job(
            job_id="test_job_123",
            policy_version="custom_policy_v1",
            dictionary_version="custom_dict_v1",
            schema_contract_version="v2",
            evaluator_version="custom_eval_v1",
        )
        
        assert stamp.policy_version == "custom_policy_v1"
        assert stamp.dictionary_version == "custom_dict_v1"
        assert stamp.schema_contract_version == "v2"
        assert stamp.evaluator_version == "custom_eval_v1"
        assert stamp.created_at_iso is not None
        
        # Parse ISO timestamp
        parsed = datetime.fromisoformat(stamp.created_at_iso.replace("Z", "+00:00"))
        assert parsed.year == 2026  # Current year
    
    def test_create_for_job_auto_detect(self):
        """Test automatic version detection."""
        stamp = VerdictStampV1.create_for_job(job_id="test_job")
        
        # Should have detected versions
        assert stamp.policy_version is not None
        assert stamp.dictionary_version is not None
        assert stamp.schema_contract_version is not None
        assert stamp.evaluator_version is not None
        
        # Dictionary version should be v1.5.0 (from gate_reason_explain)
        assert stamp.dictionary_version == "v1.5.0"
        
        # Schema contract version should be "v1" (from GateSummaryV1)
        assert stamp.schema_contract_version == "v1"
    
    def test_to_dict_from_dict(self):
        """Test dictionary conversion."""
        stamp = VerdictStampV1(
            policy_version="v1",
            dictionary_version="v1.5.0",
            schema_contract_version="v1",
            evaluator_version="v1.5.0",
            created_at_iso="2026-01-17T12:00:00Z",
        )
        
        # Convert to dict
        data = stamp.to_dict()
        assert data["schema_version"] == "v1.0"
        assert data["policy_version"] == "v1"
        assert data["dictionary_version"] == "v1.5.0"
        
        # Convert back
        stamp2 = VerdictStampV1.from_dict(data)
        assert stamp2.policy_version == stamp.policy_version
        assert stamp2.dictionary_version == stamp.dictionary_version
    
    def test_json_serialization(self):
        """Test JSON serialization/deserialization."""
        stamp = VerdictStampV1(
            policy_version="v2.0.0",
            dictionary_version="v1.5.0",
            schema_contract_version="v1",
            evaluator_version="v1.5.0",
            created_at_iso="2026-01-17T12:00:00Z",
        )
        
        # Serialize
        json_str = stamp.model_dump_json(indent=2)
        data = json.loads(json_str)
        
        assert data["schema_version"] == "v1.0"
        assert data["policy_version"] == "v2.0.0"
        
        # Deserialize
        stamp2 = VerdictStampV1.model_validate(data)
        assert stamp2.policy_version == stamp.policy_version
        assert stamp2.dictionary_version == stamp.dictionary_version
    
    def test_compare_with_current(self):
        """Test version comparison with current system."""
        stamp = VerdictStampV1(
            policy_version="v1.0.0",
            dictionary_version="v1.5.0",
            schema_contract_version="v1",
            evaluator_version="v1.5.0",
            created_at_iso="2026-01-17T12:00:00Z",
        )
        
        comparison = stamp.compare_with_current()
        
        assert "stamp" in comparison
        assert "current" in comparison
        assert "matches" in comparison
        assert "warnings" in comparison
        
        # Stamp should match itself
        assert comparison["stamp"]["dictionary_version"] == "v1.5.0"
        
        # Current dictionary version should be detected
        assert "dictionary_version" in comparison["current"]
        
        # Should have match results
        assert "dictionary_version" in comparison["matches"]
    
    def test_schema_version_constant(self):
        """Test schema version constant matches model."""
        stamp = VerdictStampV1(
            policy_version="v1",
            dictionary_version="v1",
            schema_contract_version="v1",
            evaluator_version="v1",
            created_at_iso="2026-01-17T12:00:00Z",
        )
        
        assert stamp.schema_version == VERDICT_STAMP_SCHEMA_VERSION


class TestVerdictStampGoldenFixtures:
    """Test golden fixtures for verdict stamp."""
    
    def test_golden_fixture_structure(self):
        """Verify golden fixture has expected structure."""
        stamp = VerdictStampV1(
            policy_version="registry_v2.1.0",
            dictionary_version="v1.5.0",
            schema_contract_version="v1",
            evaluator_version="v1.5.0",
            created_at_iso="2026-01-17T12:00:00Z",
        )
        
        # Verify structure
        data = stamp.to_dict()
        assert "schema_version" in data
        assert "policy_version" in data
        assert "dictionary_version" in data
        assert "schema_contract_version" in data
        assert "evaluator_version" in data
        assert "created_at_iso" in data
        
        # All fields should be strings
        for value in data.values():
            assert isinstance(value, str)
    
    def test_version_constants_consistent(self):
        """Test that version constants are consistent across modules."""
        from src.contracts.portfolio.gate_reason_explain import DICTIONARY_VERSION
        
        stamp = VerdictStampV1.create_for_job(job_id="test")
        
        # Dictionary version should match
        assert stamp.dictionary_version == DICTIONARY_VERSION
        
        # Schema version constants should match
        from src.contracts.portfolio.evidence_snapshot_v1 import EVIDENCE_SNAPSHOT_SCHEMA_VERSION
        assert EVIDENCE_SNAPSHOT_SCHEMA_VERSION == "v1.0"
        assert VERDICT_STAMP_SCHEMA_VERSION == "v1.0"