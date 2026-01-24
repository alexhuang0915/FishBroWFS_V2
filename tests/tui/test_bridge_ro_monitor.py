import os
import tempfile
import unittest
from pathlib import Path


class TestBridgeROMonitor(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="fishbro_test_bridge_")
        self.addCleanup(self._tmp.cleanup)
        self.outputs_root = Path(self._tmp.name) / "outputs"
        os.environ["FISHBRO_OUTPUTS_ROOT"] = str(self.outputs_root)

    def tearDown(self) -> None:
        os.environ.pop("FISHBRO_OUTPUTS_ROOT", None)

    def test_bridge_lists_jobs_shape(self) -> None:
        from control.supervisor import submit
        from gui.tui.services.bridge import Bridge

        submit("BUILD_DATA", {"dataset_id": "CME.MNQ", "timeframe_min": 60, "mode": "BARS_ONLY"})
        submit("BUILD_DATA", {"dataset_id": "CME.MNQ", "timeframe_min": 60, "mode": "BARS_ONLY"})

        bridge = Bridge()
        jobs = bridge.get_recent_jobs(limit=10)
        self.assertTrue(jobs, "should list jobs from sqlite (RO)")

        j = jobs[0]
        # Field shape that Monitor depends on.
        self.assertTrue(hasattr(j, "job_id"))
        self.assertTrue(hasattr(j, "job_type"))
        self.assertTrue(hasattr(j, "state"))
        self.assertTrue(hasattr(j, "progress"))
        self.assertTrue(hasattr(j, "phase"))
        self.assertTrue(hasattr(j, "updated_at"))


if __name__ == "__main__":
    unittest.main()
