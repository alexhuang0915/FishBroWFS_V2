from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from datetime import datetime
import json


@dataclass
class PolicyCheck:
    """Result of a single policy check."""
    policy_name: str
    passed: bool
    message: str
    checked_at: str  # ISO-8601


@dataclass
class PolicyCheckBundle:
    """Bundle of pre-flight and post-flight policy checks."""
    pre_flight_checks: List[PolicyCheck] = field(default_factory=list)
    post_flight_checks: List[PolicyCheck] = field(default_factory=list)
    downstream_admissible: bool = True


@dataclass
class FingerprintBundle:
    """Fingerprint bundle for deterministic input/output identification."""
    params_hash: str
    dependencies: Dict[str, str]
    code_fingerprint: str  # git commit hash
    hash_version: str = "v1"


@dataclass
class RuntimeMetrics:
    """Runtime execution metrics."""
    job_id: str
    handler_name: str
    execution_time_sec: float
    peak_memory_mb: float
    custom_metrics: Dict[str, Any] = field(default_factory=dict)


def stable_params_hash(payload: dict) -> str:
    """
    Compute stable ABI-level hash of parameters.
    
    Rules:
    - JSON canonicalization: sort_keys=True, separators=(",", ":")
    - Hash = sha256(bytes)
    - Logic MUST NEVER CHANGE after merge.
    """
    import hashlib
    
    # Ensure deterministic JSON serialization
    canonical_json = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical_json.encode()).hexdigest()


def now_iso() -> str:
    """Return current UTC time in ISO format."""
    return datetime.utcnow().isoformat() + "Z"