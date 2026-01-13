"""
Tests for SeasonsRepository functions.
"""
import pytest
import json
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timezone
from control.seasons_repo import (
    create_season,
    list_seasons,
    get_season,
    freeze_season,
    archive_season,
    attach_job_to_season,
    get_season_jobs,
)
from contracts.season import (
    SeasonCreateRequest,
    SeasonRecord,
    SeasonHardBoundary,
    SeasonState,
)


def test_create_season():
    """Test creating a new season."""
    mock_request = SeasonCreateRequest(
        label="Test Season",
        note="Test note",
        hard_boundary=SeasonHardBoundary(
            universe_fingerprint="universe_fp_123",
            timeframes_fingerprint="timeframes_fp_456",
            dataset_snapshot_id="dataset_snap_789",
            engine_constitution_id="engine_constitution_abc"
        ),
    )
    
    mock_conn = Mock()
    mock_cursor = Mock()
    mock_conn.cursor.return_value = mock_cursor
    mock_cursor.lastrowid = 1
    
    # Mock SupervisorDB and its _connect method
    mock_db = Mock()
    # Create a mock context manager for _connect
    mock_context_manager = MagicMock()
    mock_context_manager.__enter__.return_value = mock_conn
    mock_context_manager.__exit__.return_value = None
    mock_db._connect.return_value = mock_context_manager
    with patch('control.seasons_repo.SupervisorDB') as mock_supervisor_db:
        mock_supervisor_db.return_value = mock_db
        
        season = create_season(mock_request, actor="test_user")
        
        assert isinstance(season, SeasonRecord)
        assert season.season_id is not None
        assert season.label == "Test Season"
        assert season.note == "Test note"
        assert season.state == "DRAFT"
        assert season.hard_boundary.universe_fingerprint == "universe_fp_123"
        
        # Verify database was called (conn.execute, not cursor.execute)
        mock_conn.execute.assert_called()
        mock_conn.commit.assert_called_once()


def test_create_season_duplicate():
    """Test creating a season with duplicate ID should raise ValueError."""
    mock_request = SeasonCreateRequest(
        label="Test Season",
        note="Test note",
        hard_boundary=SeasonHardBoundary(
            universe_fingerprint="ufp",
            timeframes_fingerprint="tfp",
            dataset_snapshot_id="dsid",
            engine_constitution_id="ecid"
        ),
    )
    
    mock_conn = Mock()
    mock_cursor = Mock()
    mock_conn.cursor.return_value = mock_cursor
    
    # Simulate integrity error (duplicate) - actual code uses conn.execute()
    # There are two execute calls: BEGIN IMMEDIATE and INSERT
    # We want the INSERT to raise IntegrityError
    import sqlite3
    mock_conn.execute.side_effect = [
        Mock(),  # First call: BEGIN IMMEDIATE (returns a mock cursor)
        sqlite3.IntegrityError("UNIQUE constraint failed"),  # Second call: INSERT
    ]
    
    # Mock SupervisorDB and its _connect method
    mock_db = Mock()
    # Create a mock context manager for _connect
    mock_context_manager = MagicMock()
    mock_context_manager.__enter__.return_value = mock_conn
    mock_context_manager.__exit__.return_value = None
    mock_db._connect.return_value = mock_context_manager
    with patch('control.seasons_repo.SupervisorDB') as mock_supervisor_db:
        mock_supervisor_db.return_value = mock_db
        
        with pytest.raises(ValueError) as exc_info:
            create_season(mock_request, actor="test_user")
        
        assert "already exists" in str(exc_info.value)


