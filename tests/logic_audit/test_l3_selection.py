import sys
from unittest.mock import MagicMock

# Mock PySide6 if not installed
try:
    import PySide6
except ImportError:
    # Create mock module structure
    mock_pyside = MagicMock()
    mock_qtcore = MagicMock()
    
    # Mock QObject and Signal
    class MockQObject:
        def __init__(self, *args, **kwargs):
            pass
            
    class MockSignal:
        def __init__(self, *args):
            self._slots = []
        
        def connect(self, slot):
            self._slots.append(slot)
            
        def emit(self, *args):
            for slot in self._slots:
                slot(*args)
                
    mock_qtcore.QObject = MockQObject
    mock_qtcore.Signal = MockSignal
    
    mock_pyside.QtCore = mock_qtcore
    sys.modules["PySide6"] = mock_pyside
    sys.modules["PySide6.QtCore"] = mock_qtcore

import pytest
from gui.desktop.state.job_store import job_store
from gui.desktop.state.research_selection_state import research_selection_state

def test_selection_sync():
    """L3-2: Verify ResearchSelectionState follows JobStore selection."""
    
    # Simulate selecting a job in JobStore
    job_id = "job_123_sync_test"
    
    # [Fix] Job must exist to be selected
    from gui.desktop.state.job_store import JobRecord
    from datetime import datetime
    job = JobRecord(
        job_id=job_id, job_type="test", created_at=datetime.now(), status="done"
    )
    job_store.upsert(job)
    
    job_store.set_selected(job_id)
    
    # Assert ResearchSelectionState updated automatically
    assert research_selection_state.get_selected_job_id() == job_id
    
    # Change to another
    job_id_2 = "job_456_sync_test"
    job_2 = JobRecord(
        job_id=job_id_2, job_type="test", created_at=datetime.now(), status="done"
    )
    job_store.upsert(job_2)
    
    job_store.set_selected(job_id_2)
    assert research_selection_state.get_selected_job_id() == job_id_2
