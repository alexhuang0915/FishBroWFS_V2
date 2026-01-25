from __future__ import annotations

from textual.screen import ModalScreen
from textual.containers import Vertical, Horizontal
from textual.widgets import Button, Label, Static


class ConfirmDeleteModal(ModalScreen):
    """Confirmation modal for destructive deletes."""

    def __init__(self, job_id: str, **kwargs):
        super().__init__(**kwargs)
        self.job_id = job_id

    def compose(self):
        with Vertical(id="confirm_delete_modal"):
            yield Label("Confirm Delete", id="confirm_delete_title")
            yield Static(
                f"Delete local data for job:\n{self.job_id}\nThis cannot be undone.",
                id="confirm_delete_body",
            )
            with Horizontal(id="confirm_delete_actions"):
                yield Button("Cancel", id="confirm_delete_cancel", variant="default")
                yield Button("Delete", id="confirm_delete_confirm", variant="error")

    def on_mount(self):
        try:
            self.query_one("#confirm_delete_cancel", Button).focus()
        except Exception:
            pass

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "confirm_delete_cancel":
            self.app.pop_screen()
            return
        if event.button.id == "confirm_delete_confirm":
            result = self.app.bridge.delete_job_data(self.job_id)
            try:
                screen = self.app.get_screen("monitor")
                status = screen.query_one("#status")
                if result.get("error"):
                    status.update(f"Delete failed: {result['error']}")
                else:
                    status.update(f"Deleted job data: {self.job_id[:8]}")
                if hasattr(screen, "_reload_artifacts"):
                    screen._reload_artifacts()
            except Exception:
                pass
            self.app.pop_screen()
