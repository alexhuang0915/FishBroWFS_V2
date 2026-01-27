import os
import tempfile
import unittest
from pathlib import Path


class TestAutoOrchestratorDryRun(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="fishbro_test_auto_")
        self.addCleanup(self._tmp.cleanup)
        self.outputs_root = Path(self._tmp.name) / "outputs"
        os.environ["FISHBRO_OUTPUTS_ROOT"] = str(self.outputs_root)

    def tearDown(self) -> None:
        os.environ.pop("FISHBRO_OUTPUTS_ROOT", None)

    def test_dry_run_writes_manifest(self) -> None:
        from control.auto.portfolio_spec import load_portfolio_spec_v1
        from control.auto.run_plan import plan_from_portfolio_spec
        from control.auto.orchestrator import run_auto_wfs
        from core.paths import get_outputs_root

        spec = load_portfolio_spec_v1(Path("configs/portfolio/portfolio_spec_v1.yaml"))
        plan = plan_from_portfolio_spec(spec, season=spec.seasons[-1], timeframes_min=[60], max_workers=1, data2_mode="matrix")

        out = run_auto_wfs(plan=plan, dry_run=True, timeout_sec=1.0)
        self.assertTrue(out.get("dry_run"))

        # Ensure auto_runs/manifest exists under redirected outputs root.
        auto_runs_dir = get_outputs_root() / "artifacts" / "auto_runs"
        self.assertTrue(auto_runs_dir.exists())
        manifests = list(auto_runs_dir.rglob("manifest.json"))
        self.assertTrue(manifests, "manifest.json must be written in dry-run")


if __name__ == "__main__":
    unittest.main()
