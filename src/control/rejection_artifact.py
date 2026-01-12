"""
Standardized rejection artifact for governance rejections.

Schema:
{
  "schema_version": "1.0",
  "rejection_code": "string",
  "rejection_message": "string",
  "rejected_at": "ISO8601 UTC timestamp",
  "rejected_by": "system/user identifier",
  "context": {
    "job_id": "optional",
    "run_id": "optional",
    "policy_name": "optional",
    "fields": {}  # additional context-specific fields
  }
}
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Dict, Any, Optional

from control.artifacts import write_json_atomic


@dataclass
class RejectionArtifact:
    """Standardized rejection artifact."""
    
    # Required fields
    rejection_code: str
    rejection_message: str
    
    # Optional fields with defaults
    schema_version: str = "1.0"
    rejected_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"))
    rejected_by: str = "system"
    
    # Context fields
    context: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> RejectionArtifact:
        """Create from dictionary."""
        return cls(**data)
    
    def write(self, output_path: Path) -> None:
        """Write rejection artifact to file atomically."""
        write_json_atomic(output_path, self.to_dict())


def create_policy_rejection(
    policy_name: str,
    failure_message: str,
    job_id: Optional[str] = None,
    run_id: Optional[str] = None,
    additional_context: Optional[Dict[str, Any]] = None
) -> RejectionArtifact:
    """Create a rejection artifact for policy failure."""
    context = {
        "policy_name": policy_name,
        "job_id": job_id,
        "run_id": run_id,
    }
    
    if additional_context:
        context.update(additional_context)
    
    # Clean up None values
    context = {k: v for k, v in context.items() if v is not None}
    
    return RejectionArtifact(
        rejection_code=f"policy_failure.{policy_name}",
        rejection_message=failure_message,
        context=context
    )


def create_validation_rejection(
    validation_error: str,
    field_errors: Optional[Dict[str, str]] = None,
    job_id: Optional[str] = None,
    run_id: Optional[str] = None
) -> RejectionArtifact:
    """Create a rejection artifact for validation failure."""
    context = {
        "validation_type": "parameter_validation",
        "job_id": job_id,
        "run_id": run_id,
        "field_errors": field_errors or {}
    }
    
    # Clean up None values
    context = {k: v for k, v in context.items() if v is not None}
    
    return RejectionArtifact(
        rejection_code="validation_failure",
        rejection_message=validation_error,
        context=context
    )


def create_governance_rejection(
    governance_rule: str,
    reason: str,
    affected_ids: Optional[list] = None,
    metrics: Optional[Dict[str, Any]] = None,
    job_id: Optional[str] = None,
    run_id: Optional[str] = None
) -> RejectionArtifact:
    """Create a rejection artifact for governance rule violation."""
    context = {
        "governance_rule": governance_rule,
        "job_id": job_id,
        "run_id": run_id,
        "affected_ids": affected_ids or [],
        "metrics": metrics or {}
    }
    
    # Clean up None values
    context = {k: v for k, v in context.items() if v is not None}
    
    return RejectionArtifact(
        rejection_code=f"governance_violation.{governance_rule}",
        rejection_message=reason,
        context=context
    )


def write_rejection_artifact(
    output_path: Path,
    rejection_code: str,
    rejection_message: str,
    context: Optional[Dict[str, Any]] = None
) -> None:
    """Convenience function to write a rejection artifact."""
    artifact = RejectionArtifact(
        rejection_code=rejection_code,
        rejection_message=rejection_message,
        context=context or {}
    )
    artifact.write(output_path)