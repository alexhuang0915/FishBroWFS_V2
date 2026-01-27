import unittest
from pathlib import Path
import tempfile


class TestAutoPlanFromPortfolioSpec(unittest.TestCase):
    def test_plan_defaults(self) -> None:
        from control.auto.portfolio_spec import load_portfolio_spec_v1, data2_candidates_by_data1
        from control.auto.run_plan import plan_from_portfolio_spec

        spec_path = Path("configs/portfolio/portfolio_spec_v1.yaml")
        spec = load_portfolio_spec_v1(spec_path)
        plan = plan_from_portfolio_spec(spec, season=spec.seasons[-1], timeframes_min=[60])

        self.assertEqual(plan.season, spec.seasons[-1])
        self.assertEqual(plan.start_season, plan.end_season)
        self.assertEqual(plan.timeframes_min, [60])
        self.assertTrue(plan.instrument_ids)
        self.assertTrue(plan.strategy_ids)
        self.assertEqual(plan.data2_mode, "matrix")

        pairing = data2_candidates_by_data1(plan.instrument_ids)
        self.assertEqual(pairing, plan.data2_candidates_by_instrument)

    def test_plan_data2_override(self) -> None:
        from control.auto.portfolio_spec import load_portfolio_spec_v1
        from control.auto.run_plan import plan_from_portfolio_spec

        spec = load_portfolio_spec_v1(Path("configs/portfolio/portfolio_spec_v1.yaml"))
        plan = plan_from_portfolio_spec(spec, timeframes_min=[60], data2_dataset_id="CFE.VX")
        self.assertEqual(plan.data2_mode, "single")
        self.assertTrue(plan.data2_candidates_by_instrument)
        self.assertEqual({ins: ["CFE.VX"] for ins in plan.instrument_ids}, plan.data2_candidates_by_instrument)

    def test_plan_season_range_from_spec(self) -> None:
        from control.auto.portfolio_spec import load_portfolio_spec_v1
        from control.auto.run_plan import plan_from_portfolio_spec

        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "spec.yaml"
            p.write_text(
                "\n".join(
                    [
                        'version: "PORTFOLIO_SPEC_V1"',
                        'portfolio_id: "tmp_range_spec"',
                        "instrument_ids:",
                        '  - "CME.MNQ"',
                        "strategy_ids:",
                        '  - "baseline_v1"',
                        "seasons:",
                        '  - "2019Q1"',
                        '  - "2025Q4"',
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            spec = load_portfolio_spec_v1(p)
            plan = plan_from_portfolio_spec(spec, season="2026Q1", timeframes_min=[60])

            self.assertEqual(plan.season, "2026Q1")
            self.assertEqual(plan.start_season, "2019Q1")
            self.assertEqual(plan.end_season, "2025Q4")


if __name__ == "__main__":
    unittest.main()