def test_list_seasons():
    """Test listing all seasons."""
    mock_conn = Mock()
    mock_cursor = Mock()
    # The code uses conn.execute, not conn.cursor
    mock_conn.execute.return_value = mock_cursor
    
    # Mock database rows as dict-like objects using MagicMock
    def make_mock_row(season_id, label, note, state, universe_fp, timeframes_fp, dataset_id, engine_id, tags, created_at, updated_at):
        row = MagicMock()
        row.__getitem__.side_effect = lambda key: {
            "season_id": season_id,
            "label": label,
            "note": note,
            "state": state,
            "universe_fingerprint": universe_fp,
            "timeframes_fingerprint": timeframes_fp,
            "dataset_snapshot_id": dataset_id,
            "engine_constitution_id": engine_id,
            "created_at": created_at,
            "created_by": "test_user",
            "updated_at": updated_at,
        }[key]
        return row
    
    mock_rows = [
        make_mock_row(
            season_id="season_123",
            label="Test Season 1",
            note="Note 1",
            state="DRAFT",
            universe_fp="ufp1",
            timeframes_fp="tfp1",
            dataset_id="dsid1",
            engine_id="ecid1",
            tags=["test", "season1"],
            created_at="2025-01-01T00:00:00Z",
            updated_at="2025-01-01T00:00:00Z",
        ),
        make_mock_row(
            season_id="season_456",
            label="Test Season 2",
            note="Note 2",
            state="OPEN",
            universe_fp="ufp2",
            timeframes_fp="tfp2",
            dataset_id="dsid2",
            engine_id="ecid2",
            tags=["test", "season2"],
            created_at="2025-01-02T00:00:00Z",
            updated_at="2025-01-02T00:00:00Z",
        )
    ]
    mock_cursor.fetchall.return_value = mock_rows
    
    # Mock SupervisorDB and its _connect method
    mock_db = Mock()
    # Create a mock context manager for _connect
    mock_context_manager = MagicMock()
    mock_context_manager.__enter__.return_value = mock_conn
    mock_context_manager.__exit__.return_value = None
    mock_db._connect.return_value = mock_context_manager
    with patch('control.seasons_repo.SupervisorDB') as mock_supervisor_db:
        mock_supervisor_db.return_value = mock_db
        
        seasons = list_seasons()
        
        assert len(seasons) == 2
        assert seasons[0].season_id == "season_123"
        assert seasons[0].label == "Test Season 1"
        assert seasons[0].state == "DRAFT"
        assert seasons[1].season_id == "season_456"
        assert seasons[1].state == "OPEN"


def test_get_season_found():
    """Test getting a season by ID when it exists."""
    mock_conn = Mock()
    # First call: season select, second call: job select
    mock_season_cursor = Mock()
    mock_job_cursor = Mock()
    mock_conn.execute.side_effect = [mock_season_cursor, mock_job_cursor]
    
    # Mock season row as dict-like
    season_row = MagicMock()
    season_row.__getitem__.side_effect = lambda key: {
        "season_id": "season_123",
        "label": "Test Season",
        "note": "Test note",
        "state": "OPEN",
        "universe_fingerprint": "ufp1",
        "timeframes_fingerprint": "tfp1",
        "dataset_snapshot_id": "dsid1",
        "engine_constitution_id": "ecid1",
        "created_at": "2025-01-01T00:00:00Z",
        "created_by": "test_user",
        "updated_at": "2025-01-01T00:00:00Z",
    }[key]
    mock_season_cursor.fetchone.return_value = season_row
    
    # Mock job rows as dict-like (only job_id column)
    job_row1 = MagicMock()
    job_row1.__getitem__.side_effect = lambda key: {"job_id": "job_123"}[key]
    job_row2 = MagicMock()
    job_row2.__getitem__.side_effect = lambda key: {"job_id": "job_456"}[key]
    mock_job_cursor.fetchall.return_value = [job_row1, job_row2]
    
    # Mock SupervisorDB and its _connect method
    mock_db = Mock()
    # Create a mock context manager for _connect
    mock_context_manager = MagicMock()
    mock_context_manager.__enter__.return_value = mock_conn
    mock_context_manager.__exit__.return_value = None
    mock_db._connect.return_value = mock_context_manager
    with patch('control.seasons_repo.SupervisorDB') as mock_supervisor_db:
        mock_supervisor_db.return_value = mock_db
        
        season, job_ids = get_season("season_123")
        
        assert isinstance(season, SeasonRecord)
        assert season.season_id == "season_123"
        assert season.label == "Test Season"
        assert season.state == "OPEN"
        assert job_ids == ["job_123", "job_456"]


