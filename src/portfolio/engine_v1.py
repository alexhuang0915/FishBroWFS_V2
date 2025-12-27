"""Portfolio admission engine V1."""

import logging
from typing import List, Tuple, Dict, Optional
from datetime import datetime

from core.schemas.portfolio_v1 import (
    PortfolioPolicyV1,
    SignalCandidateV1,
    OpenPositionV1,
    AdmissionDecisionV1,
    PortfolioStateV1,
    PortfolioSummaryV1,
)

logger = logging.getLogger(__name__)


class PortfolioEngineV1:
    """Portfolio admission engine with deterministic decision making."""
    
    def __init__(self, policy: PortfolioPolicyV1, equity_base: float):
        """
        Initialize portfolio engine.
        
        Args:
            policy: Portfolio policy defining limits and behavior
            equity_base: Initial equity in base currency (TWD)
        """
        self.policy = policy
        self.equity_base = equity_base
        
        # Current state
        self.open_positions: List[OpenPositionV1] = []
        self.slots_used = 0
        self.margin_used_base = 0.0
        self.notional_used_base = 0.0
        
        # Track decisions per bar
        self.decisions: List[AdmissionDecisionV1] = []
        self.bar_states: Dict[Tuple[int, datetime], PortfolioStateV1] = {}
        
        # Statistics
        self.reject_count = 0
        
    def _compute_sort_key(self, candidate: SignalCandidateV1) -> Tuple:
        """
        Compute deterministic sort key for candidate.
        
        Sort order (ascending):
        1. Higher priority first (lower priority number = higher priority)
        2. Higher candidate_score first (negative for descending)
        3. signal_series_sha256 lexicographically as final tie-break
        
        Returns:
            Tuple for sorting
        """
        priority = self.policy.strategy_priority.get(candidate.strategy_id, 9999)
        # Negative candidate_score for descending order (higher score first)
        score = -candidate.candidate_score
        # Use signal_series_sha256 as final deterministic tie-break
        # If not available, use strategy_id + instrument_id as fallback
        sha = candidate.signal_series_sha256 or f"{candidate.strategy_id}:{candidate.instrument_id}"
        
        return (priority, score, sha)
    
    def _get_sort_key_string(self, candidate: SignalCandidateV1) -> str:
        """Generate human-readable sort key string for audit."""
        priority = self.policy.strategy_priority.get(candidate.strategy_id, 9999)
        return f"priority={priority},candidate_score={candidate.candidate_score:.4f},sha={candidate.signal_series_sha256 or 'N/A'}"
    
    def _check_instrument_cap(self, instrument_id: str) -> bool:
        """Check if instrument has available slots."""
        if not self.policy.max_slots_by_instrument:
            return True
        
        max_slots = self.policy.max_slots_by_instrument.get(instrument_id)
        if max_slots is None:
            return True
        
        # Count current slots for this instrument
        current_slots = sum(
            1 for pos in self.open_positions 
            if pos.instrument_id == instrument_id
        )
        return current_slots < max_slots
    
    def _can_admit(self, candidate: SignalCandidateV1) -> Tuple[bool, str]:
        """
        Check if candidate can be admitted.
        
        Returns:
            Tuple of (can_admit, reason)
        """
        # Check total slots
        if self.slots_used + candidate.required_slot > self.policy.max_slots_total:
            return False, "REJECT_FULL"
        
        # Check instrument-specific cap
        if not self._check_instrument_cap(candidate.instrument_id):
            return False, "REJECT_FULL"  # Instrument-specific full
        
        # Check margin ratio
        required_margin = candidate.required_margin_base
        new_margin_used = self.margin_used_base + required_margin
        max_allowed_margin = self.equity_base * self.policy.max_margin_ratio
        
        if new_margin_used > max_allowed_margin:
            return False, "REJECT_MARGIN"
        
        # Check notional ratio (optional)
        if self.policy.max_notional_ratio is not None:
            # Note: notional check not implemented in v1
            pass
        
        return True, "ACCEPT"
    
    def _add_position(self, candidate: SignalCandidateV1):
        """Add new position to portfolio."""
        position = OpenPositionV1(
            strategy_id=candidate.strategy_id,
            instrument_id=candidate.instrument_id,
            slots=candidate.required_slot,
            margin_base=candidate.required_margin_base,
            notional_base=0.0,  # Notional not tracked in v1
            entry_bar_index=candidate.bar_index,
            entry_bar_ts=candidate.bar_ts,
        )
        self.open_positions.append(position)
        self.slots_used += candidate.required_slot
        self.margin_used_base += candidate.required_margin_base
    
    def admit_candidates(
        self,
        candidates: List[SignalCandidateV1],
        current_open_positions: Optional[List[OpenPositionV1]] = None,
    ) -> List[AdmissionDecisionV1]:
        """
        Process admission for a list of candidates at the same bar.
        
        Args:
            candidates: List of candidates for the same bar
            current_open_positions: Optional list of existing open positions
                (if None, uses engine's current state)
        
        Returns:
            List of admission decisions
        """
        # Reset to provided open positions if given
        if current_open_positions is not None:
            self.open_positions = current_open_positions.copy()
            self.slots_used = sum(pos.slots for pos in self.open_positions)
            self.margin_used_base = sum(pos.margin_base for pos in self.open_positions)
        
        # Sort candidates deterministically
        sorted_candidates = sorted(candidates, key=self._compute_sort_key)
        
        decisions = []
        for candidate in sorted_candidates:
            # Check if can admit
            can_admit, reason = self._can_admit(candidate)
            
            # Create decision
            sort_key_str = self._get_sort_key_string(candidate)
            decision = AdmissionDecisionV1(
                strategy_id=candidate.strategy_id,
                instrument_id=candidate.instrument_id,
                bar_ts=candidate.bar_ts,
                bar_index=candidate.bar_index,
                signal_strength=candidate.signal_strength,
                candidate_score=candidate.candidate_score,
                signal_series_sha256=candidate.signal_series_sha256,
                accepted=can_admit,
                reason=reason,
                sort_key_used=sort_key_str,
                slots_after=self.slots_used + (candidate.required_slot if can_admit else 0),
                margin_after_base=self.margin_used_base + (candidate.required_margin_base if can_admit else 0),
            )
            
            if can_admit:
                # Admit candidate
                self._add_position(candidate)
                logger.debug(
                    f"Admitted {candidate.strategy_id}/{candidate.instrument_id} "
                    f"at bar {candidate.bar_index}, slots={self.slots_used}, "
                    f"margin={self.margin_used_base:.0f}"
                )
            else:
                self.reject_count += 1
                logger.debug(
                    f"Rejected {candidate.strategy_id}/{candidate.instrument_id} "
                    f"at bar {candidate.bar_index}: {reason}"
                )
            
            decisions.append(decision)
        
        # Record bar state
        if candidates:
            bar_ts = candidates[0].bar_ts
            bar_index = candidates[0].bar_index
            self.bar_states[(bar_index, bar_ts)] = PortfolioStateV1(
                bar_ts=bar_ts,
                bar_index=bar_index,
                equity_base=self.equity_base,
                slots_used=self.slots_used,
                margin_used_base=self.margin_used_base,
                notional_used_base=self.notional_used_base,
                open_positions=self.open_positions.copy(),
                reject_count=self.reject_count,
            )
        
        self.decisions.extend(decisions)
        return decisions
    
    def get_summary(self) -> PortfolioSummaryV1:
        """Generate summary of admission results."""
        reject_reasons = {}
        for decision in self.decisions:
            if not decision.accepted:
                reject_reasons[decision.reason] = reject_reasons.get(decision.reason, 0) + 1
        
        total = len(self.decisions)
        accepted = sum(1 for d in self.decisions if d.accepted)
        rejected = total - accepted
        
        return PortfolioSummaryV1(
            total_candidates=total,
            accepted_count=accepted,
            rejected_count=rejected,
            reject_reasons=reject_reasons,
            final_slots_used=self.slots_used,
            final_margin_used_base=self.margin_used_base,
            final_margin_ratio=self.margin_used_base / self.equity_base if self.equity_base > 0 else 0.0,
            policy_sha256="",  # To be filled by caller
            spec_sha256="",  # To be filled by caller
        )
    
    def reset(self):
        """Reset engine to initial state."""
        self.open_positions.clear()
        self.slots_used = 0
        self.margin_used_base = 0.0
        self.notional_used_base = 0.0
        self.decisions.clear()
        self.bar_states.clear()
        self.reject_count = 0


# Convenience function
def admit_candidates(
    policy: PortfolioPolicyV1,
    equity_base: float,
    candidates: List[SignalCandidateV1],
    current_open_positions: Optional[List[OpenPositionV1]] = None,
) -> Tuple[List[AdmissionDecisionV1], PortfolioSummaryV1]:
    """
    Convenience function for one-shot admission.
    
    Returns:
        Tuple of (decisions, summary)
    """
    engine = PortfolioEngineV1(policy, equity_base)
    decisions = engine.admit_candidates(candidates, current_open_positions)
    summary = engine.get_summary()
    return decisions, summary