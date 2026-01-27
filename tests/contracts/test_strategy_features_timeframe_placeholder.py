import tempfile
import unittest
from pathlib import Path


class TestStrategyFeaturesTimeframePlaceholder(unittest.TestCase):
    def test_pack_timeframe_run_resolves_to_default(self) -> None:
        from contracts.strategy_features import load_requirements_from_yaml

        with tempfile.TemporaryDirectory(prefix="fishbro_test_tf_placeholder_") as td:
            p = Path(td) / "s.yaml"
            p.write_text(
                "\n".join(
                    [
                        "strategy_id: TEST",
                        "features:",
                        "  data1:",
                        "    pack: data1_v1_basic",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            req = load_requirements_from_yaml(str(p), default_timeframe_min=15)
            self.assertGreaterEqual(len(req.required), 1)
            # data1_v1_basic contains atr_14 with timeframe: RUN in SSOT packs.
            self.assertEqual(req.required[0].name, "atr_14")
            self.assertEqual(req.required[0].timeframe_min, 15)


if __name__ == "__main__":
    unittest.main()

