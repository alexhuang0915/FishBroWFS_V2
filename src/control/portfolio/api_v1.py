"""
Portfolio Build API v1 endpoints for Phase D.

Implements:
- POST /api/v1/portfolios/build
- GET /api/v1/portfolios/{portfolio_id}
- GET /api/v1/portfolios/{portfolio_id}/artifacts
- GET /api/v1/portfolios/{portfolio_id}/artifacts/{filename}
- GET /api/v1/portfolios/{portfolio_id}/reveal_admission_path
"""

from __future__ import annotations

import hashlib
import json
import mimetypes
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, validator

from src.control.supervisor import submit as supervisor_submit


# -----------------------------------------------------------------------------
# Request/Response Models
# -----------------------------------------------------------------------------

class GovernanceParamsOverrides(BaseModel):
    """Optional governance parameter overrides."""
    max_pairwise_correlation: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    portfolio_risk_budget_max: Optional[float] = Field(default=None, ge=0.0)


class PortfolioBuildRequestV1(BaseModel):
    """Request for POST /api/v1/portfolios/build."""
    season: str = Field(..., description="Season identifier (e.g., '2026Q1')")
    timeframe: str = Field(..., description="Timeframe (e.g., '60m')")
    candidate_run_ids: List[str] = Field(..., description="List of candidate run IDs to include")
    governance_params_overrides: Optional[GovernanceParamsOverrides] = Field(
        default=None, description="Optional governance parameter overrides"
    )

    @validator('candidate_run_ids')
    def candidate_run_ids_non_empty(cls, v):
        if not v:
            raise ValueError('candidate_run_ids must be non-empty')
        return v


class PortfolioBuildResponseV1(BaseModel):
    """Response for POST /api/v1/portfolios/build."""
    job_id: str = Field(..., description="Job ID for the portfolio build")
    portfolio_id: Optional[str] = Field(
        default=None, description="Portfolio ID (may be null initially)"
    )
    status: str = Field(..., description="Job status (PENDING, RUNNING, etc.)")


class PortfolioResponseV1(BaseModel):
    """Response for GET /api/v1/portfolios/{portfolio_id}."""
    portfolio_id: str = Field(..., description="Portfolio ID")
    created_at: Optional[str] = Field(default=None, description="Creation timestamp")
    admission_report_v1_url: str = Field(
        ..., description="URL to portfolio report v1"
    )
    admission_artifacts_index_url: str = Field(
        ..., description="URL to portfolio artifacts index"
    )


class ArtifactFile(BaseModel):
    """File entry in artifacts index."""
    filename: str = Field(..., description="Filename (relative path)")
    size_bytes: int = Field(..., description="File size in bytes")
    content_type: str = Field(..., description="MIME type")
    sha256: Optional[str] = Field(default=None, description="SHA256 hash (null if not computed)")
    url: str = Field(..., description="URL to download the file")


class PortfolioArtifactsResponseV1(BaseModel):
    """Response for GET /api/v1/portfolios/{portfolio_id}/artifacts."""
    portfolio_id: str = Field(..., description="Portfolio ID")
    links: Dict[str, Optional[str]] = Field(
        ..., description="Named links to key artifacts"
    )
    files: List[ArtifactFile] = Field(..., description="List of all files")


class RevealAdmissionPathResponse(BaseModel):
    """Response for GET /api/v1/portfolios/{portfolio_id}/reveal_admission_path."""
    approved: bool = Field(..., description="Whether path access is approved")
    path: str = Field(..., description="Absolute path to admission directory")


# -----------------------------------------------------------------------------
# Router
# -----------------------------------------------------------------------------

router = APIRouter(prefix="/api/v1/portfolios", tags=["portfolios"])


# -----------------------------------------------------------------------------
# Helper Functions
# -----------------------------------------------------------------------------

def _get_portfolios_root() -> Path:
    """Return the root directory for portfolio evidence bundles.
    
    LOCKED: outputs/portfolios/
    """
    return Path("outputs/portfolios")


def _get_portfolio_admission_dir(portfolio_id: str) -> Path:
    """Return the admission directory for a portfolio, ensuring containment."""
    root = _get_portfolios_root()
    admission_dir = root / portfolio_id / "admission"
    
    # Security: ensure admission_dir is within root (no path traversal)
    try:
        admission_dir.resolve().relative_to(root.resolve())
    except ValueError:
        raise HTTPException(status_code=403, detail="Portfolio ID contains path traversal")
    
    return admission_dir


