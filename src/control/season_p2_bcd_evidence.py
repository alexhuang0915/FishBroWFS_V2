"""
Phase P2-B/C/D: Evidence writers for Season Viewer, Admission Decisions, and Export.

Writes canonical evidence files for:
- Season analysis (P2-B)
- Admission decisions (P2-C) 
- Portfolio candidate set exports (P2-D)
"""

import json
from pathlib import Path
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from contracts.season import (
    SeasonAnalysisResponse,
    SeasonAdmissionResponse,
    SeasonExportCandidatesResponse,
    AdmissionDecision,
    PortfolioCandidateSetV1,
)


class SeasonP2BCDEvidenceWriter:
    """
    Writes evidence files for P2-B/C/D operations.
    
    Evidence is written to:
    - outputs/_dp_evidence/phase_p2_bcd/
    
    Organized by subdirectories:
    - analysis/: Season analysis evidence
    - admissions/: Admission decisions evidence  
    - exports/: Portfolio candidate set exports evidence
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
        self.base_dir = outputs_root / "_dp_evidence" / "phase_p2_bcd"
        self.analysis_dir = self.base_dir / "analysis"
        self.admissions_dir = self.base_dir / "admissions"
        self.exports_dir = self.base_dir / "exports"
        
        # Create directories
        self.analysis_dir.mkdir(parents=True, exist_ok=True)
        self.admissions_dir.mkdir(parents=True, exist_ok=True)
        self.exports_dir.mkdir(parents=True, exist_ok=True)
    
    def write_analysis_evidence(
        self,
        analysis_response: SeasonAnalysisResponse,
        actor: str,
    ) -> Path:
        """
        Write evidence for season analysis (P2-B).
        
        Args:
            analysis_response: Season analysis response
            actor: Who performed the analysis
            
        Returns:
            Path to the evidence file
        """
        timestamp = datetime.now(timezone.utc).isoformat()
        evidence_id = f"{analysis_response.season_id}_{timestamp.replace(':', '-').replace('.', '-')}"
        evidence_path = self.analysis_dir / f"{evidence_id}_ANALYSIS.json"
        
        evidence = {
            "timestamp": timestamp,
            "evidence_id": evidence_id,
            "type": "SEASON_ANALYSIS",
            "season_id": analysis_response.season_id,
            "season_state": analysis_response.season_state,
            "total_jobs": analysis_response.total_jobs,
            "valid_candidates": analysis_response.valid_candidates,
            "skipped_jobs": analysis_response.skipped_jobs,
            "candidate_count": len(analysis_response.candidates),
            "actor": actor,
            "generated_at": analysis_response.generated_at,
            "deterministic_order": analysis_response.deterministic_order,
            # Include summary of candidates (not full list to keep file size manageable)
            "candidates_summary": [
                {
                    "candidate_id": c.identity.candidate_id,
                    "strategy_id": c.strategy_id,
                    "score": c.research_metrics.get("score"),
                    "rank": c.identity.rank,
                }
                for c in analysis_response.candidates[:10]  # First 10 only
            ],
            "evidence_path": str(evidence_path),
        }
        
        with open(evidence_path, "w") as f:
            json.dump(evidence, f, indent=2)
        
        return evidence_path
    
    def write_admission_evidence(
        self,
        admission_response: SeasonAdmissionResponse,
        actor: str,
    ) -> Path:
        """
        Write evidence for admission decisions (P2-C).
        
        Args:
            admission_response: Admission decisions response
            actor: Who performed the admission decisions
            
        Returns:
            Path to the evidence file
        """
        timestamp = datetime.now(timezone.utc).isoformat()
        evidence_id = f"{admission_response.season_id}_{timestamp.replace(':', '-').replace('.', '-')}"
        evidence_path = self.admissions_dir / f"{evidence_id}_ADMISSIONS.json"
        
        # Summarize decisions
        decisions_summary = []
        for decision in admission_response.decisions[:20]:  # First 20 only
            decisions_summary.append({
                "candidate_identity": decision.candidate_identity,
                "outcome": decision.outcome.value,
                "reason": decision.decision_reason,
                "decided_at": decision.decided_at,
            })
        
        evidence = {
            "timestamp": timestamp,
            "evidence_id": evidence_id,
            "type": "SEASON_ADMISSIONS",
            "season_id": admission_response.season_id,
            "total_candidates": admission_response.total_candidates,
            "admitted_count": admission_response.admitted_count,
            "rejected_count": admission_response.rejected_count,
            "held_count": admission_response.held_count,
            "actor": actor,
            "generated_at": admission_response.generated_at,
            "decisions_count": len(admission_response.decisions),
            "decisions_summary": decisions_summary,
            "evidence_path": str(evidence_path),
        }
        
        with open(evidence_path, "w") as f:
            json.dump(evidence, f, indent=2)
        
        return evidence_path
    
    def write_export_evidence(
        self,
        export_response: SeasonExportCandidatesResponse,
        actor: str,
    ) -> Path:
        """
        Write evidence for portfolio candidate set export (P2-D).
        
        Args:
            export_response: Export response
            actor: Who performed the export
            
        Returns:
            Path to the evidence file
        """
        timestamp = datetime.now(timezone.utc).isoformat()
        evidence_id = f"{export_response.season_id}_{export_response.export_id}"
        evidence_path = self.exports_dir / f"{evidence_id}_EXPORT.json"
        
        evidence = {
            "timestamp": timestamp,
            "evidence_id": evidence_id,
            "type": "PORTFOLIO_CANDIDATE_SET_EXPORT",
            "season_id": export_response.season_id,
            "export_id": export_response.export_id,
            "candidate_count": export_response.candidate_count,
            "artifact_path": export_response.artifact_path,
            "actor": actor,
            "generated_at": export_response.generated_at,
            "evidence": export_response.evidence if export_response.evidence else {},
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
        transition_type: str,
        reason: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Path:
        """
        Write evidence for season state transitions during P2-B/C/D.
        
        Args:
            season_id: Season ID
            from_state: Previous state
            to_state: New state
            actor: Who performed the transition
            transition_type: Type of transition (e.g., "ANALYSIS_TO_ADMISSION", "ADMISSION_TO_EXPORT")
            reason: Optional reason for transition
            metadata: Optional additional metadata
            
        Returns:
            Path to the evidence file
        """
        timestamp = datetime.now(timezone.utc).isoformat()
        evidence_id = f"{season_id}_{timestamp.replace(':', '-').replace('.', '-')}"
        evidence_path = self.base_dir / f"{evidence_id}_STATE_{from_state}_TO_{to_state}.json"
        
        evidence = {
            "timestamp": timestamp,
            "evidence_id": evidence_id,
            "type": "SEASON_STATE_TRANSITION_P2_BCD",
            "season_id": season_id,
            "from_state": from_state,
            "to_state": to_state,
            "actor": actor,
            "transition_type": transition_type,
            "reason": reason,
            "metadata": metadata or {},
            "evidence_path": str(evidence_path),
        }
        
        with open(evidence_path, "w") as f:
            json.dump(evidence, f, indent=2)
        
        return evidence_path


# High-level convenience functions
def write_analysis_evidence(
    analysis_response: SeasonAnalysisResponse,
    actor: str,
    outputs_root: Optional[Path] = None,
) -> Path:
    """Write season analysis evidence."""
    writer = SeasonP2BCDEvidenceWriter(outputs_root)
    return writer.write_analysis_evidence(analysis_response, actor)


def write_admission_evidence(
    admission_response: SeasonAdmissionResponse,
    actor: str,
    outputs_root: Optional[Path] = None,
) -> Path:
    """Write admission decisions evidence."""
    writer = SeasonP2BCDEvidenceWriter(outputs_root)
    return writer.write_admission_evidence(admission_response, actor)


def write_export_evidence(
    export_response: SeasonExportCandidatesResponse,
    actor: str,
    outputs_root: Optional[Path] = None,
) -> Path:
    """Write portfolio candidate set export evidence."""
    writer = SeasonP2BCDEvidenceWriter(outputs_root)
    return writer.write_export_evidence(export_response, actor)


def get_evidence_dir(outputs_root: Optional[Path] = None) -> Path:
    """
    Get the evidence directory for P2-B/C/D.
    
    Args:
        outputs_root: Root outputs directory
        
    Returns:
        Path to evidence directory
    """
    if outputs_root is None:
        outputs_root = Path("outputs")
    return outputs_root / "_dp_evidence" / "phase_p2_bcd"