def test_get_season_not_found():
    """Test getting a season by ID when it doesn't exist."""
    mock_conn = Mock()
    mock_cursor = Mock()
    mock_conn.execute.return_value = mock_cursor
    mock_cursor.fetchone.return_value = None
    
    # Mock SupervisorDB and its _connect method
    mock_db = Mock()
    # Create a mock context manager for _connect
    mock_context_manager = MagicMock()
    mock_context_manager.__enter__.return_value = mock_conn
    mock_context_manager.__exit__.return_value = None
    mock_db._connect.return_value = mock_context_manager
    with patch('control.seasons_repo.SupervisorDB') as mock_supervisor_db:
        mock_supervisor_db.return_value = mock_db
        
        season, job_ids = get_season("nonexistent")
        
        assert season is None
        assert job_ids == []


def test_freeze_season():
    """Test freezing a season."""
    mock_conn = Mock()
    # Three calls: BEGIN IMMEDIATE, SELECT season, UPDATE season
    mock_begin_cursor = Mock()
    mock_select_cursor = Mock()
    mock_update_cursor = Mock()
    mock_conn.execute.side_effect = [mock_begin_cursor, mock_select_cursor, mock_update_cursor]
    
    # Create a dict-like row object
    class MockRow:
        def __init__(self, data):
            self._data = data
        def __getitem__(self, key):
            return self._data[key]
        def get(self, key, default=None):
            return self._data.get(key, default)
    
    season_row = MockRow({
        "season_id": "season_123",
        "label": "Test Season",
        "note": "Test note",
        "state": "OPEN",
        "universe_fingerprint": "ufp1",
        "timeframes_fingerprint": "tfp1",
        "dataset_snapshot_id": "dsid1",
        "engine_constitution_id": "ecid1",
        "created_at": "2025-01-01T00:00:00Z",
        "created_by": "test_user",
        "updated_at": "2025-01-01T00:00:00Z",
    })
    mock_select_cursor.fetchone.return_value = season_row
    mock_update_cursor.rowcount = 1  # One row affected
    
    # Mock SupervisorDB and its _connect method
    mock_db = Mock()
    # Create a mock context manager for _connect
    mock_context_manager = MagicMock()
    mock_context_manager.__enter__.return_value = mock_conn
    mock_context_manager.__exit__.return_value = None
    mock_db._connect.return_value = mock_context_manager
    with patch('control.seasons_repo.SupervisorDB') as mock_supervisor_db:
        mock_supervisor_db.return_value = mock_db
        
        updated_season = freeze_season("season_123", actor="test_user")
        
        assert isinstance(updated_season, SeasonRecord)
        assert updated_season.season_id == "season_123"
        assert updated_season.state == "FROZEN"
        
        # Verify database was called
        assert mock_conn.execute.call_count == 3
        mock_conn.commit.assert_called_once()


def test_freeze_season_not_found():
    """Test freezing a season that doesn't exist."""
    mock_conn = Mock()
    # Two calls: BEGIN IMMEDIATE, SELECT season (no UPDATE because error before)
    mock_begin_cursor = Mock()
    mock_select_cursor = Mock()
    mock_conn.execute.side_effect = [mock_begin_cursor, mock_select_cursor]
    mock_select_cursor.fetchone.return_value = None  # Season not found
    
    # Mock SupervisorDB and its _connect method
    mock_db = Mock()
    # Create a mock context manager for _connect
    mock_context_manager = MagicMock()
    mock_context_manager.__enter__.return_value = mock_conn
    mock_context_manager.__exit__.return_value = None
    mock_db._connect.return_value = mock_context_manager
    with patch('control.seasons_repo.SupervisorDB') as mock_supervisor_db:
        mock_supervisor_db.return_value = mock_db
        
        with pytest.raises(ValueError) as exc_info:
            freeze_season("nonexistent", actor="test_user")
        
        assert "Season nonexistent not found" in str(exc_info.value)


