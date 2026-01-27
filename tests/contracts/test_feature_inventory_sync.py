import unittest

import yaml
import numpy as np
from pathlib import Path

from core.features.cross import compute_cross_features_v1


def _is_supported_data1_name(name: str) -> bool:
    if name in {"atr_14", "ret_z_200", "session_vwap"}:
        return True
    supported_prefixes = (
        "sma_",
        "ema_",
        "hh_",
        "ll_",
        "atr_",
        "percentile_",
        "vx_percentile_",
        "zscore_",
        "ret_z_",
        "bb_pb_",
        "bb_width_",
        "atr_ch_upper_",
        "atr_ch_lower_",
        "atr_ch_pos_",
        "donchian_width_",
        "dist_hh_",
        "dist_ll_",
        "rsi_",
        "adx_",
        "di_plus_",
        "di_minus_",
        "macd_hist_",
        "roc_",
        "atr_pct_",
    )
    return name.startswith(supported_prefixes)


class TestFeatureInventorySync(unittest.TestCase):
    def test_data1_packs_are_supported_by_dispatch(self):
        doc = yaml.safe_load(Path("configs/registry/feature_packs.yaml").read_text(encoding="utf-8")) or {}
        packs = doc.get("packs", {}) or {}

        for pack_id in ("data1_v1_basic", "data1_v1_full", "data1_v1_momentum"):
            pack = packs.get(pack_id) or {}
            feats = pack.get("features") or []
            for f in feats:
                self.assertIsInstance(f, dict)
                name = str(f.get("name") or "")
                self.assertTrue(name, msg=f"empty feature name in pack {pack_id}")
                self.assertTrue(
                    _is_supported_data1_name(name),
                    msg=f"pack {pack_id} contains unsupported data1 feature name: {name}",
                )

    def test_cross_pack_matches_cross_compute_keys(self):
        doc = yaml.safe_load(Path("configs/registry/feature_packs.yaml").read_text(encoding="utf-8")) or {}
        packs = doc.get("packs", {}) or {}
        pack = packs.get("cross_v1_full") or {}
        feats = pack.get("features") or []
        expected = {str(f.get("name")) for f in feats if isinstance(f, dict) and f.get("name")}

        n = 260  # > 120 windows
        o1 = np.full(n, 100.0)
        h1 = np.full(n, 101.0)
        l1 = np.full(n, 99.0)
        c1 = np.linspace(100.0, 120.0, n)
        o2 = np.full(n, 50.0)
        h2 = np.full(n, 51.0)
        l2 = np.full(n, 49.0)
        c2 = np.linspace(50.0, 60.0, n)

        out = compute_cross_features_v1(o1=o1, h1=h1, l1=l1, c1=c1, o2=o2, h2=h2, l2=l2, c2=c2)
        keys = set(out.keys())

        missing = sorted(expected - keys)
        self.assertFalse(missing, msg=f"cross_v1_full contains missing keys from compute_cross_features_v1: {missing}")


if __name__ == "__main__":
    unittest.main()

