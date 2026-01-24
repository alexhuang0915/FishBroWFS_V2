import os
import tempfile
import unittest
from pathlib import Path


class TestPolicyPreflight(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="fishbro_test_policy_")
        self.addCleanup(self._tmp.cleanup)
        self.outputs_root = Path(self._tmp.name) / "outputs"
        os.environ["FISHBRO_OUTPUTS_ROOT"] = str(self.outputs_root)

    def tearDown(self) -> None:
        os.environ.pop("FISHBRO_OUTPUTS_ROOT", None)

    def test_missing_season_rejected_with_stable_code(self) -> None:
        from control.supervisor import submit
        from control.policy_enforcement import PolicyEnforcementError
        from control.supervisor.db import SupervisorDB, get_default_db_path

        params = {
            "strategy_id": "s1_v1",
            "instrument": "CME.MNQ",
            "timeframe": "60m",
            "start_season": "2020Q1",
            "end_season": "2020Q2",
            # "season" missing
        }
        with self.assertRaises(PolicyEnforcementError) as ctx:
            submit("RUN_RESEARCH_WFS", params)

        self.assertEqual(ctx.exception.result.code, "POLICY_REJECT_MISSING_SEASON")

        # Job must be recorded as REJECTED.
        db = SupervisorDB(get_default_db_path())
        row = db.get_job_row(ctx.exception.job_id)
        self.assertIsNotNone(row)
        self.assertEqual(row.state, "REJECTED")

    def test_invalid_timeframe_format_rejected(self) -> None:
        from control.supervisor import submit
        from control.policy_enforcement import PolicyEnforcementError

        params = {
            "strategy_id": "s1_v1",
            "instrument": "CME.MNQ",
            "timeframe": "bad",
            "start_season": "2020Q1",
            "end_season": "2020Q2",
            "season": "2026Q1",
        }
        with self.assertRaises(PolicyEnforcementError) as ctx:
            submit("RUN_RESEARCH_WFS", params)

        self.assertEqual(ctx.exception.result.code, "POLICY_REJECT_INVALID_TIMEFRAME_FORMAT")


if __name__ == "__main__":
    unittest.main()

