"""
Feature models for causality verification.

Defines FeatureSpec with window metadata and causality contract.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Callable, Any
from pydantic import BaseModel, Field, field_validator, ConfigDict
import numpy as np


class FeatureSpec(BaseModel):
    """
    Enhanced feature specification with causality verification metadata.
    
    This extends the contract FeatureSpec with additional fields needed for
    causality verification and lookahead detection.
    
    Attributes:
        name: Feature name (e.g., "atr_14")
        timeframe_min: Applicable timeframe in minutes (15, 30, 60, 120, 240)
        lookback_bars: Maximum lookback bars required for computation (e.g., ATR(14) needs 14)
        params: Parameter dictionary (e.g., {"window": 14, "method": "log"})
        compute_func: Optional reference to the compute function (for runtime verification)
        window_honest: Whether the window specification is honest (no lookahead)
        causality_verified: Whether this feature has passed causality verification
        verification_timestamp: When causality verification was performed
    """
    name: str
    timeframe_min: int
    lookback_bars: int = Field(default=0, ge=0)
    params: Dict[str, str | int | float] = Field(default_factory=dict)
    compute_func: Optional[Callable[..., np.ndarray]] = Field(default=None, exclude=True)
    window_honest: bool = Field(default=True)
    causality_verified: bool = Field(default=False)
    verification_timestamp: Optional[float] = Field(default=None)
    
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
        """Ensure timeframe_min is a supported value."""
        supported = [15, 30, 60, 120, 240]
        if v not in supported:
            raise ValueError(f"timeframe_min must be one of {supported}, got {v}")
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
    
    def to_contract_spec(self) -> 'FeatureSpec':
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
            params=self.params.copy()
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
            contract_spec: The contract FeatureSpec to convert
            compute_func: Optional compute function reference
            
        Returns:
            A new FeatureSpec with causality fields
        """
        return cls(
            name=contract_spec.name,
            timeframe_min=contract_spec.timeframe_min,
            lookback_bars=contract_spec.lookback_bars,
            params=contract_spec.params.copy(),
            compute_func=compute_func,
            window_honest=True,  # Assume honest until verified
            causality_verified=False,
            verification_timestamp=None
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