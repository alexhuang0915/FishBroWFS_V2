from dataclasses import dataclass
from typing import Optional, Dict, Any
import hashlib
import json


@dataclass
class RunPlateauPayload:
    """Payload for run_plateau_v2 job."""
    research_run_id: str  # Job ID of the research run to process
    k_neighbors: Optional[int] = None
    score_threshold_rel: Optional[float] = None
    
    def validate(self) -> None:
        """Validate payload fields."""
        if not self.research_run_id:
            raise ValueError("research_run_id is required")
        
        # Validate optional parameters
        if self.k_neighbors is not None and self.k_neighbors < 1:
            raise ValueError("k_neighbors must be >= 1")
        if self.score_threshold_rel is not None and (self.score_threshold_rel <= 0 or self.score_threshold_rel > 1):
            raise ValueError("score_threshold_rel must be between 0 and 1")
    
    def compute_input_fingerprint(self) -> str:
        """Compute deterministic fingerprint of input parameters."""
        data = {
            "research_run_id": self.research_run_id,
            "k_neighbors": self.k_neighbors,
            "score_threshold_rel": self.score_threshold_rel
        }
        # Sort keys for deterministic JSON
        json_str = json.dumps(data, sort_keys=True, separators=(',', ':'))
        return hashlib.sha256(json_str.encode()).hexdigest()[:16]