def test_archive_season():
    """Test archiving a season."""
    mock_conn = Mock()
    # Three calls: BEGIN IMMEDIATE, SELECT season, UPDATE season
    mock_begin_cursor = Mock()
    mock_select_cursor = Mock()
    mock_update_cursor = Mock()
    mock_conn.execute.side_effect = [mock_begin_cursor, mock_select_cursor, mock_update_cursor]
    
    # Create a dict-like row object
    class MockRow:
        def __init__(self, data):
            self._data = data
        def __getitem__(self, key):
            return self._data[key]
        def get(self, key, default=None):
            return self._data.get(key, default)
    
    season_row = MockRow({
        "season_id": "season_123",
        "label": "Test Season",
        "note": "Test note",
        "state": "FROZEN",
        "universe_fingerprint": "ufp1",
        "timeframes_fingerprint": "tfp1",
        "dataset_snapshot_id": "dsid1",
        "engine_constitution_id": "ecid1",
        "created_at": "2025-01-01T00:00:00Z",
        "created_by": "test_user",
        "updated_at": "2025-01-01T00:00:00Z",
    })
    mock_select_cursor.fetchone.return_value = season_row
    mock_update_cursor.rowcount = 1  # One row affected
    
    # Mock SupervisorDB and its _connect method
    mock_db = Mock()
    # Create a mock context manager for _connect
    mock_context_manager = MagicMock()
    mock_context_manager.__enter__.return_value = mock_conn
    mock_context_manager.__exit__.return_value = None
    mock_db._connect.return_value = mock_context_manager
    with patch('control.seasons_repo.SupervisorDB') as mock_supervisor_db:
        mock_supervisor_db.return_value = mock_db
        
        updated_season = archive_season("season_123", actor="test_user")
        
        assert isinstance(updated_season, SeasonRecord)
        assert updated_season.season_id == "season_123"
        assert updated_season.state == "ARCHIVED"
        
        # Verify database was called
        assert mock_conn.execute.call_count == 3
        mock_conn.commit.assert_called_once()


def test_attach_job_to_season():
    """Test attaching a job to a season."""
    mock_conn = Mock()
    # The function calls conn.execute multiple times:
    # 0. BEGIN IMMEDIATE
    # 1. SELECT 1 FROM seasons WHERE season_id = ?
    # 2. SELECT 1 FROM jobs WHERE job_id = ?
    # 3. SELECT 1 FROM season_jobs WHERE season_id = ? AND job_id = ?
    # 4. INSERT INTO season_jobs ...
    # 5. UPDATE seasons SET updated_at = ...
    # We'll mock each call to return a cursor with fetchone returning a row (for SELECTs)
    mock_begin_cursor = Mock()
    mock_cursor1 = Mock()
    mock_cursor1.fetchone.return_value = (1,)  # season exists
    mock_cursor2 = Mock()
    mock_cursor2.fetchone.return_value = (1,)  # job exists
    mock_cursor3 = Mock()
    mock_cursor3.fetchone.return_value = None  # not already attached
    mock_cursor4 = Mock()  # INSERT (no fetch needed)
    mock_cursor5 = Mock()  # UPDATE (no fetch needed)
    
    mock_conn.execute.side_effect = [mock_begin_cursor, mock_cursor1, mock_cursor2, mock_cursor3, mock_cursor4, mock_cursor5]
    
    # Mock SupervisorDB and its _connect method
    mock_db = Mock()
    # Create a mock context manager for _connect
    mock_context_manager = MagicMock()
    mock_context_manager.__enter__.return_value = mock_conn
    mock_context_manager.__exit__.return_value = None
    mock_db._connect.return_value = mock_context_manager
    with patch('control.seasons_repo.SupervisorDB') as mock_supervisor_db:
        mock_supervisor_db.return_value = mock_db
        
        attach_job_to_season(
            season_id="season_123",
            job_id="job_456",
            actor="test_user",
            attach_evidence_path="/tmp/evidence.json",
        )
        
        # Verify database was called (conn.execute, not cursor.execute)
        assert mock_conn.execute.call_count == 6
        mock_conn.commit.assert_called_once()


