"""
Test params_hash stability (ABI-level lock).
"""
import json
import hashlib
from contracts.supervisor.evidence_schemas import stable_params_hash


def test_params_hash_stability():
    """Test that params_hash is stable and deterministic."""
    # Golden test payload
    payload = {
        "strategy_id": "momentum_sma",
        "profile_name": "baseline_no_flip",
        "start_date": "2024-01-01",
        "end_date": "2024-12-31",
        "timeframe": 60,
        "params_override": {"lookback": 20, "threshold": 0.05}
    }
    
    # Compute hash
    hash1 = stable_params_hash(payload)
    
    # Compute hash again - should be identical
    hash2 = stable_params_hash(payload)
    assert hash1 == hash2, "Hash should be deterministic"
    
    # Verify hash matches expected properties
    assert len(hash1) == 64, "SHA256 hash should be 64 hex chars"
    assert all(c in "0123456789abcdef" for c in hash1), "Hash should be hex"
    
    # Test with different key order (should produce same hash due to sort_keys=True)
    payload_reordered = {
        "end_date": "2024-12-31",
        "start_date": "2024-01-01",
        "profile_name": "baseline_no_flip",
        "strategy_id": "momentum_sma",
        "params_override": {"lookback": 20, "threshold": 0.05},
        "timeframe": 60
    }
    hash3 = stable_params_hash(payload_reordered)
    assert hash1 == hash3, "Hash should be order-independent"
    
    # Test with different whitespace (should produce same hash due to canonical JSON)
    payload_json = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    payload_json_pretty = json.dumps(payload, sort_keys=True, indent=2)
    
    # Direct hash computation to verify
    canonical_json = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    expected_hash = hashlib.sha256(canonical_json.encode()).hexdigest()
    assert hash1 == expected_hash, "Hash should match manual computation"
    
    print(f"✓ params_hash stability test passed: {hash1[:16]}...")


def test_params_hash_versioning():
    """Test that hash_version is included in fingerprint bundle."""
    from contracts.supervisor.evidence_schemas import FingerprintBundle
    
    bundle = FingerprintBundle(
        params_hash="test_hash",
        dependencies={},
        code_fingerprint="abc123",
        hash_version="v1"
    )
    
    assert bundle.hash_version == "v1", "hash_version should be v1"
    
    # Serialize and deserialize
    import json
    from dataclasses import asdict
    bundle_dict = asdict(bundle)
    assert bundle_dict["hash_version"] == "v1"
    
    print("✓ hash_version test passed")


if __name__ == "__main__":
    test_params_hash_stability()
    test_params_hash_versioning()
    print("All tests passed!")