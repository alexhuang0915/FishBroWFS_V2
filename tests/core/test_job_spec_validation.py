import os
import tempfile
import unittest
from pathlib import Path


class TestJobSpecValidation(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="fishbro_test_core_")
        self.addCleanup(self._tmp.cleanup)
        self.outputs_root = Path(self._tmp.name) / "outputs"
        os.environ["FISHBRO_OUTPUTS_ROOT"] = str(self.outputs_root)

    def tearDown(self) -> None:
        os.environ.pop("FISHBRO_OUTPUTS_ROOT", None)

    def test_unknown_job_type_rejected_before_enqueue(self) -> None:
        from control.supervisor import submit

        with self.assertRaises(ValueError):
            submit("NOT_A_REAL_JOB", {})


if __name__ == "__main__":
    unittest.main()

