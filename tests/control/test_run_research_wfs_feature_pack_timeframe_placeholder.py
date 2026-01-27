import unittest


class TestRunResearchWfsFeaturePackTimeframePlaceholder(unittest.TestCase):
    def test_strategy_feature_pack_timeframe_run(self) -> None:
        from control.supervisor.handlers.run_research_wfs import _feature_specs_from_strategy

        doc = {
            "strategy_id": "TEST",
            "features": {
                "data1": {"pack": "data1_v1_basic"},
                "data2": None,
                "cross": {"pack": "cross_v1_full"},
            },
        }

        data1_specs, data2_specs, cross_names, _alias = _feature_specs_from_strategy(doc, default_tf=30)
        self.assertTrue(data1_specs)
        self.assertEqual(data1_specs[0].timeframe_min, 30)
        self.assertEqual(data2_specs, [])
        self.assertTrue(cross_names)


if __name__ == "__main__":
    unittest.main()

