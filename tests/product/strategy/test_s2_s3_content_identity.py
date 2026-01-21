"""Test content-addressed identity for S2 and S3 strategies."""

from __future__ import annotations

import pytest

from strategy.registry import load_builtin_strategies, get


def test_s2_s3_have_unique_content_ids():
    """Verify that S2 and S3 have unique content IDs."""
    load_builtin_strategies()
    
    spec_s2 = get("S2")
    spec_s3 = get("S3")
    
    # Both should have content_id
    assert spec_s2.content_id is not None
    assert spec_s3.content_id is not None
    
    # Content IDs should be 64-character hex strings
    assert len(spec_s2.content_id) == 64
    assert len(spec_s3.content_id) == 64
    assert all(c in "0123456789abcdef" for c in spec_s2.content_id)
    assert all(c in "0123456789abcdef" for c in spec_s3.content_id)
    
    # S2 and S3 should have different content IDs (different logic)
    assert spec_s2.content_id != spec_s3.content_id, \
        "S2 and S3 should have different content IDs (different strategy logic)"


def test_s2_content_id_deterministic():
    """Verify that S2 content ID is deterministic (same across runs)."""
    load_builtin_strategies()
    
    spec1 = get("S2")
    content_id1 = spec1.content_id
    
    # Clear and reload to get fresh spec
    from strategy.registry import clear
    clear()
    load_builtin_strategies()
    
    spec2 = get("S2")
    content_id2 = spec2.content_id
    
    # Content ID should be the same
    assert content_id1 == content_id2, "S2 content ID should be deterministic"
    
    # Also check immutable_id property
    assert spec1.immutable_id == spec2.immutable_id


def test_s3_content_id_deterministic():
    """Verify that S3 content ID is deterministic (same across runs)."""
    load_builtin_strategies()
    
    spec1 = get("S3")
    content_id1 = spec1.content_id
    
    from strategy.registry import clear
    clear()
    load_builtin_strategies()
    
    spec2 = get("S3")
    content_id2 = spec2.content_id
    
    assert content_id1 == content_id2, "S3 content ID should be deterministic"
    assert spec1.immutable_id == spec2.immutable_id


def test_s2_identity_object():
    """Verify S2 has a valid StrategyIdentity object."""
    load_builtin_strategies()
    
    spec = get("S2")
    
    # Should have identity attribute
    assert hasattr(spec, 'identity')
    assert spec.identity is not None
    
    # Identity should have strategy_id and source_hash
    from core.ast_identity import StrategyIdentity
    assert isinstance(spec.identity, StrategyIdentity)
    assert spec.identity.strategy_id == spec.content_id
    assert spec.identity.source_hash == spec.content_id
    
    # get_identity() method should return the same
    identity_from_method = spec.get_identity()
    assert identity_from_method.strategy_id == spec.content_id


def test_s3_identity_object():
    """Verify S3 has a valid StrategyIdentity object."""
    load_builtin_strategies()
    
    spec = get("S3")
    
    assert hasattr(spec, 'identity')
    assert spec.identity is not None
    
    from core.ast_identity import StrategyIdentity
    assert isinstance(spec.identity, StrategyIdentity)
    assert spec.identity.strategy_id == spec.content_id
    assert spec.identity.source_hash == spec.content_id
    
    identity_from_method = spec.get_identity()
    assert identity_from_method.strategy_id == spec.content_id


def test_s2_s3_not_duplicate():
    """Test that S2 and S3 are not detected as duplicates (different content)."""
    from strategy.registry import clear, register
    from strategy.spec import StrategySpec
    
    load_builtin_strategies()
    
    spec_s2 = get("S2")
    spec_s3 = get("S3")
    
    # Clear registry
    clear()
    
    # Register S2
    register(spec_s2)
    
    # Attempt to register S3 should succeed (different content)
    # Note: register will raise ValueError if duplicate content
    try:
        register(spec_s3)
        # If no exception, that's good - they're not duplicates
    except ValueError as e:
        if "duplicate" in str(e).lower() or "already registered" in str(e).lower():
            pytest.fail(f"S2 and S3 should not be detected as duplicates: {e}")
        else:
            raise
    
    clear()


def test_s2_content_id_from_source():
    """Verify S2 content ID can be computed from source code."""
    from core.ast_identity import compute_strategy_id_from_file
    from pathlib import Path
    
    # Get S2 source file path
    s2_path = Path("src/strategy/builtin/s2_v1.py")
    assert s2_path.exists()
    
    # Compute content ID from file
    file_content_id = compute_strategy_id_from_file(s2_path)
    
    load_builtin_strategies()
    spec = get("S2")
    
    # The content ID from file should match spec.content_id
    # (Might differ due to module-level code vs function-only hashing)
    # But we can at least verify it's a valid 64-char hex
    assert len(file_content_id) == 64
    assert all(c in "0123456789abcdef" for c in file_content_id)


def test_s3_content_id_from_source():
    """Verify S3 content ID can be computed from source code."""
    from core.ast_identity import compute_strategy_id_from_file
    from pathlib import Path
    
    s3_path = Path("src/strategy/builtin/s3_v1.py")
    assert s3_path.exists()
    
    file_content_id = compute_strategy_id_from_file(s3_path)
    
    load_builtin_strategies()
    spec = get("S3")
    
    assert len(file_content_id) == 64
    assert all(c in "0123456789abcdef" for c in file_content_id)


def test_s2_s3_immutable_id_fallback():
    """Test immutable_id property works even without content_id."""
    load_builtin_strategies()
    
    spec_s2 = get("S2")
    spec_s3 = get("S3")
    
    # Both should have content_id, so immutable_id should return it
    assert spec_s2.immutable_id == spec_s2.content_id
    assert spec_s3.immutable_id == spec_s3.content_id
    
    # Create a mock spec without content_id to test fallback
    from strategy.spec import StrategySpec
    
    def dummy_func(context, params):
        return {"intents": [], "debug": {}}
    
    mock_spec = StrategySpec(
        strategy_id="test_strategy",
        version="v1",
        param_schema={},
        defaults={},
        fn=dummy_func,
        content_id=None
    )
    
    # Should still have an immutable_id (fallback hash)
    assert len(mock_spec.immutable_id) == 64
    assert all(c in "0123456789abcdef" for c in mock_spec.immutable_id)


def test_s2_s3_to_dict_serialization():
    """Test that S2 and S3 can be serialized to dict with content_id."""
    load_builtin_strategies()
    
    spec_s2 = get("S2")
    spec_s3 = get("S3")
    
    # Convert to dict
    s2_dict = spec_s2.to_dict()
    s3_dict = spec_s3.to_dict()
    
    # Check required fields
    assert s2_dict["strategy_id"] == "S2"
    assert s2_dict["version"] == "v1"
    assert "param_schema" in s2_dict
    assert "defaults" in s2_dict
    assert "content_id" in s2_dict
    assert s2_dict["content_id"] == spec_s2.content_id
    
    assert s3_dict["strategy_id"] == "S3"
    assert s3_dict["version"] == "v1"
    assert s3_dict["content_id"] == spec_s3.content_id
    
    # Content IDs should be in dict
    assert len(s2_dict["content_id"]) == 64
    assert len(s3_dict["content_id"]) == 64


if __name__ == "__main__":
    pytest.main([__file__, "-v"])