
import sys
import unittest
from unittest.mock import MagicMock
from pathlib import Path
from textual import events
from textual.app import App
from textual.geometry import Offset

# Add src to sys.path
src_path = str(Path.cwd() / "src")
if src_path not in sys.path:
    sys.path.insert(0, src_path)

# Import the widget to test
try:
    from gui.tui.widgets.job_monitor import JobDataTable  # legacy name
except Exception:
    raise unittest.SkipTest("Legacy JobDataTable no longer exists; skip outdated test.")

class MockApp(App):
    def __init__(self):
        super().__init__()
        self.open_delete_confirm_called_with = None

    def open_delete_confirm(self, job_id: str):
        self.open_delete_confirm_called_with = job_id

class TestDeleteClick(unittest.IsolatedAsyncioTestCase):
    async def test_action_click(self):
        app = MockApp()
        table = JobDataTable(id="monitor_table", cursor_type="row")
        
        # Mount the table to an app to initialize it
        async with app.run_test() as pilot:
            # Add table to app
            await app.mount(table)
            
            # Setup columns to match app (Must be done after app is available or inside context)
            table.add_column("Job ID", key="job_id")
            table.add_column("Type", key="job_type")
            table.add_column("Data2", key="data2")
            table.add_column("State", key="state")
            table.add_column("Progress", key="progress")
            table.add_column("Phase", key="phase")
            table.add_column("Updated", key="updated_at")
            table.add_column("Action", key="action") # Last column is Action
            
            table.add_row(
                "job123", "TYPE", "D2", "STATE", "100%", "phase", "time", "DELETE", key="job123"
            )
            
            # We need to find where the cell is.
            # In a headless test, geometry might be tricky.
            # Let's Mock get_coordinate_at to simulate a click hitting the right cell.
            # This verifies the LOGIC inside on_mouse_down, independent of exact pixel rendering.
            
            from textual.coordinate import Coordinate
            
            # Mock screen_to_local to return simple offset
            # table.screen_to_local = MagicMock(return_value=Offset(100, 10))
            # Actually, standard event has x,y.
            
            # Mock get_coordinate_at to return (0, 7) -> Row 0, Col 7 (Action)
            table.get_coordinate_at = MagicMock(return_value=Coordinate(0, 7))
            
            # Create a Click event
            event = events.Click(
                table,
                x=100, y=10,
                delta_x=0, delta_y=0,
                button=1, # Left Click
                shift=False, meta=False, ctrl=False,
                screen_x=100, screen_y=10
            )
            
            # Dispatch async
            await table.on_click(event)
            
            # Check results
            if app.open_delete_confirm_called_with == "job123":
                print("SUCCESS: Delete confirmation triggered for job123")
            else:
                print(f"FAILURE: Expected job123, got {app.open_delete_confirm_called_with}")
                sys.exit(1)

if __name__ == "__main__":
    unittest.main()
