"""
Season repository functions for P2-A: Season SSOT + Boundary Validator.

Provides CRUD operations for seasons and job attachments.
"""

from __future__ import annotations
import sqlite3
import uuid
from pathlib import Path
from typing import Optional, List, Tuple
from datetime import datetime, timezone

from contracts.season import (
    SeasonRecord,
    SeasonCreateRequest,
    SeasonDetailResponse,
    SeasonAttachResponse,
    SeasonAttachRequest,
    BoundaryMismatchItem,
    SeasonState,
    SeasonHardBoundary,
)
from control.supervisor.db import SupervisorDB, get_default_db_path
from control.supervisor.models import now_iso


def new_season_id() -> str:
    """Generate a new season ID."""
    return str(uuid.uuid4())


def create_season(req: SeasonCreateRequest, actor: str) -> SeasonRecord:
    """
    Create a new season.
    
    Args:
        req: Season creation request
        actor: Who is creating the season (e.g., "ui", "api", "cli")
    
    Returns:
        SeasonRecord for the created season
    """
    season_id = new_season_id()
    now = now_iso()
    
    # Create season record
    season = SeasonRecord(
        season_id=season_id,
        label=req.label,
        note=req.note,
        state="DRAFT",
        hard_boundary=req.hard_boundary,
        created_at=now,
        created_by=actor,
        updated_at=now,
    )
    
    # Insert into database
    db = SupervisorDB(get_default_db_path())
    with db._connect() as conn:
        try:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("""
                INSERT INTO seasons (
                    season_id, label, note, state,
                    universe_fingerprint, timeframes_fingerprint,
                    dataset_snapshot_id, engine_constitution_id,
                    created_at, created_by, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                season.season_id,
                season.label,
                season.note,
                season.state,
                season.hard_boundary.universe_fingerprint,
                season.hard_boundary.timeframes_fingerprint,
                season.hard_boundary.dataset_snapshot_id,
                season.hard_boundary.engine_constitution_id,
                season.created_at,
                season.created_by,
                season.updated_at,
            ))
            conn.commit()
        except sqlite3.IntegrityError as e:
            conn.rollback()
            raise ValueError(f"Season already exists: {e}")
        except Exception:
            conn.rollback()
            raise
    
    return season


def list_seasons() -> List[SeasonRecord]:
    """
    List all seasons.
    
    Returns:
        List of SeasonRecord objects
    """
    db = SupervisorDB(get_default_db_path())
    with db._connect() as conn:
        cursor = conn.execute("""
            SELECT 
                season_id, label, note, state,
                universe_fingerprint, timeframes_fingerprint,
                dataset_snapshot_id, engine_constitution_id,
                created_at, created_by, updated_at
            FROM seasons
            ORDER BY created_at DESC
        """)
        rows = cursor.fetchall()
    
    seasons = []
    for row in rows:
        hard_boundary = SeasonHardBoundary(
            universe_fingerprint=row["universe_fingerprint"],
            timeframes_fingerprint=row["timeframes_fingerprint"],
            dataset_snapshot_id=row["dataset_snapshot_id"],
            engine_constitution_id=row["engine_constitution_id"],
        )
        season = SeasonRecord(
            season_id=row["season_id"],
            label=row["label"],
            note=row["note"],
            state=row["state"],
            hard_boundary=hard_boundary,
            created_at=row["created_at"],
            created_by=row["created_by"],
            updated_at=row["updated_at"],
        )
        seasons.append(season)
    
    return seasons


def get_season(season_id: str) -> Tuple[Optional[SeasonRecord], List[str]]:
    """
    Get season details with attached job IDs.
    
    Args:
        season_id: Season ID to retrieve
    
    Returns:
        Tuple of (SeasonRecord or None, list of attached job IDs)
    """
    db = SupervisorDB(get_default_db_path())
    with db._connect() as conn:
        # Get season
        cursor = conn.execute("""
            SELECT 
                season_id, label, note, state,
                universe_fingerprint, timeframes_fingerprint,
                dataset_snapshot_id, engine_constitution_id,
                created_at, created_by, updated_at
            FROM seasons
            WHERE season_id = ?
        """, (season_id,))
        row = cursor.fetchone()
        
        if row is None:
            return None, []
        
        # Get attached job IDs
        cursor = conn.execute("""
            SELECT job_id FROM season_jobs
            WHERE season_id = ?
            ORDER BY attached_at DESC
        """, (season_id,))
        job_rows = cursor.fetchall()
        job_ids = [r["job_id"] for r in job_rows]
        
        # Build season record
        hard_boundary = SeasonHardBoundary(
            universe_fingerprint=row["universe_fingerprint"],
            timeframes_fingerprint=row["timeframes_fingerprint"],
            dataset_snapshot_id=row["dataset_snapshot_id"],
            engine_constitution_id=row["engine_constitution_id"],
        )
        season = SeasonRecord(
            season_id=row["season_id"],
            label=row["label"],
            note=row["note"],
            state=row["state"],
            hard_boundary=hard_boundary,
            created_at=row["created_at"],
            created_by=row["created_by"],
            updated_at=row["updated_at"],
        )
        
        return season, job_ids


def attach_job_to_season(
    season_id: str,
    job_id: str,
    actor: str,
    attach_evidence_path: str,
) -> SeasonAttachResponse:
    """
    Attach a job to a season.
    
    This function assumes boundary validation has already been performed
    and the attachment is valid. It only performs the database insertion.
    
    Args:
        season_id: Season ID
        job_id: Job ID to attach
        actor: Who is attaching the job
        attach_evidence_path: Path to evidence file
    
    Returns:
        SeasonAttachResponse with result="ACCEPTED"
    """
    now = now_iso()
    db = SupervisorDB(get_default_db_path())
    
    with db._connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            # Check if season exists
            cursor = conn.execute("SELECT 1 FROM seasons WHERE season_id = ?", (season_id,))
            if cursor.fetchone() is None:
                raise ValueError(f"Season {season_id} not found")
            
            # Check if job exists
            cursor = conn.execute("SELECT 1 FROM jobs WHERE job_id = ?", (job_id,))
            if cursor.fetchone() is None:
                raise ValueError(f"Job {job_id} not found")
            
            # Check if already attached
            cursor = conn.execute("""
                SELECT 1 FROM season_jobs 
                WHERE season_id = ? AND job_id = ?
            """, (season_id, job_id))
            if cursor.fetchone() is not None:
                raise ValueError(f"Job {job_id} already attached to season {season_id}")
            
            # Insert attachment
            conn.execute("""
                INSERT INTO season_jobs (
                    season_id, job_id, attached_at, attached_by, attach_evidence_path
                ) VALUES (?, ?, ?, ?, ?)
            """, (season_id, job_id, now, actor, attach_evidence_path))
            
            # Update season updated_at
            conn.execute("""
                UPDATE seasons SET updated_at = ? WHERE season_id = ?
            """, (now, season_id))
            
            conn.commit()
        except Exception:
            conn.rollback()
            raise
    
    return SeasonAttachResponse(
        season_id=season_id,
        job_id=job_id,
        result="ACCEPTED",
        mismatches=[],
    )


def freeze_season(season_id: str, actor: str) -> SeasonRecord:
    """
    Freeze a season (transition from OPEN to FROZEN).
    
    Args:
        season_id: Season ID to freeze
        actor: Who is freezing the season
    
    Returns:
        Updated SeasonRecord
    """
    now = now_iso()
    db = SupervisorDB(get_default_db_path())
    
    with db._connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            # Get current season
            cursor = conn.execute("""
                SELECT 
                    season_id, label, note, state,
                    universe_fingerprint, timeframes_fingerprint,
                    dataset_snapshot_id, engine_constitution_id,
                    created_at, created_by, updated_at
                FROM seasons
                WHERE season_id = ?
            """, (season_id,))
            row = cursor.fetchone()
            
            if row is None:
                raise ValueError(f"Season {season_id} not found")
            
            current_state = row["state"]
            if current_state != "OPEN":
                raise ValueError(f"Cannot freeze season in state {current_state}")
            
            # Update state
            conn.execute("""
                UPDATE seasons 
                SET state = 'FROZEN', updated_at = ?
                WHERE season_id = ?
            """, (now, season_id))
            
            conn.commit()
            
            # Build updated record
            hard_boundary = SeasonHardBoundary(
                universe_fingerprint=row["universe_fingerprint"],
                timeframes_fingerprint=row["timeframes_fingerprint"],
                dataset_snapshot_id=row["dataset_snapshot_id"],
                engine_constitution_id=row["engine_constitution_id"],
            )
            season = SeasonRecord(
                season_id=row["season_id"],
                label=row["label"],
                note=row["note"],
                state="FROZEN",
                hard_boundary=hard_boundary,
                created_at=row["created_at"],
                created_by=row["created_by"],
                updated_at=now,
            )
            
            return season
        except Exception:
            conn.rollback()
            raise


def archive_season(season_id: str, actor: str) -> SeasonRecord:
    """
    Archive a season (transition from FROZEN/DECIDING to ARCHIVED).
    
    Args:
        season_id: Season ID to archive
        actor: Who is archiving the season
    
    Returns:
        Updated SeasonRecord
    """
    now = now_iso()
    db = SupervisorDB(get_default_db_path())
    
    with db._connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            # Get current season
            cursor = conn.execute("""
                SELECT 
                    season_id, label, note, state,
                    universe_fingerprint, timeframes_fingerprint,
                    dataset_snapshot_id, engine_constitution_id,
                    created_at, created_by, updated_at
                FROM seasons
                WHERE season_id = ?
            """, (season_id,))
            row = cursor.fetchone()
            
            if row is None:
                raise ValueError(f"Season {season_id} not found")
            
            current_state = row["state"]
            if current_state not in ("FROZEN", "DECIDING"):
                raise ValueError(f"Cannot archive season in state {current_state}")
            
            # Update state
            conn.execute("""
                UPDATE seasons 
                SET state = 'ARCHIVED', updated_at = ?
                WHERE season_id = ?
            """, (now, season_id))
            
            conn.commit()
            
            # Build updated record
            hard_boundary = SeasonHardBoundary(
                universe_fingerprint=row["universe_fingerprint"],
                timeframes_fingerprint=row["timeframes_fingerprint"],
                dataset_snapshot_id=row["dataset_snapshot_id"],
                engine_constitution_id=row["engine_constitution_id"],
            )
            season = SeasonRecord(
                season_id=row["season_id"],
                label=row["label"],
                note=row["note"],
                state="ARCHIVED",
                hard_boundary=hard_boundary,
                created_at=row["created_at"],
                created_by=row["created_by"],
                updated_at=now,
            )
            
            return season
        except Exception:
            conn.rollback()
            raise


def get_season_jobs(season_id: str) -> List[str]:
    """
    Get list of job IDs attached to a season.
    
    Args:
        season_id: Season ID
    
    Returns:
        List of job IDs
    """
    db = SupervisorDB(get_default_db_path())
    with db._connect() as conn:
        cursor = conn.execute("""
            SELECT job_id FROM season_jobs
            WHERE season_id = ?
            ORDER BY attached_at DESC
        """, (season_id,))
        rows = cursor.fetchall()
        return [r["job_id"] for r in rows]


def is_job_attached_to_season(job_id: str) -> Optional[str]:
    """
    Check if a job is attached to any season.
    
    Args:
        job_id: Job ID to check
    
    Returns:
        Season ID if attached, None otherwise
    """
    db = SupervisorDB(get_default_db_path())
    with db._connect() as conn:
        cursor = conn.execute("""
            SELECT season_id FROM season_jobs
            WHERE job_id = ?
            LIMIT 1
        """, (job_id,))
        row = cursor.fetchone()
        return row["season_id"] if row else None