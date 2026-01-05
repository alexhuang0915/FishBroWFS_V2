"""
Test that GovernanceParams loads thresholds from JSON overrides correctly.
"""
import json
import tempfile
from pathlib import Path

from src.portfolio.governance.params import load_governance_params


def test_load_governance_params_with_overrides(tmp_path):
    """Verify that custom JSON overrides are respected."""
    # Create a temporary JSON file with custom values
    custom_params = {
        "max_pairwise_correlation": 0.45,
        "portfolio_risk_budget_max": 0.8,
        "corr_member_hard_limit": 0.75,
        "corr_portfolio_hard_limit": 0.65,
        "corr_rolling_days": 45,
        "corr_min_samples": 25,
        "bucket_slots": {"Trend": 3, "MeanRev": 1},
        "allowed_risk_models": ["vol_target"],
        "risk_model": "vol_target",
        "portfolio_vol_target": 0.12,
        "vol_floor": 0.01,
        "w_max": 0.4,
        "w_min": 0.05,
        "dd_absolute_cap": 0.3,
        "dd_k_multiplier": 1.2,
        "portfolio_dd_cap": 0.15,
        "exposure_reduction_on_breaker": 0.6,
    }
    param_file = tmp_path / "custom_params.json"
    param_file.write_text(json.dumps(custom_params, indent=2))

    # Load via the loader
    params = load_governance_params(str(param_file))

    # Assert overridden values
    assert params.max_pairwise_correlation == 0.45
    assert params.portfolio_risk_budget_max == 0.8
    assert params.corr_member_hard_limit == 0.75
    assert params.corr_portfolio_hard_limit == 0.65
    assert params.corr_rolling_days == 45
    assert params.corr_min_samples == 25
    assert params.bucket_slots == {"Trend": 3, "MeanRev": 1}
    assert params.allowed_risk_models == ["vol_target"]
    assert params.risk_model == "vol_target"
    assert params.portfolio_vol_target == 0.12
    assert params.vol_floor == 0.01
    assert params.w_max == 0.4
    assert params.w_min == 0.05
    assert params.dd_absolute_cap == 0.3
    assert params.dd_k_multiplier == 1.2
    assert params.portfolio_dd_cap == 0.15
    assert params.exposure_reduction_on_breaker == 0.6


def test_default_values_are_present():
    """Ensure the new fields have default values when loading default config."""
    params = load_governance_params()
    # Defaults from GovernanceParams class
    assert params.max_pairwise_correlation == 0.60
    assert params.portfolio_risk_budget_max == 1.00
    # Ensure other defaults are as expected
    assert params.corr_member_hard_limit == 0.8
    assert params.corr_portfolio_hard_limit == 0.7


def test_validation_rejects_invalid_values():
    """Check that field validators reject out‑of‑range values."""
    invalid_params = {
        "max_pairwise_correlation": 1.5,  # >1
        "portfolio_risk_budget_max": -0.1,
        "corr_member_hard_limit": 0.8,
        "corr_portfolio_hard_limit": 0.7,
        "bucket_slots": {"Trend": 2},
        "allowed_risk_models": ["vol_target"],
        "risk_model": "vol_target",
        "portfolio_vol_target": 0.1,
        "vol_floor": 0.02,
        "w_max": 0.35,
        "w_min": 0.0,
        "dd_absolute_cap": 0.35,
        "dd_k_multiplier": 1.0,
        "portfolio_dd_cap": 0.2,
        "exposure_reduction_on_breaker": 0.5,
    }
    param_file = Path(tempfile.mktemp(suffix=".json"))
    param_file.write_text(json.dumps(invalid_params))
    try:
        # Should raise ValidationError (Pydantic)
        import pydantic
        try:
            load_governance_params(str(param_file))
            assert False, "Expected validation error"
        except pydantic.ValidationError as e:
            # Ensure the error mentions the offending field
            error_str = str(e)
            assert "max_pairwise_correlation" in error_str or "portfolio_risk_budget_max" in error_str
    finally:
        param_file.unlink(missing_ok=True)