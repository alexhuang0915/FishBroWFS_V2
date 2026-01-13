"""
Phase P2-D: Export Portfolio Candidate Set service.

Contract:
- Exports admitted candidates as a portfolio candidate set
- Creates versioned export artifact
- Writes export record to database (season_exports table)
- Generates evidence for audit trail
- Season must be in DECIDING or ARCHIVED state
"""

from __future__ import annotations

import json
import hashlib
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, List, Dict

from contracts.season import (
    SeasonExportCandidatesRequest,
    SeasonExportCandidatesResponse,
    PortfolioCandidateSetV1,
    AdmissionDecision,
    DecisionOutcome,
    SeasonHardBoundary,
    AdmissionDecisionEnum,
)
from control.seasons_repo import get_season
from control.season_admission import get_season_admissions
from control.supervisor.db import SupervisorDB, get_default_db_path
from control.supervisor.models import now_iso
from control.artifacts import write_json_atomic


def get_exports_root() -> Path:
    """Get exports root directory from environment variable."""
    return Path(os.environ.get("FISHBRO_EXPORTS_ROOT", "outputs/exports"))


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _generate_export_id(season_id: str, timestamp: str) -> str:
    """Generate deterministic export ID."""
    hash_input = f"{season_id}_{timestamp}"
    return f"export_{hashlib.sha256(hash_input.encode()).hexdigest()[:16]}"


def _create_export_evidence(
    season_id: str,
    export_id: str,
    candidate_count: int,
    actor: str,
) -> dict:
    """
    Create export evidence for audit trail.
    """
    return {
        "evidence_id": f"export_{season_id}_{export_id}",
        "generated_at": _utc_now_iso(),
        "export_parameters": {},
        "actor": actor,
        "evidence_data": {
            "candidate_count": candidate_count,
            "export_format": "portfolio_candidate_set_v1",
        },
    }


def _create_candidate_export_record(
    candidate_identity: str,
    admission_decision: AdmissionDecision,
    export_rank: int,
) -> dict:
    """
    Create candidate export record from admission decision.
    """
    return {
        "candidate_identity": candidate_identity,
        "export_rank": export_rank,
        "admission_outcome": admission_decision.outcome.value,
        "admission_reason": admission_decision.decision_reason,
        "exported_at": _utc_now_iso(),
    }


def export_season_candidates(
    season_id: str,
    request: SeasonExportCandidatesRequest,
) -> SeasonExportCandidatesResponse:
    """
    Export admitted candidates as a portfolio candidate set.
    
    Contract:
    - Season must be DECIDING or ARCHIVED (403 if not)
    - Reads admission decisions from database
    - Filters to ADMITTED candidates only
    - Creates versioned export artifact
    - Writes export record to database
    - Returns export summary
    """
    # Get season to check state
    season, _ = get_season(season_id)
    if season is None:
        raise ValueError(f"Season {season_id} not found")
    
    # Season must be DECIDING or ARCHIVED for export
    if season.state not in ("DECIDING", "ARCHIVED"):
        raise ValueError(
            f"Season must be DECIDING or ARCHIVED for export, current state: {season.state}"
        )
    
    # Get admission decisions
    admission_decisions = get_season_admissions(season_id)
    
    # Filter to ADMITTED candidates only
    admitted_decisions = [
        d for d in admission_decisions
        if d.outcome.value == "ADMIT"
    ]
    
    if not admitted_decisions:
        raise ValueError(f"No admitted candidates found for season {season_id}")
    
    # Create export ID
    timestamp = _utc_now_iso()
    export_id = _generate_export_id(season_id, timestamp)
    
    # Create candidate export records
    candidate_records: List[dict] = []
    for i, decision in enumerate(admitted_decisions, 1):
        record = _create_candidate_export_record(
            candidate_identity=decision.candidate_identity,
            admission_decision=decision,
            export_rank=i,
        )
        candidate_records.append(record)
    
    # Create portfolio candidate set
    candidate_set = PortfolioCandidateSetV1(
        schema_version="1.0",
        season_id=season_id,
        hard_boundary=season.hard_boundary,
        created_at=timestamp,
        created_by=request.actor,
        admitted=candidate_records,
        rejected=[],
        hold=[],
    )
    
    # Create export evidence
    evidence = _create_export_evidence(
        season_id=season_id,
        export_id=export_id,
        candidate_count=len(candidate_records),
        actor=request.actor,
    )
    
    # Write export artifact
    exports_root = get_exports_root()
    export_dir = exports_root / "candidate_sets" / export_id
    export_dir.mkdir(parents=True, exist_ok=True)
    
    artifact_path = export_dir / "portfolio_candidate_set.json"
    write_json_atomic(artifact_path, candidate_set.model_dump())
    
    # Write evidence file
    evidence_path = export_dir / "export_evidence.json"
    write_json_atomic(evidence_path, evidence)
    
    # Write export record to database
    db = SupervisorDB(get_default_db_path())
    with db._connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            # Check if export already exists
            cursor = conn.execute("""
                SELECT 1 FROM season_exports
                WHERE season_id = ? AND export_id = ?
            """, (season_id, export_id))
            
            if cursor.fetchone() is None:
                # Insert new export record
                conn.execute("""
                    INSERT INTO season_exports (
                        season_id, export_id, export_type,
                        candidate_count, artifact_path, evidence_json,
                        exported_at, exported_by
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    season_id,
                    export_id,
                    "portfolio_candidate_set",
                    len(candidate_records),
                    str(artifact_path),
                    json.dumps(evidence),
                    timestamp,
                    request.actor,
                ))
            
            conn.commit()
        except Exception:
            conn.rollback()
            raise
    
    # Update season state to ARCHIVED if currently DECIDING
    if season.state == "DECIDING":
        with db._connect() as conn:
            conn.execute("""
                UPDATE seasons
                SET state = 'ARCHIVED', updated_at = ?
                WHERE season_id = ? AND state = 'DECIDING'
            """, (now_iso(), season_id))
    
    return SeasonExportCandidatesResponse(
        season_id=season_id,
        export_id=export_id,
        candidate_count=len(candidate_records),
        artifact_path=str(artifact_path),
        evidence=evidence,
        generated_at=timestamp,
    )


def get_season_exports(season_id: str) -> List[Dict[str, Any]]:
    """
    Get export records for a season.
    """
    db = SupervisorDB(get_default_db_path())
    with db._connect() as conn:
        cursor = conn.execute("""
            SELECT 
                season_id, export_id, export_type,
                candidate_count, artifact_path, evidence_json,
                exported_at, exported_by
            FROM season_exports
            WHERE season_id = ?
            ORDER BY exported_at DESC
        """, (season_id,))
        
        rows = cursor.fetchall()
    
    exports = []
    for row in rows:
        # Parse evidence JSON
        evidence_data = json.loads(row["evidence_json"]) if row["evidence_json"] else {}
        
        exports.append({
            "season_id": row["season_id"],
            "export_id": row["export_id"],
            "export_type": row["export_type"],
            "candidate_count": row["candidate_count"],
            "artifact_path": row["artifact_path"],
            "evidence": evidence_data,
            "exported_at": row["exported_at"],
            "exported_by": row["exported_by"],
        })
    
    return exports