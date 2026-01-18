"""
Verdict Stamp v1 - SSOT contract for reproducible verdicts.

This module defines the Verdict Stamp v1 contract, which guarantees
that historical verdicts remain interpretable even as rules evolve.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class VerdictStampV1(BaseModel):
    """Verdict stamp capturing all version dependencies at verdict time."""
    
    model_config = ConfigDict(frozen=True, extra="forbid")
    
    schema_version: Literal["v1.0"] = Field(
        default="v1.0",
        description="Verdict stamp schema version"
    )
    policy_version: str = Field(
        ...,
        description="Policy version used for verdict (e.g., registry schema version)"
    )
    dictionary_version: str = Field(
        ...,
        description="Gate reason explain dictionary version (e.g., 'v1.5.0')"
    )
    schema_contract_version: str = Field(
        ...,
        description="Gate summary schema contract version (e.g., 'v1')"
    )
    evaluator_version: str = Field(
        ...,
        description="Gate evaluation engine version (e.g., 'v1.5.0')"
    )
    created_at_iso: str = Field(
        ...,
        description="ISO-8601 timestamp when verdict was stamped"
    )
    
    @classmethod
    def create_for_job(
        cls,
        job_id: str,
        *,
        policy_version: str = None,
        dictionary_version: str = None,
        schema_contract_version: str = None,
        evaluator_version: str = None,
    ) -> "VerdictStampV1":
        """
        Create verdict stamp for a job with automatic version detection.
        
        Args:
            job_id: Job identifier (for context)
            policy_version: Optional explicit policy version
            dictionary_version: Optional explicit dictionary version
            schema_contract_version: Optional explicit schema contract version
            evaluator_version: Optional explicit evaluator version
            
        Returns:
            VerdictStampV1 with detected versions
        """
        from datetime import datetime
        
        # Detect policy version from registry if not provided
        if policy_version is None:
            try:
                from config.registry import __version__ as registry_version
                policy_version = registry_version
            except (ImportError, AttributeError):
                policy_version = "unknown"
        
        # Detect dictionary version if not provided
        if dictionary_version is None:
            try:
                from .gate_reason_explain import DICTIONARY_VERSION
                dictionary_version = DICTIONARY_VERSION
            except (ImportError, AttributeError):
                dictionary_version = "unknown"
        
        # Detect schema contract version if not provided
        if schema_contract_version is None:
            try:
                from .gate_summary_schemas import GateSummaryV1
                schema_contract_version = GateSummaryV1.model_fields["schema_version"].default
            except (ImportError, AttributeError, KeyError):
                schema_contract_version = "v1"
        
        # Detect evaluator version if not provided
        if evaluator_version is None:
            try:
                from core.portfolio import __version__ as core_version
                evaluator_version = core_version
            except (ImportError, AttributeError):
                evaluator_version = "v1.5.0"  # Default for v1.5
        
        return cls(
            policy_version=policy_version,
            dictionary_version=dictionary_version,
            schema_contract_version=schema_contract_version,
            evaluator_version=evaluator_version,
            created_at_iso=datetime.now().isoformat(),
        )
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return self.model_dump()
    
    @classmethod
    def from_dict(cls, data: dict) -> "VerdictStampV1":
        """Create from dictionary (JSON deserialization)."""
        return cls.model_validate(data)
    
    def compare_with_current(self) -> dict:
        """
        Compare stamp versions with current system versions.
        
        Returns:
            Dictionary with comparison results
        """
        result = {
            "stamp": self.to_dict(),
            "current": {},
            "matches": {},
            "warnings": [],
        }
        
        # Get current versions
        try:
            from .gate_reason_explain import DICTIONARY_VERSION
            result["current"]["dictionary_version"] = DICTIONARY_VERSION
            result["matches"]["dictionary_version"] = (
                self.dictionary_version == DICTIONARY_VERSION
            )
            if not result["matches"]["dictionary_version"]:
                result["warnings"].append(
                    f"Dictionary version mismatch: stamp={self.dictionary_version}, "
                    f"current={DICTIONARY_VERSION}"
                )
        except (ImportError, AttributeError):
            result["current"]["dictionary_version"] = "unknown"
            result["matches"]["dictionary_version"] = False
        
        try:
            from config.registry import __version__ as registry_version
            result["current"]["policy_version"] = registry_version
            result["matches"]["policy_version"] = (
                self.policy_version == registry_version
            )
            if not result["matches"]["policy_version"]:
                result["warnings"].append(
                    f"Policy version mismatch: stamp={self.policy_version}, "
                    f"current={registry_version}"
                )
        except (ImportError, AttributeError):
            result["current"]["policy_version"] = "unknown"
            result["matches"]["policy_version"] = False
        
        # Schema contract version
        try:
            from .gate_summary_schemas import GateSummaryV1
            current_schema = GateSummaryV1.model_fields["schema_version"].default
            result["current"]["schema_contract_version"] = current_schema
            result["matches"]["schema_contract_version"] = (
                self.schema_contract_version == current_schema
            )
            if not result["matches"]["schema_contract_version"]:
                result["warnings"].append(
                    f"Schema contract version mismatch: stamp={self.schema_contract_version}, "
                    f"current={current_schema}"
                )
        except (ImportError, AttributeError, KeyError):
            result["current"]["schema_contract_version"] = "v1"
            result["matches"]["schema_contract_version"] = False
        
        return result


# Version constant for verdict stamp schema
VERDICT_STAMP_SCHEMA_VERSION = "v1.0"