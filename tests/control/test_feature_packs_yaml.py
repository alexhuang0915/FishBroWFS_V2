import unittest


class TestFeaturePacksYaml(unittest.TestCase):
    def test_cross_pack_contains_expected_minimum(self) -> None:
        from control.feature_packs_yaml import get_pack_features

        feats = get_pack_features("cross_v1_full")
        names = {f.get("name") for f in feats}
        for required in ("corr_60", "beta_60", "r2_60", "spread_log_z_60", "rel_vol_ratio"):
            self.assertIn(required, names)

    def test_strategy_requirements_expand_packs(self) -> None:
        from contracts.strategy_features import load_requirements_from_yaml

        req = load_requirements_from_yaml("configs/strategies/regime_filter_v1.yaml")
        names = {r.name for r in req.required} | {r.name for r in req.optional}
        # from cross_v1_full
        self.assertIn("corr_60", names)
        # from data1_v1_basic
        self.assertIn("atr_14", names)


if __name__ == "__main__":
    unittest.main()

