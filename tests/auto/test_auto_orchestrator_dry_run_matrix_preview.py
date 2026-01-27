import os
import tempfile
import unittest
from pathlib import Path


class TestAutoOrchestratorDryRunMatrixPreview(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="fishbro_test_auto_matrix_preview_")
        self.addCleanup(self._tmp.cleanup)
        self.outputs_root = Path(self._tmp.name) / "outputs"
        os.environ["FISHBRO_OUTPUTS_ROOT"] = str(self.outputs_root)

    def tearDown(self) -> None:
        os.environ.pop("FISHBRO_OUTPUTS_ROOT", None)

    def test_dry_run_includes_matrix_preview(self) -> None:
        from control.auto.portfolio_spec import load_portfolio_spec_v1
        from control.auto.run_plan import plan_from_portfolio_spec
        from control.auto.orchestrator import run_auto_wfs

        spec = load_portfolio_spec_v1(Path("configs/portfolio/portfolio_spec_v1.yaml"))
        plan = plan_from_portfolio_spec(
            spec,
            season=spec.seasons[-1],
            timeframes_min=[60],
            data2_mode="matrix",
            max_workers=1,
        )

        out = run_auto_wfs(plan=plan, dry_run=True, timeout_sec=1.0)
        preview = out.get("preview") or {}
        self.assertIn("planned_wfs_job_count", preview)
        self.assertIn("planned_wfs_jobs_head", preview)

        head = preview.get("planned_wfs_jobs_head") or []
        self.assertTrue(head, "matrix preview must include at least one planned job")
        # For regime_filter_v1, data2 is required, so preview should include a data2 id.
        self.assertTrue(any((x.get("data2_dataset_id") not in (None, "")) for x in head))


if __name__ == "__main__":
    unittest.main()

