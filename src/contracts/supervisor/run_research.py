from dataclasses import dataclass
from typing import Optional, Dict, Any
import hashlib
import json


@dataclass
class RunResearchPayload:
    """Payload for run_research_v2 job."""
    strategy_id: str
    start_date: str   # YYYY-MM-DD
    end_date: str     # YYYY-MM-DD
    params_override: Optional[Dict[str, Any]] = None
    
    def validate(self) -> None:
        """Validate payload fields."""
        if not self.strategy_id:
            raise ValueError("strategy_id is required")
        if not self.start_date:
            raise ValueError("start_date is required")
        if not self.end_date:
            raise ValueError("end_date is required")
        
        # Validate date format (basic check)
        if len(self.start_date) != 10 or self.start_date[4] != '-' or self.start_date[7] != '-':
            raise ValueError(f"start_date must be YYYY-MM-DD format, got {self.start_date}")
        if len(self.end_date) != 10 or self.end_date[4] != '-' or self.end_date[7] != '-':
            raise ValueError(f"end_date must be YYYY-MM-DD format, got {self.end_date}")
    
    def compute_input_fingerprint(self) -> str:
        """Compute deterministic fingerprint of input parameters."""
        data = {
            "strategy_id": self.strategy_id,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "params_override": self.params_override or {}
        }
        # Sort keys for deterministic JSON
        json_str = json.dumps(data, sort_keys=True, separators=(',', ':'))
        return hashlib.sha256(json_str.encode()).hexdigest()[:16]