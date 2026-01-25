import unittest


class TestStrategyRegistryYaml(unittest.TestCase):
    def test_registry_is_ssot_and_legacy_is_not_listed(self) -> None:
        from control.strategy_registry_yaml import load_strategy_registry_yaml

        reg = load_strategy_registry_yaml()
        self.assertIn("regime_filter_v1", reg)
        self.assertNotIn("s1_v1", reg)
        self.assertNotIn("s2_v1", reg)
        self.assertNotIn("s3_v1", reg)

    def test_unknown_strategy_rejected(self) -> None:
        from control.strategy_registry_yaml import get_strategy_config_path

        with self.assertRaises(KeyError):
            get_strategy_config_path("s1_v1")

    def test_strategy_config_has_class_path(self) -> None:
        from control.strategy_registry_yaml import load_strategy_config

        doc = load_strategy_config("regime_filter_v1")
        self.assertTrue(doc.get("class_path"))


if __name__ == "__main__":
    unittest.main()

