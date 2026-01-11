"""
Test that GovernanceParams loads thresholds from YAML overrides correctly.
"""
import yaml
import tempfile
from pathlib import Path

from src.portfolio.governance.params import load_governance_params


def test_load_governance_params_with_overrides(tmp_path):
    """Verify that custom YAML overrides are respected."""
    # Create a temporary YAML file with custom values
    custom_params = {
        "version": "2.0",
        "risk_model": "vol_target",
        "allowed_risk_models": ["vol_target"],
        "bucket_slots": {
            "Trend": {"bucket_name": "Trend", "slots": 3},
            "MeanRev": {"bucket_name": "MeanRev", "slots": 1}
        },
        "correlation_policy": {
            "method": "pearson",
            "member_hard_limit": 0.75,
            "portfolio_hard_limit": 0.65,
            "max_pairwise_correlation": 0.45,
            "rolling_days": 45,
            "min_samples": 25
        },
        "drawdown_policy": {
            "portfolio_dd_cap": 0.15,
            "dd_absolute_cap": 0.3,
            "dd_k_multiplier": 1.2
        },
        "risk_budget_policy": {
            "portfolio_risk_budget_max": 0.8,
            "portfolio_vol_target": 0.12,
            "vol_floor": 0.01,
            "w_max": 0.4,
            "w_min": 0.05
        },
        "breaker_policy": {
            "exposure_reduction_on_breaker": 0.6
        }
    }
    param_file = tmp_path / "custom_params.yaml"
    param_file.write_text(yaml.dump(custom_params, default_flow_style=False))

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
        "version": "2.0",
        "risk_model": "vol_target",
        "allowed_risk_models": ["vol_target"],
        "bucket_slots": {
            "Trend": {"bucket_name": "Trend", "slots": 2}
        },
        "correlation_policy": {
            "method": "pearson",
            "member_hard_limit": 0.8,
            "portfolio_hard_limit": 0.7,
            "max_pairwise_correlation": 1.5,  # >1 (invalid)
            "rolling_days": 30,
            "min_samples": 20
        },
        "drawdown_policy": {
            "portfolio_dd_cap": 0.2,
            "dd_absolute_cap": 0.35,
            "dd_k_multiplier": 1.0
        },
        "risk_budget_policy": {
            "portfolio_risk_budget_max": -0.1,  # negative (invalid)
            "portfolio_vol_target": 0.1,
            "vol_floor": 0.02,
            "w_max": 0.35,
            "w_min": 0.0
        },
        "breaker_policy": {
            "exposure_reduction_on_breaker": 0.5
        }
    }
    param_file = Path(tempfile.mktemp(suffix=".yaml"))
    param_file.write_text(yaml.dump(invalid_params, default_flow_style=False))
    try:
        # Should raise ConfigError (wraps Pydantic validation errors)
        # Import the same ConfigError that will be raised (config.ConfigError)
        import config
        try:
            load_governance_params(str(param_file))
            assert False, "Expected validation error"
        except config.ConfigError as e:
            # Ensure the error mentions the offending field
            error_str = str(e)
            # The error string includes field names with prefixes; accept any mention
            if "max_pairwise_correlation" not in error_str and "portfolio_risk_budget_max" not in error_str:
                # If neither substring appears, raise assertion error with debug info
                raise AssertionError(
                    f"Expected error to mention 'max_pairwise_correlation' or 'portfolio_risk_budget_max', "
                    f"but got: {error_str}"
                )
    finally:
        param_file.unlink(missing_ok=True)