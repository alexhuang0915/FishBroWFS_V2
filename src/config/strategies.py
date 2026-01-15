"""
Strategy Configuration Loader

Defines strategy parameters, feature flags, and determinism settings.
Implements seed precedence: job.seed > strategy.default_seed
"""

from pathlib import Path
from typing import List, Dict, Optional, Any, Union
from functools import lru_cache
from enum import Enum

from pydantic import BaseModel, Field, field_validator, ConfigDict


def get_strategy_path(strategy_id: str) -> Path:
    """Get path to strategy configuration file."""
    from . import get_config_root
    return get_config_root() / "strategies" / f"{strategy_id}.yaml"


def load_yaml(path: Path) -> dict:
    """Load YAML file with proper error handling."""
    from . import load_yaml as _load_yaml
    return _load_yaml(path)


def compute_yaml_sha256(path: Path) -> str:
    """Compute SHA256 hash of YAML file."""
    from . import compute_yaml_sha256 as _compute_yaml_sha256
    return _compute_yaml_sha256(path)


class ParameterType(str, Enum):
    """Parameter type for validation."""
    INT = "int"
    FLOAT = "float"
    BOOL = "bool"
    STRING = "string"
    CHOICE = "choice"


class ParameterSchema(BaseModel):
    """Parameter schema definition."""
    
    type: ParameterType = Field(..., description="Parameter type")
    default: Any = Field(..., description="Default value")
    
    # Type-specific constraints
    min: Optional[Union[int, float]] = Field(None, description="Minimum value")
    max: Optional[Union[int, float]] = Field(None, description="Maximum value")
    choices: Optional[List[Any]] = Field(None, description="Allowed choices")
    
    # Optional metadata
    description: Optional[str] = Field(None, description="Parameter description")
    step: Optional[Union[int, float]] = Field(None, description="Step size for grid search")
    
    @field_validator('default')
    @classmethod
    def validate_default_type(cls, v: Any, info) -> Any:
        """Validate default value matches parameter type."""
        param_type = info.data.get('type')
        
        if param_type == ParameterType.INT:
            if not isinstance(v, int):
                raise ValueError(f"Default value must be int for type {param_type}")
        elif param_type == ParameterType.FLOAT:
            if not isinstance(v, (int, float)):
                raise ValueError(f"Default value must be float for type {param_type}")
        elif param_type == ParameterType.BOOL:
            if not isinstance(v, bool):
                raise ValueError(f"Default value must be bool for type {param_type}")
        elif param_type == ParameterType.STRING:
            if not isinstance(v, str):
                raise ValueError(f"Default value must be str for type {param_type}")
        elif param_type == ParameterType.CHOICE:
            choices = info.data.get('choices', [])
            if v not in choices:
                raise ValueError(f"Default value {v} not in choices: {choices}")
        
        return v
    
    @field_validator('min', 'max')
    @classmethod
    def validate_min_max_for_numeric(cls, v: Optional[Union[int, float]], info) -> Optional[Union[int, float]]:
        """Validate min/max only for numeric types."""
        if v is None:
            return v
        
        param_type = info.data.get('type')
        if param_type not in [ParameterType.INT, ParameterType.FLOAT]:
            raise ValueError(f"min/max only allowed for INT or FLOAT types, got {param_type}")
        
        return v
    
    @field_validator('choices')
    @classmethod
    def validate_choices_for_choice_type(cls, v: Optional[List[Any]], info) -> Optional[List[Any]]:
        """Validate choices only for CHOICE type."""
        if v is None:
            return v
        
        param_type = info.data.get('type')
        if param_type != ParameterType.CHOICE:
            raise ValueError(f"choices only allowed for CHOICE type, got {param_type}")
        
        if not v:
            raise ValueError("choices list cannot be empty")
        
        return v
    
    model_config = ConfigDict(frozen=True, extra='forbid')


class FeatureSpec(BaseModel):
    """Feature specification for strategy."""
    
    name: str = Field(..., description="Feature name")
    timeframe: int = Field(..., description="Feature timeframe in minutes")
    
    # Optional fields
    required: bool = Field(True, description="Whether feature is required")
    params: Optional[Dict[str, Any]] = Field(None, description="Feature parameters")
    
    model_config = ConfigDict(frozen=True, extra='forbid')


class DeterminismConfig(BaseModel):
    """Determinism configuration with seed precedence."""
    
    default_seed: int = Field(
        42,
        description="Default random seed (used when job.seed is not provided)"
    )
    
    model_config = ConfigDict(frozen=True, extra='forbid')


