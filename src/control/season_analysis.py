"""
Phase P2-B: Season Viewer / Analysis Aggregator.

Contract:
- Read-only analysis of season jobs
- Aggregates candidate information from job artifacts
- Generates candidate list with research metrics
- No mutation of database or files
- Deterministic ordering
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, List, Dict

from contracts.season import (
    SeasonAnalysisResponse,
    SeasonCandidate,
    CandidateIdentity,
    CandidateSource,
)
from control.seasons_repo import get_season, get_season_jobs
from control.reporting.io import read_job_artifact


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _extract_candidate_from_job_artifact(job_id: str, artifact_data: dict) -> Optional[SeasonCandidate]:
    """
    Extract candidate information from job artifact.
    
    Expected artifact structure (from winners.json or similar):
    {
        "candidates": [
            {
                "candidate_id": "candidate_001",
                "strategy_id": "sma_cross_v1",
                "params": {...},
                "score": 1.5,
                "rank": 1,
                ...
            }
        ]
    }
    """
    # Try to find candidates in various possible locations
    candidates = artifact_data.get("candidates", [])
    if not candidates:
        # Try winners list
        candidates = artifact_data.get("winners", [])
    if not candidates:
        # Try topk list
        candidates = artifact_data.get("topk", [])
    
    if not candidates or not isinstance(candidates, list):
        return None
    
    # For now, take the first candidate (highest scoring)
    if not candidates:
        return None
    
    candidate_data = candidates[0]
    if not isinstance(candidate_data, dict):
        return None
    
    # Extract candidate identity
    candidate_id = candidate_data.get("candidate_id")
    if not candidate_id:
        # Try to construct from job_id + rank
        rank = candidate_data.get("rank", 1)
        candidate_id = f"{job_id}:rank:{rank}"
    
    # Create candidate identity
    identity = CandidateIdentity(
        candidate_id=candidate_id,
        display_name=candidate_data.get("display_name", candidate_id),
        rank=candidate_data.get("rank", 1),
    )
    
    # Extract research metrics
    research_metrics = {}
    for key in ["score", "sharpe", "cagr", "mdd", "win_rate", "profit_factor"]:
        if key in candidate_data:
            research_metrics[key] = candidate_data[key]
    
    # Extract source information
    source = CandidateSource(
        job_id=job_id,
        batch_id=candidate_data.get("batch_id"),
        artifact_type="winners.json",
        extracted_at=_utc_now_iso(),
    )
    
    return SeasonCandidate(
        identity=identity,
        strategy_id=candidate_data.get("strategy_id", "unknown"),
        param_hash=candidate_data.get("param_hash", ""),
        research_metrics=research_metrics,
        source=source,
        tags=candidate_data.get("tags", []),
        metadata=candidate_data.get("metadata", {}),
    )


def analyze_season_jobs(season_id: str) -> SeasonAnalysisResponse:
    """
    Analyze all jobs attached to a season and aggregate candidate information.
    
    Contract:
    - Read-only: only reads job artifacts, no writes
    - Deterministic: candidates sorted by score descending, then by candidate_id
    - Returns SeasonAnalysisResponse with aggregated candidates
    - Missing/invalid artifacts are skipped (not errors)
    """
    # Get season and attached job IDs
    season, job_ids = get_season(season_id)
    if season is None:
        raise ValueError(f"Season {season_id} not found")
    
    candidates: List[SeasonCandidate] = []
    skipped_jobs: List[str] = []
    
    for job_id in job_ids:
        # Try to read job artifacts
        # First try winners.json (common artifact for research results)
        artifact_data = read_job_artifact(job_id, "winners.json")
        if artifact_data is None:
            # Try strategy_report_v1.json
            artifact_data = read_job_artifact(job_id, "strategy_report_v1.json")
        
        if artifact_data is None:
            skipped_jobs.append(job_id)
            continue
        
        # Extract candidate from artifact
        candidate = _extract_candidate_from_job_artifact(job_id, artifact_data)
        if candidate is None:
            skipped_jobs.append(job_id)
            continue
        
        candidates.append(candidate)
    
    # Sort candidates by score (descending), then by candidate_id
    def sort_key(candidate: SeasonCandidate) -> tuple:
        score = candidate.research_metrics.get("score", 0.0)
        # Use negative score for descending order
        return (-float(score), candidate.identity.candidate_id)
    
    sorted_candidates = sorted(candidates, key=sort_key)
    
    return SeasonAnalysisResponse(
        season_id=season_id,
        season_state=season.state,
        total_jobs=len(job_ids),
        valid_candidates=len(sorted_candidates),
        skipped_jobs=skipped_jobs,
        candidates=sorted_candidates,
        generated_at=_utc_now_iso(),
        deterministic_order="score desc, candidate_id asc",
    )


def analyze_season(season_id: str, request: Any) -> SeasonAnalysisResponse:
    """
    Analyze season (P2-B API endpoint).
    
    Contract:
    - Season must be FROZEN (enforced by API)
    - Returns aggregated candidate analysis
    """
    # For now, just call analyze_season_jobs
    # The request parameter is ignored for now
    return analyze_season_jobs(season_id)


def get_season_candidate_count(season_id: str) -> int:
    """
    Get count of valid candidates in a season.
    
    Used for UI to enable/disable analysis drawer.
    """
    try:
        response = analyze_season_jobs(season_id)
        return response.valid_candidates
    except Exception:
        return 0