from PySide6.QtCore import QObject, Signal

from gui.desktop.state.job_store import job_store

class ResearchSelectionState(QObject):
    """Singleton state for tracking the research run selected for portfolio decision.
    
    [L3-2 Fix] Bound to JobStore to ensure single source of truth for selection.
    """
    selection_changed = Signal(str)  # Emits job_id

    def __init__(self):
        super().__init__()
        self._selected_job_id: str = ""
        
        # [L3-2 Fix] Auto-follow JobStore selection
        job_store.selected_changed.connect(self.set_selection)

    def set_selection(self, job_id: str):
        if self._selected_job_id != job_id:
            self._selected_job_id = job_id
            self.selection_changed.emit(job_id)

    def get_selected_job_id(self) -> str:
        return self._selected_job_id

research_selection_state = ResearchSelectionState()