def _compute_portfolio_id(candidate_run_ids: List[str], season: str) -> str:
    """Compute deterministic portfolio ID from candidate run IDs and season."""
    sorted_ids = sorted(candidate_run_ids)
    id_string = f"{season}:{','.join(sorted_ids)}"
    hash_digest = hashlib.sha256(id_string.encode()).hexdigest()[:12]
    return f"portfolio_{season}_{hash_digest}"


def _build_portfolio_job_params(
    request: PortfolioBuildRequestV1,
    portfolio_id: str
) -> dict:
    """Build parameters for BUILD_PORTFOLIO_V2 job."""
    
    params = {
        "season": request.season,
        "timeframe": request.timeframe,
        "candidate_run_ids": request.candidate_run_ids,
        "portfolio_id": portfolio_id,
    }
    
    # Add governance params overrides if present
    if request.governance_params_overrides:
        params["governance_params_overrides"] = (
            request.governance_params_overrides.dict(exclude_none=True)
        )
    
    return params


def _list_admission_artifacts(portfolio_id: str) -> List[ArtifactFile]:
    """List files in the portfolio admission directory."""
    admission_dir = _get_portfolio_admission_dir(portfolio_id)
    if not admission_dir.exists():
        return []
    
    artifacts = []
    for file_path in admission_dir.rglob("*"):
        if file_path.is_file():
            rel_path = file_path.relative_to(admission_dir)
            # Store relative path as filename
            filename = str(rel_path)
            
            # Compute size
            size = file_path.stat().st_size
            
            # Guess content type
            content_type, _ = mimetypes.guess_type(str(file_path))
            if content_type is None:
                content_type = "application/octet-stream"
            
            # Compute SHA256 (optional, can be expensive for large files)
            sha256 = None
            try:
                if size < 10 * 1024 * 1024:  # 10 MB limit
                    with open(file_path, "rb") as f:
                        sha256 = hashlib.sha256(f.read()).hexdigest()
            except Exception:
                pass
            
            artifacts.append(ArtifactFile(
                filename=filename,
                size_bytes=size,
                content_type=content_type,
                sha256=sha256,
                url=f"/api/v1/portfolios/{portfolio_id}/artifacts/{filename}"
            ))
    
    return artifacts


def _build_portfolio_links(portfolio_id: str) -> Dict[str, Optional[str]]:
    """Build named links for portfolio artifacts."""
    admission_dir = _get_portfolio_admission_dir(portfolio_id)
    
    links = {
        "portfolio_report_v1_url": f"/api/v1/reports/portfolio/{portfolio_id}",
        "admission_decision_url": None,
        "correlation_matrix_url": None,
        "correlation_violations_url": None,
        "risk_budget_snapshot_url": None,
        "reveal_admission_path_url": f"/api/v1/portfolios/{portfolio_id}/reveal_admission_path",
    }
    
    # Check for specific files
    if (admission_dir / "admission_decision.json").exists():
        links["admission_decision_url"] = f"/api/v1/portfolios/{portfolio_id}/artifacts/admission_decision.json"
    
    if (admission_dir / "correlation_matrix.json").exists():
        links["correlation_matrix_url"] = f"/api/v1/portfolios/{portfolio_id}/artifacts/correlation_matrix.json"
    
    if (admission_dir / "correlation_violations.json").exists():
        links["correlation_violations_url"] = f"/api/v1/portfolios/{portfolio_id}/artifacts/correlation_violations.json"
    
    if (admission_dir / "risk_budget_snapshot.json").exists():
        links["risk_budget_snapshot_url"] = f"/api/v1/portfolios/{portfolio_id}/artifacts/risk_budget_snapshot.json"
    
    return links


# -----------------------------------------------------------------------------
# API Endpoints
# -----------------------------------------------------------------------------

@router.post("/build", response_model=PortfolioBuildResponseV1)
async def post_portfolio_build(request: PortfolioBuildRequestV1) -> PortfolioBuildResponseV1:
    """
    Submit a portfolio build request.
    
    Creates a BUILD_PORTFOLIO_V2 job and returns job_id immediately.
    The portfolio_id may be null initially and will be discoverable from job evidence.
    """
    # Compute deterministic portfolio ID
    portfolio_id = _compute_portfolio_id(request.candidate_run_ids, request.season)
    
    # Build job parameters
    params = _build_portfolio_job_params(request, portfolio_id)
    
    # Submit to supervisor (jobs_v2.db)
    job_id = supervisor_submit(
        job_type="BUILD_PORTFOLIO_V2",
        params=params,
        metadata={
            "season": request.season,
            "timeframe": request.timeframe,
            "portfolio_id": portfolio_id,
            "source": "portfolio_build_api_v1"
        }
    )
    
    return PortfolioBuildResponseV1(
        job_id=job_id,
        portfolio_id=portfolio_id,
        status="PENDING"
    )


