from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from datetime import datetime, UTC
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


def _canonicalize_for_json(obj: Any) -> Any:
    """
    Recursively canonicalize Python objects for deterministic JSON serialization.
    
    Rules:
    - numpy scalar (int64, float64) → Python int/float
    - tuple → list
    - Decimal → str (standard decimal representation)
    - dict keys are sorted (handled by json.dumps sort_keys)
    - list/tuple elements are recursively canonicalized
    - dict values are recursively canonicalized
    """
    # Try to import numpy (optional)
    try:
        import numpy as np
        HAS_NUMPY = True
    except ImportError:
        HAS_NUMPY = False
    
    # Decimal detection
    try:
        from decimal import Decimal
        HAS_DECIMAL = True
    except ImportError:
        HAS_DECIMAL = False
    
    if HAS_NUMPY and isinstance(obj, np.integer):
        return int(obj)
    if HAS_NUMPY and isinstance(obj, np.floating):
        return float(obj)
    if HAS_DECIMAL and isinstance(obj, Decimal):
        # Use standard string representation (no scientific notation)
        return str(obj)
    if isinstance(obj, tuple):
        return [_canonicalize_for_json(item) for item in obj]
    if isinstance(obj, list):
        return [_canonicalize_for_json(item) for item in obj]
    if isinstance(obj, dict):
        # Note: sorting of keys is done by json.dumps with sort_keys=True
        # but we still need to canonicalize values.
        return {key: _canonicalize_for_json(value) for key, value in obj.items()}
    # For any other type, assume it's already JSON serializable (int, float, str, bool, None)
    return obj


def stable_params_hash(payload: dict) -> str:
    """
    Compute stable ABI-level hash of parameters.
    
    Rules:
    - JSON canonicalization: sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    - Hash = sha256(bytes)
    - Logic MUST NEVER CHANGE after merge.
    """
    import hashlib
    
    # Canonicalize payload before serialization
    canonical_payload = _canonicalize_for_json(payload)
    
    # Ensure deterministic JSON serialization matching canonical_json_bytes
    canonical_json = json.dumps(
        canonical_payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()


def now_iso() -> str:
    """Return current UTC time in ISO format."""
    # Use timezone-aware datetime (UTC)
    dt = datetime.now(UTC)
    # Convert +00:00 offset to Z for backward compatibility
    return dt.isoformat().replace('+00:00', 'Z')