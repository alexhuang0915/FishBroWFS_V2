from __future__ import annotations

from pathlib import Path

import yaml


def test_cost_model_is_in_instruments_and_not_in_profiles():
    instruments_path = Path("configs/registry/instruments.yaml")
    assert instruments_path.exists()
    doc = yaml.safe_load(instruments_path.read_text(encoding="utf-8")) or {}
    instruments = doc.get("instruments", []) or []
    assert isinstance(instruments, list) and instruments

    for it in instruments:
        assert isinstance(it, dict)
        assert "id" in it
        cm = it.get("cost_model")
        assert isinstance(cm, dict), f"{it.get('id')} missing cost_model"
        assert "commission_per_side" in cm
        assert "slippage_per_side_ticks" in cm
        assert float(cm["slippage_per_side_ticks"]) == 1.0

    profiles_dir = Path("configs/profiles")
    assert profiles_dir.exists()
    for p in profiles_dir.glob("*.yaml"):
        p_doc = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        assert isinstance(p_doc, dict)
        assert "cost_model" not in p_doc, f"profile must not define cost_model: {p}"
