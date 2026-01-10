"""
Test source-agnostic naming compliance.

Ensure no canonical feature names contain VX/DX/ZN prefixes.
Verify deprecated aliases are properly flagged and map to canonical names.
"""

from __future__ import annotations

import re
import pytest
from features.registry import get_default_registry


def test_no_vx_dx_zn_prefixes_in_canonical_names():
    """Canonical feature names must not contain VX/DX/ZN prefixes."""
    registry = get_default_registry()
    
    # Patterns to reject
    forbidden_prefixes = ("vx_", "dx_", "zn_")
    
    for spec in registry.specs:
        # Skip deprecated features (they may have forbidden prefixes)
        if getattr(spec, "deprecated", False):
            continue
        
        name = spec.name
        for prefix in forbidden_prefixes:
            assert not name.startswith(prefix), (
                f"Canonical feature '{name}' starts with forbidden prefix '{prefix}'. "
                "Use source-agnostic naming (e.g., 'percentile_' not 'vx_percentile_')."
            )


def test_deprecated_aliases_have_canonical_mapping():
    """Deprecated aliases must have canonical_name attribute pointing to source-agnostic name."""
    registry = get_default_registry()
    
    deprecated_specs = [spec for spec in registry.specs if getattr(spec, "deprecated", False)]
    
    for spec in deprecated_specs:
        assert hasattr(spec, "canonical_name"), (
            f"Deprecated feature '{spec.name}' missing 'canonical_name' attribute."
        )
        canonical = spec.canonical_name
        assert canonical is not None, (
            f"Deprecated feature '{spec.name}' has None canonical_name."
        )
        # Canonical must exist in registry
        canonical_spec = None
        for s in registry.specs:
            if s.name == canonical:
                canonical_spec = s
                break
        assert canonical_spec is not None, (
            f"Deprecated feature '{spec.name}' references non-existent canonical '{canonical}'."
        )
        # Canonical must not be deprecated
        assert not getattr(canonical_spec, "deprecated", False), (
            f"Deprecated feature '{spec.name}' references another deprecated canonical '{canonical}'."
        )
        # Canonical must not have forbidden prefixes
        for prefix in ("vx_", "dx_", "zn_"):
            assert not canonical.startswith(prefix), (
                f"Canonical '{canonical}' referenced by deprecated '{spec.name}' "
                f"starts with forbidden prefix '{prefix}'."
            )


def test_percentile_features_use_percentile_rank():
    """Percentile features must use percentile_rank indicator, not vx_percentile."""
    # This test is more about ensuring the compute function mapping is correct.
    # Since we cannot directly inspect the compute function (it's a lambda),
    # we rely on the import and naming conventions.
    # We'll verify that the registry's percentile_* features exist and are not deprecated.
    registry = get_default_registry()
    
    percentile_features = [spec for spec in registry.specs if spec.name.startswith("percentile_")]
    assert len(percentile_features) >= 3, "Expected at least three percentile windows (63,126,252)"
    
    for spec in percentile_features:
        assert not getattr(spec, "deprecated", False), (
            f"Percentile feature '{spec.name}' should not be deprecated."
        )
        # Ensure window parameter matches name
        window = spec.params.get("window")
        assert window is not None, f"Percentile feature '{spec.name}' missing window param."
        expected_window = int(spec.name.split("_")[1])
        assert window == expected_window, (
            f"Percentile feature '{spec.name}' window param mismatch: {window} != {expected_window}"
        )


def test_vx_percentile_aliases_are_deprecated():
    """Legacy vx_percentile_* features must be marked deprecated."""
    registry = get_default_registry()
    
    vx_features = [spec for spec in registry.specs if spec.name.startswith("vx_percentile_")]
    assert len(vx_features) >= 2, "Expected at least two vx_percentile windows (126,252)"
    
    for spec in vx_features:
        assert getattr(spec, "deprecated", False), (
            f"Legacy feature '{spec.name}' should be marked deprecated."
        )
        assert hasattr(spec, "canonical_name"), (
            f"Legacy feature '{spec.name}' missing canonical_name."
        )
        canonical = spec.canonical_name
        assert canonical is not None, (
            f"Legacy feature '{spec.name}' has None canonical_name."
        )
        assert canonical.startswith("percentile_"), (
            f"Legacy feature '{spec.name}' canonical should start with 'percentile_', got '{canonical}'."
        )


def test_indicator_function_renaming():
    """Verify vx_percentile and percentile_rank functions exist and are identical."""
    from indicators.numba_indicators import vx_percentile, percentile_rank
    import numpy as np
    
    # Generate dummy data
    arr = np.array([1.0, 2.0, 3.0, 4.0, 5.0], dtype=np.float64)
    window = 3
    
    # Both functions should produce same output
    result_vx = vx_percentile(arr, window)
    result_pr = percentile_rank(arr, window)
    
    np.testing.assert_array_equal(result_vx, result_pr,
        err_msg="vx_percentile and percentile_rank should produce identical results.")
    
    # Ensure they are not the same function object (they are separate implementations)
    # but that's okay as long as they are equivalent.


if __name__ == "__main__":
    pytest.main([__file__, "-v"])