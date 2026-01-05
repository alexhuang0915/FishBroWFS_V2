from dataclasses import dataclass
from typing import Optional, Dict, Any
import hashlib
import json


@dataclass
class RunFreezePayload:
    """Payload for run_freeze_v2 job."""
    season: str  # Season identifier e.g., "2026Q1"
    force: Optional[bool] = False
    engine_version: Optional[str] = None
    notes: Optional[str] = None
    
    def validate(self) -> None:
        """Validate payload fields."""
        if not self.season:
            raise ValueError("season is required")
        # Basic validation for season format (optional)
        if len(self.season) < 4:
            raise ValueError("season should be at least 4 characters")
    
    def compute_input_fingerprint(self) -> str:
        """Compute deterministic fingerprint of input parameters."""
        data = {
            "season": self.season,
            "force": self.force,
            "engine_version": self.engine_version,
            "notes": self.notes
        }
        # Sort keys for deterministic JSON
        json_str = json.dumps(data, sort_keys=True, separators=(',', ':'))
        return hashlib.sha256(json_str.encode()).hexdigest()[:16]