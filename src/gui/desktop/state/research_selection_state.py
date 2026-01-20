from PySide6.QtCore import QObject, Signal

class ResearchSelectionState(QObject):
    """Singleton state for tracking the research run selected for portfolio decision."""
    selection_changed = Signal(str)  # Emits job_id

    def __init__(self):
        super().__init__()
        self._selected_job_id: str = ""

    def set_selection(self, job_id: str):
        if self._selected_job_id != job_id:
            self._selected_job_id = job_id
            self.selection_changed.emit(job_id)

    def get_selected_job_id(self) -> str:
        return self._selected_job_id

research_selection_state = ResearchSelectionState()