@router.get("/{portfolio_id}", response_model=PortfolioResponseV1)
async def get_portfolio(portfolio_id: str) -> PortfolioResponseV1:
    """
    Get basic portfolio metadata.
    
    Returns portfolio ID, creation timestamp (if available), and URLs to
    report and artifacts.
    """
    admission_dir = _get_portfolio_admission_dir(portfolio_id)
    
    # Try to get creation time from portfolio_report_v1.json
    created_at = None
    report_path = admission_dir / "portfolio_report_v1.json"
    if report_path.exists():
        try:
            with open(report_path, "r") as f:
                report_data = json.load(f)
                meta = report_data.get("meta", {})
                created_at = meta.get("created_at")
        except Exception:
            pass
    
    return PortfolioResponseV1(
        portfolio_id=portfolio_id,
        created_at=created_at,
        admission_report_v1_url=f"/api/v1/reports/portfolio/{portfolio_id}",
        admission_artifacts_index_url=f"/api/v1/portfolios/{portfolio_id}/artifacts",
    )


@router.get("/{portfolio_id}/artifacts", response_model=PortfolioArtifactsResponseV1)
async def get_portfolio_artifacts(portfolio_id: str) -> PortfolioArtifactsResponseV1:
    """
    Get artifact index for a portfolio admission.
    
    Lists all files under outputs/portfolios/<portfolio_id>/admission/
    with metadata and download URLs.
    """
    # Validate portfolio admission directory exists
    admission_dir = _get_portfolio_admission_dir(portfolio_id)
    if not admission_dir.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Portfolio admission directory not found for {portfolio_id}"
        )
    
    # Build links and list files
    links = _build_portfolio_links(portfolio_id)
    files = _list_admission_artifacts(portfolio_id)
    
    return PortfolioArtifactsResponseV1(
        portfolio_id=portfolio_id,
        links=links,
        files=files,
    )


@router.get("/{portfolio_id}/artifacts/{filename}")
async def get_portfolio_artifact_file(portfolio_id: str, filename: str):
    """
    Serve a single artifact file from the portfolio admission directory.
    
    Security:
    - filename must be a simple basename (no slashes, no path traversal)
    - Must enforce containment within outputs/portfolios/<portfolio_id>/admission/
    - Returns 404 if file not found, 403 if path traversal detected.
    """
    # Validate filename does not contain slashes or path traversal attempts
    if "/" in filename or "\\" in filename or filename in (".", ".."):
        raise HTTPException(status_code=400, detail="Invalid filename")
    
    admission_dir = _get_portfolio_admission_dir(portfolio_id)
    file_path = admission_dir / filename
    
    # Ensure file_path is within admission_dir (double-check containment)
    try:
        file_path.resolve().relative_to(admission_dir.resolve())
    except ValueError:
        raise HTTPException(status_code=403, detail="Path traversal detected")
    
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    
    # Determine content type
    content_type, _ = mimetypes.guess_type(str(file_path))
    if content_type is None:
        content_type = "application/octet-stream"
    
    # For text/plain or JSON, we can return as plain text; for binary, use FileResponse
    from fastapi.responses import FileResponse
    return FileResponse(
        path=file_path,
        media_type=content_type,
        filename=filename,
    )


@router.get("/{portfolio_id}/reveal_admission_path", response_model=RevealAdmissionPathResponse)
async def reveal_portfolio_admission_path(portfolio_id: str) -> RevealAdmissionPathResponse:
    """
    Return the absolute path to the portfolio admission directory after containment check.
    
    Security:
    - Must ensure portfolio_id does not contain path traversal.
    - Must ensure the resolved path is within the locked evidence root (outputs/portfolios/).
    - Returns 404 if admission directory does not exist.
    """
    admission_dir = _get_portfolio_admission_dir(portfolio_id)
    
    if not admission_dir.exists():
        raise HTTPException(status_code=404, detail="Portfolio admission directory not found")
    
    # Already validated containment in _get_portfolio_admission_dir
    return RevealAdmissionPathResponse(
        approved=True,
        path=str(admission_dir.resolve()),
    )