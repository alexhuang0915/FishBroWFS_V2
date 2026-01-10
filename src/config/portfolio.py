"""
Portfolio Configuration Loader

Defines governance rules, admission criteria, and allocation policies.
"""

from pathlib import Path
from typing import List, Dict, Optional, Any
from functools import lru_cache
from enum import Enum

from pydantic import BaseModel, Field, field_validator, ConfigDict





def load_yaml(path: Path) -> dict:
    """Load YAML file with proper error handling."""
    from src.config import load_yaml as _load_yaml
    return _load_yaml(path)


def compute_yaml_sha256(path: Path) -> str:
    """Compute SHA256 hash of YAML file."""
    from src.config import compute_yaml_sha256 as _compute_yaml_sha256
    return _compute_yaml_sha256(path)


class RiskModel(str, Enum):
    """Portfolio risk model."""
    VOL_TARGET = "vol_target"
    RISK_PARITY = "risk_parity"
    EQUAL_WEIGHT = "equal_weight"
    MIN_VARIANCE = "min_variance"


class BucketSlot(BaseModel):
    """Bucket slot allocation."""
    
    bucket_name: str = Field(..., description="Bucket name")
    slots: int = Field(1, ge=0, description="Number of slots")
    weight_limit: Optional[float] = Field(None, ge=0.0, le=1.0, description="Maximum weight per slot")
    
    model_config = ConfigDict(frozen=True)


class CorrelationPolicy(BaseModel):
    """Correlation policy configuration."""
    
    method: str = Field("pearson", description="Correlation method")
    member_hard_limit: float = Field(0.8, ge=0.0, le=1.0, description="Member correlation hard limit")
    portfolio_hard_limit: float = Field(0.7, ge=0.0, le=1.0, description="Portfolio correlation hard limit")
    max_pairwise_correlation: float = Field(0.6, ge=0.0, le=1.0, description="Maximum pairwise correlation")
    rolling_days: int = Field(30, ge=1, description="Rolling window in days")
    min_samples: int = Field(20, ge=1, description="Minimum samples for correlation")
    
    model_config = ConfigDict(frozen=True)


class DrawdownPolicy(BaseModel):
    """Drawdown policy configuration."""
    
    portfolio_dd_cap: float = Field(0.2, ge=0.0, le=1.0, description="Portfolio drawdown cap")
    dd_absolute_cap: float = Field(0.35, ge=0.0, le=1.0, description="Absolute drawdown cap")
    dd_k_multiplier: float = Field(1.0, ge=0.0, description="Drawdown K-factor multiplier")
    
    model_config = ConfigDict(frozen=True)


class RiskBudgetPolicy(BaseModel):
    """Risk budget policy configuration."""
    
    portfolio_risk_budget_max: float = Field(1.0, ge=0.0, description="Maximum portfolio risk budget")
    portfolio_vol_target: float = Field(0.1, ge=0.0, description="Portfolio volatility target")
    vol_floor: float = Field(0.02, ge=0.0, description="Volatility floor")
    w_max: float = Field(0.35, ge=0.0, le=1.0, description="Maximum weight per strategy")
    w_min: float = Field(0.0, ge=0.0, le=1.0, description="Minimum weight per strategy")
    
    model_config = ConfigDict(frozen=True)


class BreakerPolicy(BaseModel):
    """Circuit breaker policy configuration."""
    
    exposure_reduction_on_breaker: float = Field(
        0.5,
        ge=0.0,
        le=1.0,
        description="Exposure reduction factor when breaker triggers"
    )
    
    model_config = ConfigDict(frozen=True)


