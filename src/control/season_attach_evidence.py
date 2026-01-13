"""
Season attachment evidence writer for P2-A: Season SSOT + Boundary Validator.

Writes canonical evidence files for both accepted and rejected attach attempts.
"""

import json
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional, List

from contracts.season import (
    SeasonRecord,
    SeasonAttachResponse,
    BoundaryMismatchItem,
    BoundaryMismatchErrorPayload,
)
from control.job_boundary_reader import JobBoundary


class SeasonAttachEvidenceWriter:
    """
    Writes evidence files for season attachment attempts.
    
    Evidence is written to:
    - outputs/_dp_evidence/phase_p2a_season_ssot_validator/attach_attempts/
    
    Each attempt creates a JSON file with:
    - timestamp
    - season_id, job_id
    - validation result (ACCEPTED/REJECTED)
    - boundary mismatches (if any)
    - season boundary
    - job boundary
    - actor
    - evidence_path (for accepted attachments)
    """
    
    def __init__(self, outputs_root: Optional[Path] = None):
        """
        Initialize evidence writer.
        
        Args:
            outputs_root: Root outputs directory (defaults to "outputs")
        """
        if outputs_root is None:
            outputs_root = Path("outputs")
        self.outputs_root = outputs_root
        self.evidence_dir = outputs_root / "_dp_evidence" / "phase_p2a_season_ssot_validator" / "attach_attempts"
        self.evidence_dir.mkdir(parents=True, exist_ok=True)
    
    def write_accepted_evidence(
        self,
        season: SeasonRecord,
        job_boundary: JobBoundary,
        job_id: str,
        actor: str,
        attach_response: SeasonAttachResponse,
    ) -> Path:
        """
        Write evidence for an accepted attachment.
        
        Args:
            season: Season record
            job_boundary: Job boundary
            job_id: Job ID
            actor: Who performed the attachment
            attach_response: Attachment response
        
        Returns:
            Path to the evidence file
        """
        timestamp = datetime.now(timezone.utc).isoformat()
        evidence_id = f"{season.season_id}_{job_id}_{timestamp.replace(':', '-').replace('.', '-')}"
        evidence_path = self.evidence_dir / f"{evidence_id}_ACCEPTED.json"
        
        evidence = {
            "timestamp": timestamp,
            "evidence_id": evidence_id,
            "result": "ACCEPTED",
            "season_id": season.season_id,
            "job_id": job_id,
            "actor": actor,
            "season_boundary": {
                "universe_fingerprint": season.hard_boundary.universe_fingerprint,
                "timeframes_fingerprint": season.hard_boundary.timeframes_fingerprint,
                "dataset_snapshot_id": season.hard_boundary.dataset_snapshot_id,
                "engine_constitution_id": season.hard_boundary.engine_constitution_id,
            },
            "job_boundary": {
                "universe_fingerprint": job_boundary.universe_fingerprint,
                "timeframes_fingerprint": job_boundary.timeframes_fingerprint,
                "dataset_snapshot_id": job_boundary.dataset_snapshot_id,
                "engine_constitution_id": job_boundary.engine_constitution_id,
            },
            "boundary_match": True,
            "mismatches": [],
            "season_state": season.state,
            "attach_response": attach_response.model_dump(),
            "evidence_path": str(evidence_path),
        }
        
        with open(evidence_path, "w") as f:
            json.dump(evidence, f, indent=2)
        
        return evidence_path
    
    def write_rejected_evidence(
        self,
        season: SeasonRecord,
        job_boundary: JobBoundary,
        job_id: str,
        actor: str,
        mismatches: List[BoundaryMismatchItem],
        error_message: Optional[str] = None,
    ) -> Path:
        """
        Write evidence for a rejected attachment.
        
        Args:
            season: Season record
            job_boundary: Job boundary
            job_id: Job ID
            actor: Who attempted the attachment
            mismatches: List of boundary mismatches
            error_message: Optional error message
        
        Returns:
            Path to the evidence file
        """
        timestamp = datetime.now(timezone.utc).isoformat()
        evidence_id = f"{season.season_id}_{job_id}_{timestamp.replace(':', '-').replace('.', '-')}"
        evidence_path = self.evidence_dir / f"{evidence_id}_REJECTED.json"
        
        evidence = {
            "timestamp": timestamp,
            "evidence_id": evidence_id,
            "result": "REJECTED",
            "season_id": season.season_id,
            "job_id": job_id,
            "actor": actor,
            "season_boundary": {
                "universe_fingerprint": season.hard_boundary.universe_fingerprint,
                "timeframes_fingerprint": season.hard_boundary.timeframes_fingerprint,
                "dataset_snapshot_id": season.hard_boundary.dataset_snapshot_id,
                "engine_constitution_id": season.hard_boundary.engine_constitution_id,
            },
            "job_boundary": {
                "universe_fingerprint": job_boundary.universe_fingerprint,
                "timeframes_fingerprint": job_boundary.timeframes_fingerprint,
                "dataset_snapshot_id": job_boundary.dataset_snapshot_id,
                "engine_constitution_id": job_boundary.engine_constitution_id,
            },
            "boundary_match": False,
            "mismatches": [m.model_dump() for m in mismatches],
            "season_state": season.state,
            "error_message": error_message,
            "evidence_path": str(evidence_path),
        }
        
        with open(evidence_path, "w") as f:
            json.dump(evidence, f, indent=2)
        
        return evidence_path
    
    def write_state_transition_evidence(
        self,
        season_id: str,
        from_state: str,
        to_state: str,
        actor: str,
        reason: Optional[str] = None,
    ) -> Path:
        """
        Write evidence for a season state transition.
        
        Args:
            season_id: Season ID
            from_state: Previous state
            to_state: New state
            actor: Who performed the transition
            reason: Optional reason for transition
        
        Returns:
            Path to the evidence file
        """
        timestamp = datetime.now(timezone.utc).isoformat()
        evidence_id = f"{season_id}_{timestamp.replace(':', '-').replace('.', '-')}"
        evidence_path = self.evidence_dir / f"{evidence_id}_STATE_{from_state}_TO_{to_state}.json"
        
        evidence = {
            "timestamp": timestamp,
            "evidence_id": evidence_id,
            "type": "SEASON_STATE_TRANSITION",
            "season_id": season_id,
            "from_state": from_state,
            "to_state": to_state,
            "actor": actor,
            "reason": reason,
            "evidence_path": str(evidence_path),
        }
        
        with open(evidence_path, "w") as f:
            json.dump(evidence, f, indent=2)
        
        return evidence_path


