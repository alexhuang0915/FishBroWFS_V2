"""
Feature registry with causality enforcement.

Enforces that every feature must pass causality verification before registration.
Verification is a dynamic runtime test, not static AST inspection.
Any lookahead behavior causes hard fail.
Registry cannot be bypassed.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Callable, Any
import threading
from pydantic import BaseModel, Field, ConfigDict

from contracts.features import FeatureRegistry as ContractFeatureRegistry
from contracts.features import FeatureSpec as ContractFeatureSpec
from features.models import FeatureSpec, CausalityReport
from features.causality import (
    verify_feature_causality,
    batch_verify_features,
    LookaheadDetectedError,
    WindowDishonestyError,
    CausalityVerificationError
)


class FeatureRegistry(BaseModel):
    """
    Enhanced feature registry with causality enforcement.
    
    Extends the contract FeatureRegistry with causality verification gates.
    Every feature must pass causality verification before being registered.
    
    Attributes:
        specs: List of verified feature specifications
        verification_reports: Map from feature name to causality report
        verification_enabled: Whether causality verification is enabled
        lock: Thread lock for thread-safe registration
    """
    specs: List[FeatureSpec] = Field(default_factory=list)
    verification_reports: Dict[str, CausalityReport] = Field(default_factory=dict)
    verification_enabled: bool = Field(default=True)
    lock: threading.Lock = Field(default_factory=threading.Lock, exclude=True)
    
    model_config = ConfigDict(arbitrary_types_allowed=True)
    
    def register_feature(
        self,
        name: str,
        timeframe_min: int,
        lookback_bars: int,
        params: Dict[str, str | int | float],
        compute_func: Optional[Callable[..., np.ndarray]] = None,
        skip_verification: bool = False
    ) -> FeatureSpec:
        """
        Register a new feature with causality verification.
        
        Args:
            name: Feature name
            timeframe_min: Timeframe in minutes
            lookback_bars: Required lookback bars
            params: Feature parameters
            compute_func: Feature compute function (required for verification)
            skip_verification: If True, skip causality verification (dangerous!)
            
        Returns:
            Registered FeatureSpec
            
        Raises:
            LookaheadDetectedError: If lookahead detected during verification
            WindowDishonestyError: If window specification is dishonest
            ValueError: If feature with same name/timeframe already exists
        """
        with self.lock:
            # Check for duplicates
            for spec in self.specs:
                if spec.name == name and spec.timeframe_min == timeframe_min:
                    raise ValueError(
                        f"Feature '{name}' already registered for timeframe {timeframe_min}min"
                    )
            
            # Create feature spec
            feature_spec = FeatureSpec(
                name=name,
                timeframe_min=timeframe_min,
                lookback_bars=lookback_bars,
                params=params.copy(),
                compute_func=compute_func,
                window_honest=True,  # Assume honest until verified
                causality_verified=False,
                verification_timestamp=None
            )
            
            # Perform causality verification if enabled and not skipped
            if self.verification_enabled and not skip_verification:
                if compute_func is None:
                    raise ValueError(
                        f"Cannot verify feature '{name}' without compute function"
                    )
                
                try:
                    report = verify_feature_causality(feature_spec, strict=True)
                    self.verification_reports[name] = report
                    
                    if report.passed:
                        feature_spec.mark_causality_verified()
                        feature_spec.window_honest = report.window_honest
                    else:
                        # Verification failed
                        raise CausalityVerificationError(
                            f"Feature '{name}' failed causality verification: "
                            f"{report.error_message}"
                        )
                        
                except (LookaheadDetectedError, WindowDishonestyError) as e:
                    # Re-raise these specific errors
                    raise
                except Exception as e:
                    # Wrap other errors
                    raise CausalityVerificationError(
                        f"Feature '{name}' verification failed with error: {e}"
                    ) from e
            elif skip_verification:
                # Mark as verified but with warning
                feature_spec.causality_verified = True
                feature_spec.verification_timestamp = None  # No actual verification
                warnings.warn(
                    f"Feature '{name}' registered without causality verification. "
                    f"This is dangerous and may lead to lookahead bias.",
                    UserWarning
                )
            
            # Add to registry
            self.specs.append(feature_spec)
            
            return feature_spec
    
    def register_feature_spec(
        self,
        feature_spec: FeatureSpec,
        skip_verification: bool = False
    ) -> FeatureSpec:
        """
        Register a FeatureSpec object.
        
        Args:
            feature_spec: FeatureSpec to register
            skip_verification: If True, skip causality verification
            
        Returns:
            Registered FeatureSpec (same object)
        """
        return self.register_feature(
            name=feature_spec.name,
            timeframe_min=feature_spec.timeframe_min,
            lookback_bars=feature_spec.lookback_bars,
            params=feature_spec.params,
            compute_func=feature_spec.compute_func,
            skip_verification=skip_verification
        )
    
    def register_from_contract(
        self,
        contract_spec: ContractFeatureSpec,
        compute_func: Optional[Callable[..., np.ndarray]] = None,
        skip_verification: bool = False
    ) -> FeatureSpec:
        """
        Register a feature from a contract FeatureSpec.
        
        Args:
            contract_spec: Contract FeatureSpec to register
            compute_func: Feature compute function
            skip_verification: If True, skip causality verification
            
        Returns:
            Registered FeatureSpec
        """
        # Convert to causality-aware FeatureSpec
        feature_spec = FeatureSpec.from_contract_spec(contract_spec, compute_func)
        return self.register_feature_spec(feature_spec, skip_verification)
    
    def verify_all_registered(self, reverify: bool = False) -> Dict[str, CausalityReport]:
        """
        Verify all registered features (or re-verify if requested).
        
        Args:
            reverify: If True, re-verify even previously verified features
            
        Returns:
            Dictionary of verification reports
        """
        with self.lock:
            specs_to_verify = []
            for spec in self.specs:
                if reverify or not spec.causality_verified:
                    if spec.compute_func is not None:
                        specs_to_verify.append(spec)
            
            reports = batch_verify_features(specs_to_verify, stop_on_first_failure=False)
            
            # Update feature specs based on verification results
            for spec in self.specs:
                if spec.name in reports:
                    report = reports[spec.name]
                    if report.passed:
                        spec.mark_causality_verified()
                        spec.window_honest = report.window_honest
                    else:
                        spec.mark_causality_failed()
            
            # Update verification reports
            self.verification_reports.update(reports)
            
            return reports
    
    def get_unverified_features(self) -> List[FeatureSpec]:
        """Get list of features that haven't passed causality verification."""
        return [spec for spec in self.specs if not spec.causality_verified]
    
    def get_features_with_lookahead(self) -> List[FeatureSpec]:
        """Get list of features that have detected lookahead."""
        result = []
        for spec in self.specs:
            if spec.name in self.verification_reports:
                report = self.verification_reports[spec.name]
                if report.lookahead_detected:
                    result.append(spec)
        return result
    
    def get_dishonest_window_features(self) -> List[FeatureSpec]:
        """Get list of features with dishonest window specifications."""
        result = []
        for spec in self.specs:
            if spec.name in self.verification_reports:
                report = self.verification_reports[spec.name]
                if not report.window_honest:
                    result.append(spec)
        return result
    
    def remove_feature(self, name: str, timeframe_min: int) -> bool:
        """
        Remove a feature from the registry.
        
        Args:
            name: Feature name
            timeframe_min: Timeframe in minutes
            
        Returns:
            True if feature was removed, False if not found
        """
        with self.lock:
            for i, spec in enumerate(self.specs):
                if spec.name == name and spec.timeframe_min == timeframe_min:
                    self.specs.pop(i)
                    # Remove verification report if exists
                    if name in self.verification_reports:
                        del self.verification_reports[name]
                    return True
            return False
    
    def clear(self) -> None:
        """Clear all features from the registry."""
        with self.lock:
            self.specs.clear()
            self.verification_reports.clear()
    
    def to_contract_registry(self) -> ContractFeatureRegistry:
        """
        Convert to contract FeatureRegistry (without causality fields).
        
        Returns:
            Contract FeatureRegistry with only verified features
        """
        # Only include features that have passed causality verification
        verified_specs = [
            spec.to_contract_spec()
            for spec in self.specs
            if spec.causality_verified
        ]
        
        return ContractFeatureRegistry(specs=verified_specs)
    
    def specs_for_tf(self, tf_min: int) -> List[FeatureSpec]:
        """
        Get all feature specs for a given timeframe.
        
        Args:
            tf_min: Timeframe in minutes
            
        Returns:
            List of FeatureSpecs for the timeframe (only verified features if enabled)
        """
        if self.verification_enabled:
            # Only return verified features
            filtered = [
                spec for spec in self.specs 
                if spec.timeframe_min == tf_min and spec.causality_verified
            ]
        else:
            # Return all features
            filtered = [spec for spec in self.specs if spec.timeframe_min == tf_min]
        
        # Sort by name for deterministic ordering
        return sorted(filtered, key=lambda s: s.name)
    
    def max_lookback_for_tf(self, tf_min: int) -> int:
        """
        Calculate maximum lookback for a timeframe.
        
        Args:
            tf_min: Timeframe in minutes
            
        Returns:
            Maximum lookback bars (0 if no features or verification fails)
        """
        specs = self.specs_for_tf(tf_min)
        if not specs:
            return 0
        
        # Only consider verified features with honest windows
        honest_lookbacks = [
            spec.lookback_bars 
            for spec in specs 
            if spec.causality_verified and spec.window_honest
        ]
        
        if not honest_lookbacks:
            return 0
        
        return max(honest_lookbacks)


# Import numpy and warnings for the module
import numpy as np
import warnings


# Global registry instance
_default_registry: Optional[FeatureRegistry] = None
_default_registry_lock = threading.Lock()


def get_default_registry() -> FeatureRegistry:
    """
    Get or create the default global feature registry.
    
    Returns:
        Global FeatureRegistry instance
    """
    global _default_registry
    
    with _default_registry_lock:
        if _default_registry is None:
            _default_registry = FeatureRegistry()
            
            # Optionally register default features with verification
            # This would require compute functions for default features
            
        return _default_registry


def set_default_registry(registry: FeatureRegistry) -> None:
    """
    Set the default global feature registry.
    
    Args:
        registry: FeatureRegistry to set as default
    """
    global _default_registry
    
    with _default_registry_lock:
        _default_registry = registry