class PortfolioConfig(BaseModel):
    """Portfolio configuration with governance rules."""
    
    version: str = Field(..., description="Portfolio schema version")
    
    # Risk model
    risk_model: RiskModel = Field(..., description="Portfolio risk model")
    allowed_risk_models: List[RiskModel] = Field(
        default_factory=list,
        description="Allowed risk models"
    )
    
    # Bucket allocation
    bucket_slots: Dict[str, BucketSlot] = Field(
        default_factory=dict,
        description="Bucket slot allocations"
    )
    
    # Policies
    correlation_policy: CorrelationPolicy = Field(
        default=CorrelationPolicy(
            method="pearson",
            member_hard_limit=0.8,
            portfolio_hard_limit=0.7,
            max_pairwise_correlation=0.6,
            rolling_days=30,
            min_samples=20
        ),
        description="Correlation policy"
    )
    drawdown_policy: DrawdownPolicy = Field(
        default=DrawdownPolicy(
            portfolio_dd_cap=0.2,
            dd_absolute_cap=0.35,
            dd_k_multiplier=1.0
        ),
        description="Drawdown policy"
    )
    risk_budget_policy: RiskBudgetPolicy = Field(
        default=RiskBudgetPolicy(
            portfolio_risk_budget_max=1.0,
            portfolio_vol_target=0.1,
            vol_floor=0.02,
            w_max=0.35,
            w_min=0.0
        ),
        description="Risk budget policy"
    )
    breaker_policy: BreakerPolicy = Field(
        default=BreakerPolicy(
            exposure_reduction_on_breaker=0.5
        ),
        description="Circuit breaker policy"
    )
    
    # Optional fields
    notes: Optional[str] = Field(None, description="Additional notes")
    
    # SHA256 hash of original YAML
    sha256: Optional[str] = Field(None, description="SHA256 hash of YAML file")
    
    model_config = ConfigDict(frozen=True)
    
    @field_validator('allowed_risk_models')
    @classmethod
    def validate_allowed_risk_models(cls, v: List[RiskModel], info) -> List[RiskModel]:
        """Validate allowed risk models includes the selected risk model."""
        risk_model = info.data.get('risk_model')
        if risk_model and risk_model not in v:
            v.append(risk_model)
        return v
    
    def get_total_slots(self) -> int:
        """Get total number of portfolio slots."""
        return sum(slot.slots for slot in self.bucket_slots.values())
    
    def get_bucket_names(self) -> List[str]:
        """Get list of bucket names."""
        return list(self.bucket_slots.keys())
    
    def validate_strategy_admission(
        self,
        strategy_metrics: Dict[str, Any],
        portfolio_metrics: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Validate strategy admission against portfolio policies.
        
        Args:
            strategy_metrics: Strategy performance metrics
            portfolio_metrics: Current portfolio metrics
            
        Returns:
            Dictionary with admission results and reasons
        """
        result = {
            "admitted": True,
            "reasons": [],
            "warnings": [],
            "constraints": {}
        }
        
        # Check correlation limits
        if "correlation" in strategy_metrics:
            corr = strategy_metrics["correlation"]
            if abs(corr) > self.correlation_policy.member_hard_limit:
                result["admitted"] = False
                result["reasons"].append(
                    f"Correlation {corr:.3f} exceeds member hard limit "
                    f"{self.correlation_policy.member_hard_limit}"
                )
            elif abs(corr) > self.correlation_policy.max_pairwise_correlation:
                result["warnings"].append(
                    f"Correlation {corr:.3f} exceeds max pairwise limit "
                    f"{self.correlation_policy.max_pairwise_correlation}"
                )
        
        # Check drawdown limits
        if "max_drawdown" in strategy_metrics:
            mdd = strategy_metrics["max_drawdown"]
            if mdd > self.drawdown_policy.dd_absolute_cap:
                result["admitted"] = False
                result["reasons"].append(
                    f"Max drawdown {mdd:.3f} exceeds absolute cap "
                    f"{self.drawdown_policy.dd_absolute_cap}"
                )
        
        # Check weight limits
        if "proposed_weight" in strategy_metrics:
            weight = strategy_metrics["proposed_weight"]
            if weight > self.risk_budget_policy.w_max:
                result["constraints"]["weight"] = self.risk_budget_policy.w_max
                result["warnings"].append(
                    f"Proposed weight {weight:.3f} exceeds maximum {self.risk_budget_policy.w_max}"
                )
            elif weight < self.risk_budget_policy.w_min:
                result["constraints"]["weight"] = self.risk_budget_policy.w_min
                result["warnings"].append(
                    f"Proposed weight {weight:.3f} below minimum {self.risk_budget_policy.w_min}"
                )
        
        return result


@lru_cache(maxsize=2)
def load_portfolio_config(filename: str = "governance.yaml", path: Optional[Path] = None) -> PortfolioConfig:
    """
    Load portfolio configuration from YAML file.
    
    Args:
        filename: Portfolio configuration filename (e.g., "governance.yaml")
        path: Optional path to portfolio YAML file.
              Defaults to configs/portfolio/{filename}
    
    Returns:
        PortfolioConfig instance with SHA256 hash
        
    Raises:
        ConfigError: If loading or validation fails
    """
    if path is None:
        from src.config import get_portfolio_path
        path = get_portfolio_path(filename)
    
    # Compute SHA256 hash of original YAML
    sha256_hash = compute_yaml_sha256(path)
    
    data = load_yaml(path)
    
    try:
        portfolio = PortfolioConfig(**data, sha256=sha256_hash)
        return portfolio
    except Exception as e:
        from src.config import ConfigError
        raise ConfigError(f"Failed to validate portfolio config at {path}: {e}")

