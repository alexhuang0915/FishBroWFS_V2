import os
import tempfile
import unittest
from pathlib import Path


class TestSubmitEnqueuesJob(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="fishbro_test_submit_")
        self.addCleanup(self._tmp.cleanup)
        self.outputs_root = Path(self._tmp.name) / "outputs"
        os.environ["FISHBRO_OUTPUTS_ROOT"] = str(self.outputs_root)

    def tearDown(self) -> None:
        os.environ.pop("FISHBRO_OUTPUTS_ROOT", None)

    def test_submit_creates_queued_job_row(self) -> None:
        from control.supervisor import submit
        from control.supervisor.db import SupervisorDB, get_default_db_path

        job_id = submit("BUILD_DATA", {"dataset_id": "CME.MNQ", "timeframe_min": 60, "mode": "BARS_ONLY"})
        db = SupervisorDB(get_default_db_path())
        row = db.get_job_row(job_id)
        self.assertIsNotNone(row)
        self.assertEqual(row.state, "QUEUED")
        self.assertEqual(str(row.job_type), "BUILD_DATA")


if __name__ == "__main__":
    unittest.main()
