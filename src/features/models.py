"""
Feature models for causality verification.

Defines FeatureSpec with window metadata and causality contract.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Callable, Any, Literal, TYPE_CHECKING
from pydantic import BaseModel, Field, field_validator, ConfigDict
import numpy as np
from config.registry.timeframes import load_timeframes

if TYPE_CHECKING:
    from contracts.features import FeatureSpec as ContractFeatureSpec


class FeatureSpec(BaseModel):
    """
    Enhanced feature specification with causality verification metadata.
    
    This extends the contract FeatureSpec with additional fields needed for
    causality verification and lookahead detection.
    
    Attributes:
        name: Feature name (e.g., "atr_14")
        timeframe_min: Applicable timeframe in minutes (must be from timeframe registry)
        lookback_bars: Maximum lookback bars required for computation (e.g., ATR(14) needs 14)
        params: Parameter dictionary (e.g., {"window": 14, "method": "log"})
        window: Rolling window size (window=1 for non‑windowed features)
        min_warmup_bars: Minimum bars required for warm‑up (output NaN during warm‑up)
        dtype: Output data type (currently only float64)
        div0_policy: Division‑by‑zero policy (currently only DIV0_RET_NAN)
        family: Feature family (optional, e.g., "ma", "volatility", "momentum")
        compute_func: Optional reference to the compute function (for runtime verification)
        window_honest: Whether the window specification is honest (no lookahead)
        causality_verified: Whether this feature has passed causality verification
        verification_timestamp: When causality verification was performed
        notes: Optional notes about the feature (e.g., usage guidance)
        canonical_name: For aliases, the canonical feature name to use instead
    """
    name: str
    timeframe_min: int
    lookback_bars: int = Field(default=0, ge=0)
    params: Dict[str, str | int | float] = Field(default_factory=dict)
    window: int = Field(default=1, ge=1)
    min_warmup_bars: int = Field(default=0, ge=0)
    dtype: Literal["float64"] = Field(default="float64")
    div0_policy: Literal["DIV0_RET_NAN"] = Field(default="DIV0_RET_NAN")
    family: Optional[str] = Field(default=None)
    compute_func: Optional[Callable[..., np.ndarray]] = Field(default=None, exclude=True)
    window_honest: bool = Field(default=True)
    causality_verified: bool = Field(default=False)
    verification_timestamp: Optional[float] = Field(default=None)
    notes: Optional[str] = Field(default=None)
    canonical_name: Optional[str] = Field(default=None)
    
    @field_validator('lookback_bars')
    @classmethod
    def validate_lookback_bars(cls, v: int) -> int:
        """Ensure lookback_bars is non-negative."""
        if v < 0:
            raise ValueError(f"lookback_bars must be >= 0, got {v}")
        return v
    
    @field_validator('timeframe_min')
    @classmethod
    def validate_timeframe_min(cls, v: int) -> int:
        """Ensure timeframe_min is a supported value from timeframe registry."""
        timeframe_registry = load_timeframes()
        if v not in timeframe_registry.allowed_timeframes:
            raise ValueError(
                f"timeframe_min must be one of {timeframe_registry.allowed_timeframes}, got {v}"
            )
        return v
    
    def mark_causality_verified(self) -> None:
        """Mark this feature as having passed causality verification."""
        import time
        self.causality_verified = True
        self.verification_timestamp = time.time()
    
    def mark_causality_failed(self) -> None:
        """Mark this feature as having failed causality verification."""
        self.causality_verified = False
        self.verification_timestamp = None
    
    def to_contract_spec(self) -> 'ContractFeatureSpec':
        """
        Convert to the contract FeatureSpec (without extra fields).
        
        Returns:
            A minimal FeatureSpec compatible with the contracts module.
        """
        from contracts.features import FeatureSpec as ContractFeatureSpec
        return ContractFeatureSpec(
            name=self.name,
            timeframe_min=self.timeframe_min,
            lookback_bars=self.lookback_bars,
            params=self.params.copy(),
            window=self.window,
            min_warmup_bars=self.min_warmup_bars,
            dtype=self.dtype,
            div0_policy=self.div0_policy,
            family=self.family
        )
    
    @classmethod
    def from_contract_spec(
        cls,
        contract_spec: 'FeatureSpec',
        compute_func: Optional[Callable[..., np.ndarray]] = None
    ) -> 'FeatureSpec':
        """
        Create a causality-aware FeatureSpec from a contract FeatureSpec.
        
        Args:
            contract_spec: The contract FeatureSpec to convert (can be from contracts.features)
            compute_func: Optional compute function reference
        
        Returns:
            A new FeatureSpec with causality fields
        """
        # Handle both FeatureSpec types (from contracts or from this module)
        return cls(
            name=contract_spec.name,
            timeframe_min=contract_spec.timeframe_min,
            lookback_bars=contract_spec.lookback_bars,
            params=contract_spec.params.copy(),
            window=contract_spec.window,
            min_warmup_bars=contract_spec.min_warmup_bars,
            dtype=contract_spec.dtype,
            div0_policy=contract_spec.div0_policy,
            family=contract_spec.family,
            compute_func=compute_func,
            window_honest=True,  # Assume honest until verified
            causality_verified=False,
            verification_timestamp=None,
            notes=None,
            canonical_name=None
        )


class CausalityReport(BaseModel):
    """
    Report of causality verification results.
    
    Attributes:
        feature_name: Name of the feature tested
        passed: Whether the feature passed causality verification
        lookahead_detected: Whether lookahead behavior was detected
        window_honest: Whether the window specification is honest
        impulse_response: The impulse response array (for debugging)
        error_message: Error message if verification failed
        timestamp: When verification was performed
    """
    feature_name: str
    passed: bool
    lookahead_detected: bool = Field(default=False)
    window_honest: bool = Field(default=True)
    impulse_response: Optional[np.ndarray] = Field(default=None, exclude=True)
    error_message: Optional[str] = Field(default=None)
    timestamp: float = Field(default_factory=lambda: time.time())
    
    model_config = ConfigDict(arbitrary_types_allowed=True)


# Import time for default factory
import time