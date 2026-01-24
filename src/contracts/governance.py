"""
Governance Contracts (Layer 4).

Defines Policies and Decisions.
"""

from __future__ import annotations

from enum import Enum
from datetime import datetime, timezone
from typing import List, Optional

from pydantic import BaseModel, Field

class DecisionType(str, Enum):
    ADMIT = "ADMIT"
    REJECT = "REJECT"

class Policy(BaseModel):
    """
    Criteria for accepting a Research Result.
    """
    policy_id: str
    min_sharpe: float = 0.0
    max_drawdown: float = 1.0
    min_total_return: float = 0.0
    min_trades: int = 0

class Decision(BaseModel):
    """
    The verdict from the Gatekeeper.
    """
    decision_id: str
    run_id: str
    policy_id: str
    verdict: DecisionType
    reason: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