class StrategyConfig(BaseModel):
    """Strategy configuration with determinism and parameters."""
    
    version: str = Field(..., description="Strategy schema version")
    strategy_id: str = Field(..., description="Strategy identifier")
    
    # Determinism configuration
    determinism: DeterminismConfig = Field(default_factory=lambda: DeterminismConfig(),  # type: ignore
        description="Determinism configuration"
    )
    
    # Parameters schema
    parameters: Dict[str, ParameterSchema] = Field(
        default_factory=dict,
        description="Parameter definitions"
    )
    
    # Features - REQUIRED for all strategies (STRICT mode)
    features: List[FeatureSpec] = Field(
        ...,
        description="Required features for strategy (STRICT: must be defined)"
    )
    
    # Optional fields
    dataset_id: Optional[str] = Field(None, description="Default dataset ID")
    timeframe: Optional[int] = Field(None, description="Default timeframe")
    notes: Optional[str] = Field(None, description="Additional notes")
    
    # SHA256 hash of original YAML
    sha256: Optional[str] = Field(None, description="SHA256 hash of YAML file")
    
    model_config = ConfigDict(frozen=True, extra='forbid')
    
    @field_validator('features')
    @classmethod
    def validate_features_not_empty(cls, v: List[FeatureSpec]) -> List[FeatureSpec]:
        """Validate that features list is not empty (STRICT mode)."""
        if not v:
            raise ValueError("Strategy must define at least one feature (STRICT mode)")
        return v
    
    def get_effective_seed(self, job_seed: Optional[int] = None) -> int:
        """
        Get effective seed based on seed precedence.
        
        Seed precedence: job.seed > strategy.default_seed
        
        Args:
            job_seed: Optional seed from job configuration
            
        Returns:
            Effective seed to use
        """
        if job_seed is not None:
            return job_seed
        return self.determinism.default_seed
    
    def validate_parameters(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate parameter values against schema.
        
        Args:
            params: Parameter values to validate
            
        Returns:
            Validated parameters with defaults filled in
            
        Raises:
            ValueError: If validation fails
        """
        validated = {}
        
        for param_name, param_schema in self.parameters.items():
            if param_name in params:
                value = params[param_name]
                
                # Type validation
                if param_schema.type == ParameterType.INT:
                    if not isinstance(value, int):
                        raise ValueError(f"Parameter {param_name} must be int, got {type(value)}")
                    if param_schema.min is not None and value < param_schema.min:
                        raise ValueError(f"Parameter {param_name} must be >= {param_schema.min}, got {value}")
                    if param_schema.max is not None and value > param_schema.max:
                        raise ValueError(f"Parameter {param_name} must be <= {param_schema.max}, got {value}")
                
                elif param_schema.type == ParameterType.FLOAT:
                    if not isinstance(value, (int, float)):
                        raise ValueError(f"Parameter {param_name} must be float, got {type(value)}")
                    value = float(value)
                    if param_schema.min is not None and value < param_schema.min:
                        raise ValueError(f"Parameter {param_name} must be >= {param_schema.min}, got {value}")
                    if param_schema.max is not None and value > param_schema.max:
                        raise ValueError(f"Parameter {param_name} must be <= {param_schema.max}, got {value}")
                
                elif param_schema.type == ParameterType.BOOL:
                    if not isinstance(value, bool):
                        raise ValueError(f"Parameter {param_name} must be bool, got {type(value)}")
                
                elif param_schema.type == ParameterType.STRING:
                    if not isinstance(value, str):
                        raise ValueError(f"Parameter {param_name} must be str, got {type(value)}")
                
                elif param_schema.type == ParameterType.CHOICE:
                    if param_schema.choices and value not in param_schema.choices:
                        raise ValueError(f"Parameter {param_name} must be one of {param_schema.choices}, got {value}")
                
                validated[param_name] = value
            else:
                # Use default value
                validated[param_name] = param_schema.default
        
        return validated
    
    def get_parameter_grid(self) -> List[Dict[str, Any]]:
        """
        Generate parameter grid for grid search.
        
        Returns:
            List of parameter combinations
        """
        # Simple implementation: single combination with defaults
        # In a real implementation, this would generate all combinations
        # based on min/max/step values
        grid = []
        
        defaults = {}
        for param_name, param_schema in self.parameters.items():
            defaults[param_name] = param_schema.default
        
        grid.append(defaults)
        return grid


@lru_cache(maxsize=4)
def load_strategy(strategy_id: str, path: Optional[Path] = None) -> StrategyConfig:
    """
    Load strategy configuration from YAML file.
    
    Args:
        strategy_id: Strategy ID (e.g., "s1_v1")
        path: Optional path to strategy YAML file.
              Defaults to configs/strategies/{strategy_id}.yaml
    
    Returns:
        StrategyConfig instance with SHA256 hash
        
    Raises:
        ConfigError: If loading or validation fails
    """
    if path is None:
        path = get_strategy_path(strategy_id)
    
    # Compute SHA256 hash of original YAML
    sha256_hash = compute_yaml_sha256(path)
    
    data = load_yaml(path)
    
    try:
        strategy = StrategyConfig(**data, sha256=sha256_hash)
        return strategy
    except Exception as e:
        from . import ConfigError
        raise ConfigError(f"Failed to validate strategy {strategy_id} at {path}: {e}")


def get_effective_seed_for_job(
    strategy_id: str, 
    job_seed: Optional[int] = None,
    reject_env_override: bool = True
) -> int:
    """
    Get effective seed for a job with proper precedence.
    
    Seed precedence: job.seed > strategy.default_seed
    Environment variable overrides are explicitly rejected.
    
    Args:
        strategy_id: Strategy ID
        job_seed: Optional seed from job configuration
        reject_env_override: If True, check for and reject env var overrides
        
    Returns:
        Effective seed to use
        
    Raises:
        ValueError: If environment variable override is detected and rejected
    """
    if reject_env_override:
        # Check for environment variable overrides
        import os
        env_seed = os.getenv("FISHBRO_PERF_PARAM_SUBSAMPLE_SEED")
        if env_seed is not None:
            raise ValueError(
                "Environment variable FISHBRO_PERF_PARAM_SUBSAMPLE_SEED detected. "
                "Seed precedence: job.seed > strategy.default_seed. "
                "Environment variable overrides are not allowed."
            )
    
    # Load strategy to get default seed
    strategy = load_strategy(strategy_id)
    
    # Apply seed precedence
    return strategy.get_effective_seed(job_seed)