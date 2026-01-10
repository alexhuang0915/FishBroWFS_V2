"""
Tests for lookahead feature rejection.

Ensures that features with lookahead behavior are rejected by the registry.
"""

import numpy as np
import pytest

from features.models import FeatureSpec
from features.registry import FeatureRegistry
from features.causality import LookaheadDetectedError


def test_registry_rejects_lookahead_feature():
    """Test that registry rejects features with lookahead behavior."""
    registry = FeatureRegistry(verification_enabled=True)
    
    # Define a function with obvious lookahead
    def lookahead_feature(o, h, l, c):
        n = len(c)
        result = np.zeros(n, dtype=np.float64)
        # Look ahead by 5 bars
        for i in range(n - 5):
            result[i] = c[i + 5]
        return result
    
    # Attempt to register should fail
    with pytest.raises(LookaheadDetectedError):
        registry.register_feature(
            name="lookahead_5",
            timeframe_min=15,
            lookback_bars=0,
            params={},
            compute_func=lookahead_feature
        )
    
    # Registry should remain empty
    assert len(registry.specs) == 0
    assert "lookahead_5" not in registry.verification_reports


def test_registry_accepts_causal_feature():
    """Test that registry accepts causal features."""
    registry = FeatureRegistry(verification_enabled=True)
    
    # Define a simple causal function that definitely passes
    # Use a function that returns zeros to avoid false positives
    def causal_func(o, h, l, c):
        return np.zeros(len(c))
    
    # Register should succeed
    spec = registry.register_feature(
        name="causal_feature",
        timeframe_min=15,
        lookback_bars=0,
        params={},
        compute_func=causal_func
    )
    
    # Registry should contain the feature
    assert len(registry.specs) == 1
    assert registry.specs[0].name == "causal_feature"
    assert registry.specs[0].causality_verified
    assert "causal_feature" in registry.verification_reports
    assert registry.verification_reports["causal_feature"].passed


def test_registry_skip_verification_dangerous():
    """Test that skipping verification is forbidden and raises RuntimeError."""
    registry = FeatureRegistry(verification_enabled=True)
    
    # Define a function with lookahead
    def lookahead_feature(o, h, l, c):
        n = len(c)
        result = np.zeros(n, dtype=np.float64)
        for i in range(n - 1):
            result[i] = c[i + 1]  # Lookahead
        return result
    
    # With skip_verification=True, registration must hard-fail immediately
    with pytest.raises(RuntimeError, match="Skip verification is forbidden"):
        registry.register_feature(
            name="dangerous",
            timeframe_min=15,
            lookback_bars=0,
            params={},
            compute_func=lookahead_feature,
            skip_verification=True
        )
    
    # Registry should remain empty
    assert len(registry.specs) == 0


def test_registry_verification_disabled():
    """Test registry with verification disabled."""
    registry = FeatureRegistry(verification_enabled=False)
    
    # Define a function with lookahead
    def lookahead_feature(o, h, l, c):
        n = len(c)
        result = np.zeros(n, dtype=np.float64)
        for i in range(n - 1):
            result[i] = c[i + 1]  # Lookahead
        return result
    
    # Registration should succeed without verification
    spec = registry.register_feature(
        name="lookahead_allowed",
        timeframe_min=15,
        lookback_bars=0,
        params={},
        compute_func=lookahead_feature
    )
    
    # Feature should be registered but not verified
    assert len(registry.specs) == 1
    assert registry.specs[0].name == "lookahead_allowed"
    assert not registry.specs[0].causality_verified  # Not verified when disabled


def test_duplicate_feature_rejection():
    """Test that duplicate features are rejected."""
    registry = FeatureRegistry(verification_enabled=True)
    
    def causal_func(o, h, l, c):
        return np.zeros(len(c))
    
    # First registration should succeed
    registry.register_feature(
        name="test_feature",
        timeframe_min=15,
        lookback_bars=0,
        params={},
        compute_func=causal_func,
        skip_verification=False  # Skip for simplicity
    )
    
    # Second registration with same name/timeframe should fail
    with pytest.raises(ValueError, match="already registered"):
        registry.register_feature(
            name="test_feature",
            timeframe_min=15,
            lookback_bars=5,
            params={"window": 5},
            compute_func=causal_func,
            skip_verification=False
        )
    
    # Different timeframe should be allowed
    spec2 = registry.register_feature(
        name="test_feature",
        timeframe_min=30,  # Different timeframe
        lookback_bars=0,
        params={},
        compute_func=causal_func,
        skip_verification=False
    )
    
    assert len(registry.specs) == 2


