"""
Phase P2-C: Admission Decisions service.

Contract:
- Creates admission decisions for season candidates
- Writes decisions to database (season_admissions table)
- Generates evidence for audit trail
- Enforces governance rules (season must be FROZEN)
- Idempotent: re-running with same inputs produces same decisions
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, List, Dict

from contracts.season import (
    SeasonAdmissionRequest,
    SeasonAdmissionResponse,
    AdmissionDecision,
    DecisionOutcome,
    AdmissionEvidence,
)
from control.seasons_repo import get_season
from control.season_analysis import analyze_season_jobs
from control.supervisor.db import SupervisorDB, get_default_db_path
from control.supervisor.models import now_iso


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _create_admission_evidence(
    season_id: str,
    candidate_identity: str,
    outcome: DecisionOutcome,
    decision_reason: str,
    decision_criteria: Dict[str, Any],
    actor: str,
) -> AdmissionEvidence:
    """
    Create admission evidence for audit trail.
    """
    return AdmissionEvidence(
        evidence_id=f"admission_{season_id}_{candidate_identity}_{_utc_now_iso()}",
        generated_at=_utc_now_iso(),
        decision_outcome=outcome,
        decision_reason=decision_reason,
        decision_criteria=decision_criteria,
        actor=actor,
        evidence_data={},
    )


def _evaluate_candidate_for_admission(
    candidate: Any,  # SeasonCandidate from analysis
    admission_criteria: Dict[str, Any],
) -> tuple[DecisionOutcome, str, Dict[str, Any]]:
    """
    Evaluate a candidate for admission based on criteria.
    
    Simple rule: admit if score >= min_score threshold.
    """
    min_score = admission_criteria.get("min_score", 0.0)
    score = candidate.research_metrics.get("score", 0.0)
    
    criteria_used = {
        "min_score": min_score,
        "candidate_score": score,
    }
    
    if score >= min_score:
        return (
            DecisionOutcome.ADMIT,
            f"Score {score} >= minimum threshold {min_score}",
            criteria_used,
        )
    else:
        return (
            DecisionOutcome.REJECT,
            f"Score {score} < minimum threshold {min_score}",
            criteria_used,
        )


def create_admission_decisions(
    request: SeasonAdmissionRequest,
) -> SeasonAdmissionResponse:
    """
    Create admission decisions for season candidates.
    
    Contract:
    - Season must be FROZEN (403 if not)
    - Reads candidates from season analysis
    - Evaluates each candidate against admission criteria
    - Writes decisions to database (season_admissions table)
    - Generates evidence for audit trail
    - Returns summary of decisions
    """
    # Get season to check state
    season, _ = get_season(request.season_id)
    if season is None:
        raise ValueError(f"Season {request.season_id} not found")
    
    # Season must be FROZEN for admission decisions
    if season.state != "FROZEN":
        raise ValueError(f"Season must be FROZEN for admission decisions, current state: {season.state}")
    
    # Analyze season to get candidates
    analysis = analyze_season_jobs(request.season_id)
    
    # Evaluate each candidate
    decisions: List[AdmissionDecision] = []
    admitted_count = 0
    rejected_count = 0
    held_count = 0
    
    for candidate in analysis.candidates:
        # Evaluate candidate
        outcome, reason, criteria = _evaluate_candidate_for_admission(
            candidate, request.admission_criteria
        )
        
        # Create evidence
        evidence = _create_admission_evidence(
            season_id=request.season_id,
            candidate_identity=candidate.identity.candidate_id,
            outcome=outcome,
            decision_reason=reason,
            decision_criteria=criteria,
            actor=request.actor,
        )
        
        # Create decision
        decision = AdmissionDecision(
            candidate_identity=candidate.identity.candidate_id,
            outcome=outcome,
            decision_reason=reason,
            evidence=evidence,
            decided_at=_utc_now_iso(),
            decided_by=request.actor,
        )
        
        decisions.append(decision)
        
        # Count outcomes
        if outcome == DecisionOutcome.ADMIT:
            admitted_count += 1
        elif outcome == DecisionOutcome.REJECT:
            rejected_count += 1
        elif outcome == DecisionOutcome.HOLD:
            held_count += 1
    
    # Write decisions to database
    db = SupervisorDB(get_default_db_path())
    with db._connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            for decision in decisions:
                # Check if decision already exists
                cursor = conn.execute("""
                    SELECT 1 FROM season_admissions 
                    WHERE season_id = ? AND candidate_identity = ?
                """, (request.season_id, decision.candidate_identity))
                
                if cursor.fetchone() is None:
                    # Insert new decision
                    conn.execute("""
                        INSERT INTO season_admissions (
                            season_id, candidate_identity, outcome,
                            decision_reason, evidence_json, decided_at, decided_by
                        ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, (
                        request.season_id,
                        decision.candidate_identity,
                        decision.outcome.value,
                        decision.decision_reason,
                        json.dumps(decision.evidence.model_dump()),
                        decision.decided_at,
                        decision.decided_by,
                    ))
            
            conn.commit()
        except Exception:
            conn.rollback()
            raise
    
    # Update season state to DECIDING if we have decisions
    if decisions:
        with db._connect() as conn:
            conn.execute("""
                UPDATE seasons 
                SET state = 'DECIDING', updated_at = ?
                WHERE season_id = ? AND state = 'FROZEN'
            """, (now_iso(), request.season_id))
    
    return SeasonAdmissionResponse(
        season_id=request.season_id,
        total_candidates=len(decisions),
        admitted_count=admitted_count,
        rejected_count=rejected_count,
        held_count=held_count,
        decisions=decisions,
        generated_at=_utc_now_iso(),
    )


def get_season_admissions(season_id: str) -> List[AdmissionDecision]:
    """
    Get admission decisions for a season.
    """
    db = SupervisorDB(get_default_db_path())
    with db._connect() as conn:
        cursor = conn.execute("""
            SELECT 
                season_id, candidate_identity, outcome,
                decision_reason, evidence_json, decided_at, decided_by
            FROM season_admissions
            WHERE season_id = ?
            ORDER BY decided_at DESC
        """, (season_id,))
        
        rows = cursor.fetchall()
    
    decisions: List[AdmissionDecision] = []
    for row in rows:
        # Parse evidence JSON
        evidence_data = json.loads(row["evidence_json"]) if row["evidence_json"] else {}
        evidence = AdmissionEvidence.model_validate(evidence_data)
        
        decision = AdmissionDecision(
            candidate_identity=row["candidate_identity"],
            outcome=DecisionOutcome(row["outcome"]),
            decision_reason=row["decision_reason"],
            evidence=evidence,
            decided_at=row["decided_at"],
            decided_by=row["decided_by"],
        )
        decisions.append(decision)
    
    return decisions