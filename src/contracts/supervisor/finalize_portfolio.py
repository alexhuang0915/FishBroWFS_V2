from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class FinalizePortfolioPayload:
    """Payload for FINALIZE_PORTFOLIO_V1 job."""

    season: str  # e.g. "2026Q1"
    portfolio_id: str  # portfolio directory name under outputs/artifacts/seasons/{season}/portfolios/
    outputs_root: Optional[str] = None  # Optional override for outputs root (tests/advanced)

    def validate(self) -> None:
        if not self.season:
            raise ValueError("season is required")
        if not self.portfolio_id:
            raise ValueError("portfolio_id is required")

