import json
import hashlib
from typing import Dict, Any

def stable_seed_from_intent(intent_obj: Dict[str, Any]) -> int:
    """
    Derive stable 32-bit seed from intent/config dict.
    
    Deterministic: same input dict -> same seed across runs/machines.
    """
    # Canonical JSON: sorted keys, no whitespace
    payload = json.dumps(
        intent_obj,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False
    )
    # SHA256 -> first 8 hex chars -> int mod 2**32
    h = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    seed = int(h[:8], 16) % (1 << 32)
    return seed