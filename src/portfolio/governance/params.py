"""
Load governance parameters from YAML file (single source of truth).
Migrated from JSON to YAML as part of Config Constitution v1.
JSON support has been removed - all configuration must be in YAML format.
"""
import os
from pathlib import Path
from typing import Optional

from src.config.portfolio import load_portfolio_config, PortfolioConfig
from ..models.governance_models import GovernanceParams


# Default path relative to repo root (YAML)
_DEFAULT_PATH = Path("configs/portfolio/governance.yaml")


def load_governance_params(path: Optional[str] = None) -> GovernanceParams:
    """
    Load governance parameters from a YAML file.

    Search order:
      1. Explicit `path` argument (if provided)
      2. Environment variable FISHBRO_PORTFOLIO_PARAMS
      3. Default path `configs/portfolio/governance.yaml`

    Raises FileNotFoundError if the file does not exist.
    Raises ValidationError if the file does not conform to GovernanceParams.
    
    Note: Only YAML format is supported. JSON support has been removed.
    """
    # Determine which file to load
    file_path: Optional[Path] = None
    if path is not None:
        file_path = Path(path)
    else:
        env_path = os.getenv("FISHBRO_PORTFOLIO_PARAMS")
        if env_path:
            file_path = Path(env_path)
        else:
            file_path = _DEFAULT_PATH

    # Resolve relative to repo root (current working directory)
    file_path = file_path.resolve()
    if not file_path.exists():
        raise FileNotFoundError(
            f"Governance parameters file not found: {file_path}\n"
            f"Please create it or set FISHBRO_PORTFOLIO_PARAMS environment variable."
        )

    # Only YAML format is supported
    if file_path.suffix.lower() not in ['.yaml', '.yml']:
        raise ValueError(
            f"Only YAML files are supported for governance parameters. "
            f"Received: {file_path.suffix}. "
            f"Please migrate JSON files to YAML format."
        )

    # Load from YAML using portfolio config
    portfolio_config = load_portfolio_config(path=file_path)
    return _convert_portfolio_config_to_governance_params(portfolio_config)


def _convert_portfolio_config_to_governance_params(
    portfolio_config: PortfolioConfig
) -> GovernanceParams:
    """
    Convert new PortfolioConfig to legacy GovernanceParams for backward compatibility.
    """
    from ..models.governance_models import GovernanceParams
    
    # Extract values from portfolio config
    return GovernanceParams(
        risk_model=portfolio_config.risk_model.value,
        allowed_risk_models=[rm.value for rm in portfolio_config.allowed_risk_models],
        bucket_slots={name: slot.slots for name, slot in portfolio_config.bucket_slots.items()},
        corr_member_hard_limit=portfolio_config.correlation_policy.member_hard_limit,
        corr_portfolio_hard_limit=portfolio_config.correlation_policy.portfolio_hard_limit,
        max_pairwise_correlation=portfolio_config.correlation_policy.max_pairwise_correlation,
        corr_rolling_days=portfolio_config.correlation_policy.rolling_days,
        corr_min_samples=portfolio_config.correlation_policy.min_samples,
        portfolio_dd_cap=portfolio_config.drawdown_policy.portfolio_dd_cap,
        dd_absolute_cap=portfolio_config.drawdown_policy.dd_absolute_cap,
        dd_k_multiplier=portfolio_config.drawdown_policy.dd_k_multiplier,
        portfolio_risk_budget_max=portfolio_config.risk_budget_policy.portfolio_risk_budget_max,
        portfolio_vol_target=portfolio_config.risk_budget_policy.portfolio_vol_target,
        vol_floor=portfolio_config.risk_budget_policy.vol_floor,
        w_max=portfolio_config.risk_budget_policy.w_max,
        w_min=portfolio_config.risk_budget_policy.w_min,
        exposure_reduction_on_breaker=portfolio_config.breaker_policy.exposure_reduction_on_breaker,
    )


def create_default_params_file(target_path: Optional[Path] = None) -> Path:
    """
    Write a default governance parameters YAML file.

    Useful for bootstrapping a new deployment.
    Returns the path written.
    """
    if target_path is None:
        target_path = _DEFAULT_PATH

    target_path.parent.mkdir(parents=True, exist_ok=True)

    # Create default YAML directly
    import yaml
    
    default_yaml = {
        "version": "2.0",
        "risk_model": "vol_target",
        "allowed_risk_models": ["vol_target", "risk_parity"],
        "bucket_slots": {
            "Carry/Income": {"bucket_name": "Carry/Income", "slots": 1},
            "LongVol": {"bucket_name": "LongVol", "slots": 1},
            "MeanRev": {"bucket_name": "MeanRev", "slots": 2},
            "Other": {"bucket_name": "Other", "slots": 1},
            "Trend": {"bucket_name": "Trend", "slots": 2}
        },
        "correlation_policy": {
            "method": "pearson",
            "member_hard_limit": 0.8,
            "portfolio_hard_limit": 0.7,
            "max_pairwise_correlation": 0.6,
            "rolling_days": 30,
            "min_samples": 20
        },
        "drawdown_policy": {
            "portfolio_dd_cap": 0.2,
            "dd_absolute_cap": 0.35,
            "dd_k_multiplier": 1.0
        },
        "risk_budget_policy": {
            "portfolio_risk_budget_max": 1.0,
            "portfolio_vol_target": 0.1,
            "vol_floor": 0.02,
            "w_max": 0.35,
            "w_min": 0.0
        },
        "breaker_policy": {
            "exposure_reduction_on_breaker": 0.5
        },
        "notes": "Default governance parameters created automatically."
    }
    
    # Write YAML file
    with open(target_path, 'w', encoding='utf-8') as f:
        yaml.dump(default_yaml, f, default_flow_style=False, sort_keys=False)
    
    return target_path