def write_attach_evidence(
    season: SeasonRecord,
    job_boundary: JobBoundary,
    job_id: str,
    actor: str,
    is_accepted: bool,
    attach_response: Optional[SeasonAttachResponse] = None,
    mismatches: Optional[List[BoundaryMismatchItem]] = None,
    error_message: Optional[str] = None,
    outputs_root: Optional[Path] = None,
) -> Path:
    """
    High-level function to write attachment evidence.
    
    Args:
        season: Season record
        job_boundary: Job boundary
        job_id: Job ID
        actor: Who performed the attachment
        is_accepted: Whether attachment was accepted
        attach_response: Attachment response (if accepted)
        mismatches: Boundary mismatches (if rejected)
        error_message: Error message (if rejected)
        outputs_root: Root outputs directory
    
    Returns:
        Path to the evidence file
    """
    writer = SeasonAttachEvidenceWriter(outputs_root)
    
    if is_accepted and attach_response:
        return writer.write_accepted_evidence(
            season=season,
            job_boundary=job_boundary,
            job_id=job_id,
            actor=actor,
            attach_response=attach_response,
        )
    else:
        return writer.write_rejected_evidence(
            season=season,
            job_boundary=job_boundary,
            job_id=job_id,
            actor=actor,
            mismatches=mismatches or [],
            error_message=error_message,
        )


def get_evidence_dir(outputs_root: Optional[Path] = None) -> Path:
    """
    Get the evidence directory for season attachments.
    
    Args:
        outputs_root: Root outputs directory
    
    Returns:
        Path to evidence directory
    """
    if outputs_root is None:
        outputs_root = Path("outputs")
    return outputs_root / "_dp_evidence" / "phase_p2a_season_ssot_validator" / "attach_attempts"