def test_attach_job_to_season_already_attached():
    """Test attaching a job that's already attached (raises IntegrityError)."""
    mock_conn = Mock()
    # The function calls conn.execute multiple times:
    # 0. BEGIN IMMEDIATE
    # 1. SELECT 1 FROM seasons WHERE season_id = ?
    # 2. SELECT 1 FROM jobs WHERE job_id = ?
    # 3. SELECT 1 FROM season_jobs WHERE season_id = ? AND job_id = ?
    # 4. INSERT INTO season_jobs ... (this will raise IntegrityError)
    # We'll mock the first three SELECTs to return valid rows, fourth raises error
    import sqlite3
    mock_begin_cursor = Mock()
    mock_cursor1 = Mock()
    mock_cursor1.fetchone.return_value = (1,)  # season exists
    mock_cursor2 = Mock()
    mock_cursor2.fetchone.return_value = (1,)  # job exists
    mock_cursor3 = Mock()
    mock_cursor3.fetchone.return_value = None  # not already attached (but will raise on insert due to race?)
    # Actually the SELECT returns None because the row doesn't exist yet, but INSERT will still raise UNIQUE
    # because of race condition? That's fine.
    
    mock_conn.execute.side_effect = [
        mock_begin_cursor,
        mock_cursor1,
        mock_cursor2,
        mock_cursor3,
        sqlite3.IntegrityError("UNIQUE constraint failed"),  # INSERT
    ]
    
    # Mock SupervisorDB and its _connect method
    mock_db = Mock()
    # Create a mock context manager for _connect
    mock_context_manager = MagicMock()
    mock_context_manager.__enter__.return_value = mock_conn
    mock_context_manager.__exit__.return_value = None
    mock_db._connect.return_value = mock_context_manager
    with patch('control.seasons_repo.SupervisorDB') as mock_supervisor_db:
        mock_supervisor_db.return_value = mock_db
        
        # Should raise IntegrityError (race condition)
        with pytest.raises(sqlite3.IntegrityError) as exc_info:
            attach_job_to_season(
                season_id="season_123",
                job_id="job_456",
                actor="test_user",
                attach_evidence_path="/tmp/evidence.json",
            )
        
        assert "UNIQUE constraint failed" in str(exc_info.value)
        # Should have tried to insert
        assert mock_conn.execute.call_count == 5


def test_get_season_jobs():
    """Test getting jobs attached to a season."""
    mock_conn = Mock()
    mock_cursor = Mock()
    mock_conn.execute.return_value = mock_cursor
    
    # Mock job rows as dict-like (only job_id column)
    job_row1 = MagicMock()
    job_row1.__getitem__.side_effect = lambda key: {"job_id": "job_123"}[key]
    job_row2 = MagicMock()
    job_row2.__getitem__.side_effect = lambda key: {"job_id": "job_456"}[key]
    job_row3 = MagicMock()
    job_row3.__getitem__.side_effect = lambda key: {"job_id": "job_789"}[key]
    mock_cursor.fetchall.return_value = [job_row1, job_row2, job_row3]
    
    # Mock SupervisorDB and its _connect method
    mock_db = Mock()
    # Create a mock context manager for _connect
    mock_context_manager = MagicMock()
    mock_context_manager.__enter__.return_value = mock_conn
    mock_context_manager.__exit__.return_value = None
    mock_db._connect.return_value = mock_context_manager
    with patch('control.seasons_repo.SupervisorDB') as mock_supervisor_db:
        mock_supervisor_db.return_value = mock_db
        
        job_ids = get_season_jobs("season_123")
        
        assert job_ids == ["job_123", "job_456", "job_789"]


def test_get_season_jobs_empty():
    """Test getting jobs for a season with no attached jobs."""
    mock_conn = Mock()
    mock_cursor = Mock()
    mock_conn.execute.return_value = mock_cursor
    mock_cursor.fetchall.return_value = []
    
    # Mock SupervisorDB and its _connect method
    mock_db = Mock()
    # Create a mock context manager for _connect
    mock_context_manager = MagicMock()
    mock_context_manager.__enter__.return_value = mock_conn
    mock_context_manager.__exit__.return_value = None
    mock_db._connect.return_value = mock_context_manager
    with patch('control.seasons_repo.SupervisorDB') as mock_supervisor_db:
        mock_supervisor_db.return_value = mock_db
        
        job_ids = get_season_jobs("season_123")
        
        assert job_ids == []