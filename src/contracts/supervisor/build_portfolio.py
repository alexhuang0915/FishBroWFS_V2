from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List
import hashlib
import json


@dataclass
class BuildPortfolioPayload:
    """Payload for build_portfolio_v2 job."""
    season: str  # Season identifier e.g., "2026Q1"
    outputs_root: Optional[str] = None  # Optional override for outputs root
    allowlist: Optional[str] = None  # Comma-separated list of allowed symbols
    candidate_run_ids: Optional[List[str]] = None  # Explicit candidate run IDs (optional)
    timeframe: Optional[str] = None  # Timeframe e.g., "60m" (optional)
    governance_params_overrides: Optional[Dict[str, Any]] = None  # Governance param overrides
    portfolio_id: Optional[str] = None  # Pre-computed portfolio ID (optional)
    
    def validate(self) -> None:
        """Validate payload fields."""
        if not self.season:
            raise ValueError("season is required")
        # Basic validation for season format (optional)
        if len(self.season) < 4:
            raise ValueError("season should be at least 4 characters")
        
        # Validate candidate_run_ids if provided
        if self.candidate_run_ids is not None:
            if not self.candidate_run_ids:
                raise ValueError("candidate_run_ids must be non-empty if provided")
            if not all(isinstance(run_id, str) and run_id for run_id in self.candidate_run_ids):
                raise ValueError("candidate_run_ids must be a list of non-empty strings")
    
    def compute_input_fingerprint(self) -> str:
        """Compute deterministic fingerprint of input parameters."""
        data = {
            "season": self.season,
            "outputs_root": self.outputs_root,
            "allowlist": self.allowlist,
            "candidate_run_ids": self.candidate_run_ids,
            "timeframe": self.timeframe,
            "governance_params_overrides": self.governance_params_overrides,
            "portfolio_id": self.portfolio_id
        }
        # Sort keys for deterministic JSON
        json_str = json.dumps(data, sort_keys=True, separators=(',', ':'))
        return hashlib.sha256(json_str.encode()).hexdigest()[:16]