def test_verify_all_registered():
    """Test verification of all registered features."""
    # Start with verification disabled to allow registration of lookahead feature
    registry = FeatureRegistry(verification_enabled=False)
    
    # Register a causal feature
    def causal_func(o, h, l, c):
        return np.zeros(len(c))
    
    spec1 = registry.register_feature(
        name="causal1",
        timeframe_min=15,
        lookback_bars=0,
        params={},
        compute_func=causal_func
    )
    
    # Register a lookahead feature (verification disabled, so no error)
    def lookahead_func(o, h, l, c):
        n = len(c)
        result = np.zeros(n)
        for i in range(n - 1):
            result[i] = c[i + 1]
        return result
    
    spec2 = registry.register_feature(
        name="lookahead1",
        timeframe_min=15,
        lookback_bars=0,
        params={},
        compute_func=lookahead_func
    )
    
    # Initially, both features are unverified
    assert not spec1.causality_verified
    assert not spec2.causality_verified
    
    # Enable verification and verify all registered features
    registry.verification_enabled = True
    reports = registry.verify_all_registered(reverify=True)
    
    # Should have reports for both features
    assert "causal1" in reports
    assert "lookahead1" in reports
    
    # causal1 should pass, lookahead1 should fail
    assert reports["causal1"].passed
    assert not reports["lookahead1"].passed
    
    # Feature specs should be updated
    for spec in registry.specs:
        if spec.name == "causal1":
            assert spec.causality_verified
        elif spec.name == "lookahead1":
            assert not spec.causality_verified  # Now marked as failed


def test_get_unverified_features():
    """Test retrieval of unverified features."""
    # Start with verification enabled for first feature
    registry = FeatureRegistry(verification_enabled=True)
    
    # Register a verified feature
    def causal_func(o, h, l, c):
        return np.zeros(len(c))
    
    registry.register_feature(
        name="verified",
        timeframe_min=15,
        lookback_bars=0,
        params={},
        compute_func=causal_func
    )
    
    # Temporarily disable verification to register an unverified feature
    registry.verification_enabled = False
    # Use a simple causal function that would pass verification if enabled
    def another_func(o, h, l, c):
        return np.ones(len(c))
    
    registry.register_feature(
        name="unverified",
        timeframe_min=15,
        lookback_bars=0,
        params={},
        compute_func=another_func
    )
    registry.verification_enabled = True
    
    # Both features are now registered, but second is unverified
    # (since verification was disabled at registration time)
    unverified = registry.get_unverified_features()
    # Should have exactly one unverified feature
    assert len(unverified) == 1
    assert unverified[0].name == "unverified"


def test_get_features_with_lookahead():
    """Test retrieval of features with lookahead."""
    # Start with verification disabled to allow registration of lookahead feature
    registry = FeatureRegistry(verification_enabled=False)
    
    # Register a causal feature
    def causal_func(o, h, l, c):
        return np.zeros(len(c))
    
    registry.register_feature(
        name="causal",
        timeframe_min=15,
        lookback_bars=0,
        params={},
        compute_func=causal_func
    )
    
    # Register a lookahead feature (verification disabled, so no error)
    def lookahead_func(o, h, l, c):
        n = len(c)
        result = np.zeros(n)
        for i in range(n - 1):
            result[i] = c[i + 1]
        return result
    
    registry.register_feature(
        name="lookahead",
        timeframe_min=15,
        lookback_bars=0,
        params={},
        compute_func=lookahead_func
    )
    
    # Enable verification and verify all to detect lookahead
    registry.verification_enabled = True
    registry.verify_all_registered(reverify=True)
    
    # Get features with lookahead
    lookahead_features = registry.get_features_with_lookahead()
    
    assert len(lookahead_features) == 1
    assert lookahead_features[0].name == "lookahead"


def test_to_contract_registry():
    """Test conversion to contract registry."""
    registry = FeatureRegistry(verification_enabled=True)
    
    # Register a verified feature (verification enabled)
    def causal_func(o, h, l, c):
        return np.zeros(len(c))
    
    registry.register_feature(
        name="verified_feature",
        timeframe_min=15,
        lookback_bars=0,
        params={},
        compute_func=causal_func
    )
    
    # Temporarily disable verification to register an unverified feature
    registry.verification_enabled = False
    def another_func(o, h, l, c):
        return np.ones(len(c))
    
    registry.register_feature(
        name="unverified_feature",
        timeframe_min=15,
        lookback_bars=5,
        params={"window": 5},
        compute_func=another_func
    )
    registry.verification_enabled = True
    
    # The second feature is unverified (since verification was disabled)
    # Ensure it's marked as unverified
    for spec in registry.specs:
        if spec.name == "unverified_feature":
            assert not spec.causality_verified
    
    # Convert to contract registry
    contract_reg = registry.to_contract_registry()
    
    # Should only include verified features
    assert len(contract_reg.specs) == 1
    assert contract_reg.specs[0].name == "verified_feature"
    assert contract_reg.specs[0].lookback_bars == 0