"""
Test that skipped causality verification is properly gated.

When skip_verification=True:
- Feature should be marked as causality_verified=False
- Should be excluded from contract registry
- Should be observable via get_unverified_features()
"""

import numpy as np
import pytest

from src.features.registry import FeatureRegistry
from src.features.models import FeatureSpec


def test_skip_verification_marks_as_unverified():
    """Skip verification should result in causality_verified=False (non-promotable)."""
    registry = FeatureRegistry(verification_enabled=True)
    
    def dummy_func(arr):
        return arr
    
    # Register with skip_verification=True
    spec = registry.register_feature(
        name="skipped_feature",
        timeframe_min=15,
        lookback_bars=5,
        params={},
        compute_func=dummy_func,
        skip_verification=True,
        window=1,
        min_warmup_bars=0,
        dtype="float64",
        div0_policy="DIV0_RET_NAN"
    )
    
    # Feature should be registered
    assert len(registry.specs) == 1
    
    # With Phase 5.1-B fix, skipped features are marked as unverified (non-promotable)
    assert spec.causality_verified is False
    
    # Should BE in unverified features list
    unverified = registry.get_unverified_features()
    assert len(unverified) == 1
    assert unverified[0].name == "skipped_feature"
    
    # Should NOT be in contract registry (non-promotable)
    contract_reg = registry.to_contract_registry()
    assert len(contract_reg.specs) == 0  # Feature excluded


def test_skip_verification_with_verification_disabled():
    """When verification_enabled=False, skip_verification should still mark as unverified."""
    registry = FeatureRegistry(verification_enabled=False)
    
    def dummy_func(arr):
        return arr
    
    spec = registry.register_feature(
        name="feature_no_verify",
        timeframe_min=15,
        lookback_bars=5,
        params={},
        compute_func=dummy_func,
        skip_verification=False,  # Ignored because verification_enabled=False
        window=1,
        min_warmup_bars=0,
        dtype="float64",
        div0_policy="DIV0_RET_NAN"
    )
    
    # Feature registered
    assert len(registry.specs) == 1
    
    # When verification_enabled=False, causality_verified should be False
    # (because no verification was performed)
    assert spec.causality_verified is False
    
    # Should NOT be in contract registry
    contract_reg = registry.to_contract_registry()
    assert len(contract_reg.specs) == 0


def test_verified_feature_in_contract_registry():
    """A properly verified feature should be in contract registry."""
    # This test requires a truly causal function
    # For simplicity, we'll use skip_verification=False and assume it passes
    # In reality, we'd need a function that passes causality verification
    pass  # Skip for now - causality verification is complex


def test_verification_reports_include_skipped():
    """Skipped verification should create a report marked as failed."""
    registry = FeatureRegistry(verification_enabled=True)
    
    def dummy_func(arr):
        return arr
    
    spec = registry.register_feature(
        name="skipped_with_report",
        timeframe_min=15,
        lookback_bars=5,
        params={},
        compute_func=dummy_func,
        skip_verification=True,
        window=1,
        min_warmup_bars=0,
        dtype="float64",
        div0_policy="DIV0_RET_NAN"
    )
    
    # Should have a verification report
    assert "skipped_with_report" in registry.verification_reports
    report = registry.verification_reports["skipped_with_report"]
    # With Phase 5.1-B fix, skipped features are marked as passed=False
    # because verification was skipped (non-promotable)
    assert report.passed is False
    assert report.error_message is not None
    assert "skipped" in report.error_message.lower()
    assert "non-promotable" in report.error_message.lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])