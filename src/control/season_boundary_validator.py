"""
Season boundary validator for P2-A: Season SSOT + Boundary Validator.

Implements hard boundary validation that blocks job attachment unless boundaries match.
"""

from typing import List, Tuple, Optional
from pathlib import Path

from contracts.season import (
    SeasonHardBoundary,
    SeasonRecord,
    BoundaryMismatchItem,
    BoundaryMismatchErrorPayload,
)
from control.seasons_repo import get_season
from control.job_boundary_reader import (
    JobBoundary,
    extract_job_boundary,
    JobBoundaryExtractionError,
)


class SeasonBoundaryValidator:
    """
    Validates that a job's boundaries match a season's hard boundaries.
    
    Hard boundaries that must match exactly:
    1. universe_fingerprint
    2. timeframes_fingerprint  
    3. dataset_snapshot_id
    4. engine_constitution_id
    """
    
    @staticmethod
    def validate(
        season: SeasonRecord,
        job_boundary: JobBoundary,
    ) -> Tuple[bool, List[BoundaryMismatchItem]]:
        """
        Validate if job boundary matches season hard boundary.
        
        Args:
            season: Season record with hard boundary
            job_boundary: Job boundary extracted from job artifacts
        
        Returns:
            Tuple of (is_valid, list_of_mismatches)
        """
        mismatches: List[BoundaryMismatchItem] = []
        
        # Check each boundary field
        if season.hard_boundary.universe_fingerprint != job_boundary.universe_fingerprint:
            mismatches.append(BoundaryMismatchItem(
                field="universe_fingerprint",
                season_value=season.hard_boundary.universe_fingerprint,
                job_value=job_boundary.universe_fingerprint,
            ))
        
        if season.hard_boundary.timeframes_fingerprint != job_boundary.timeframes_fingerprint:
            mismatches.append(BoundaryMismatchItem(
                field="timeframes_fingerprint",
                season_value=season.hard_boundary.timeframes_fingerprint,
                job_value=job_boundary.timeframes_fingerprint,
            ))
        
        if season.hard_boundary.dataset_snapshot_id != job_boundary.dataset_snapshot_id:
            mismatches.append(BoundaryMismatchItem(
                field="dataset_snapshot_id",
                season_value=season.hard_boundary.dataset_snapshot_id,
                job_value=job_boundary.dataset_snapshot_id,
            ))
        
        if season.hard_boundary.engine_constitution_id != job_boundary.engine_constitution_id:
            mismatches.append(BoundaryMismatchItem(
                field="engine_constitution_id",
                season_value=season.hard_boundary.engine_constitution_id,
                job_value=job_boundary.engine_constitution_id,
            ))
        
        return len(mismatches) == 0, mismatches
    
    @classmethod
    def validate_season_job(
        cls,
        season_id: str,
        job_id: str,
        outputs_root: Optional[Path] = None,
    ) -> Tuple[bool, List[BoundaryMismatchItem], Optional[str]]:
        """
        Validate if a job can be attached to a season.
        
        Args:
            season_id: Season ID
            job_id: Job ID
            outputs_root: Optional outputs root path (defaults to "outputs")
        
        Returns:
            Tuple of (is_valid, mismatches, error_message)
            - is_valid: True if job can be attached
            - mismatches: List of boundary mismatches if not valid
            - error_message: Error message if validation failed for other reasons
        """
        if outputs_root is None:
            outputs_root = Path("outputs")
        
        # Get season
        season, _ = get_season(season_id)
        if season is None:
            return False, [], f"Season {season_id} not found"
        
        # Check season state - only OPEN seasons can accept attachments
        if season.state != "OPEN":
            return False, [], f"Season {season_id} is in state {season.state}, must be OPEN to attach jobs"
        
        # Extract job boundary
        try:
            job_boundary = extract_job_boundary(job_id, outputs_root)
        except JobBoundaryExtractionError as e:
            return False, [], f"Failed to extract job boundary: {e}"
        except Exception as e:
            return False, [], f"Unexpected error extracting job boundary: {e}"
        
        # Validate boundary match
        is_valid, mismatches = cls.validate(season, job_boundary)
        
        return is_valid, mismatches, None
    
    @classmethod
    def create_mismatch_payload(
        cls,
        season_id: str,
        job_id: str,
        mismatches: List[BoundaryMismatchItem],
    ) -> BoundaryMismatchErrorPayload:
        """
        Create a boundary mismatch error payload for API responses.
        
        Args:
            season_id: Season ID
            job_id: Job ID
            mismatches: List of boundary mismatches
        
        Returns:
            BoundaryMismatchErrorPayload for 409 Conflict responses
        """
        return BoundaryMismatchErrorPayload(
            season_id=season_id,
            job_id=job_id,
            mismatches=mismatches,
        )


def validate_and_attach_job(
    season_id: str,
    job_id: str,
    actor: str,
    outputs_root: Optional[Path] = None,
) -> Tuple[bool, List[BoundaryMismatchItem], Optional[str]]:
    """
    High-level function to validate and attach a job to a season.
    
    This performs the full validation flow:
    1. Check season exists and is OPEN
    2. Extract job boundary from artifacts
    3. Validate boundary match
    4. Return validation result
    
    Note: This does NOT perform the actual attachment - that should be done
    by the caller after successful validation.
    
    Args:
        season_id: Season ID
        job_id: Job ID
        actor: Who is attempting the attachment
        outputs_root: Optional outputs root path
    
    Returns:
        Tuple of (is_valid, mismatches, error_message)
    """
    return SeasonBoundaryValidator.validate_season_job(
        season_id=season_id,
        job_id=job_id,
        outputs_root=outputs_root,
    )