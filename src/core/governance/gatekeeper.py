"""
Gatekeeper Service (Layer 4).

The Court that decides if a Research Result is admissible.
"""

from __future__ import annotations

import logging
import uuid
from contracts.research import ResearchResult
from contracts.governance import Policy, Decision, DecisionType

logger = logging.getLogger(__name__)

class Gatekeeper:
    """
    Evaluates ResearchResults against Policies.
    """
    
    @staticmethod
    def evaluate(result: ResearchResult, policy: Policy) -> Decision:
        """
        Judge the result.
        """
        reasons = []
        is_admissible = True
        
        # 1. Check Metrics
        if result.metrics.sharpe_ratio < policy.min_sharpe:
            is_admissible = False
            reasons.append(f"Sharpe {result.metrics.sharpe_ratio:.2f} < {policy.min_sharpe}")
            
        if result.metrics.max_drawdown > policy.max_drawdown:
            is_admissible = False
            reasons.append(f"Drawdown {result.metrics.max_drawdown:.2f} > {policy.max_drawdown}")
            
        if result.metrics.total_return < policy.min_total_return:
            is_admissible = False
            reasons.append(f"Return {result.metrics.total_return:.2f} < {policy.min_total_return}")
            
        if result.metrics.total_trades < policy.min_trades:
            is_admissible = False
            reasons.append(f"Trades {result.metrics.total_trades} < {policy.min_trades}")
            
        # 2. Construct Decision
        verdict = DecisionType.ADMIT if is_admissible else DecisionType.REJECT
        reason_str = "; ".join(reasons) if reasons else "Meets all criteria."
        
        return Decision(
            decision_id=str(uuid.uuid4()),
            run_id=result.run_id,
            policy_id=policy.policy_id,
            verdict=verdict,
            reason=reason_str
        )
