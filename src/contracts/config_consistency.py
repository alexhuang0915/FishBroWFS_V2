from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


def assert_cost_model_ssot_instruments(
    *,
    instruments_path: Path = Path("configs/registry/instruments.yaml"),
    profiles_dir: Path = Path("configs/profiles"),
) -> None:
    """
    Enforce SSOT rules:
      - cost_model is defined per instrument in configs/registry/instruments.yaml
      - profiles must NOT define cost_model
    """
    if not instruments_path.exists():
        raise ValueError(f"Missing instruments registry: {instruments_path}")

    doc = yaml.safe_load(instruments_path.read_text(encoding="utf-8")) or {}
    items = doc.get("instruments", []) or []
    if not isinstance(items, list) or not items:
        raise ValueError("Instrument registry must contain a non-empty 'instruments' list")

    missing_cost: list[str] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        iid = str(it.get("id") or "").strip()
        if not iid:
            continue
        cm = it.get("cost_model") or {}
        if not isinstance(cm, dict):
            missing_cost.append(iid)
            continue
        try:
            _ = float(cm.get("commission_per_side"))
            ticks = cm.get("slippage_per_side_ticks")
            if ticks is None:
                raise ValueError("missing slippage_per_side_ticks")
            _t = float(ticks)
            if _t != 1.0:
                raise ValueError("V1 requires slippage_per_side_ticks == 1")
        except Exception:
            missing_cost.append(iid)

    if missing_cost:
        raise ValueError(
            "Missing/invalid instrument cost_model (SSOT is instruments.yaml): "
            + ", ".join(sorted(missing_cost))
        )

    if not profiles_dir.exists():
        return

    bad_profiles: list[str] = []
    for p in sorted(profiles_dir.glob("*.yaml")):
        try:
            p_doc: Any = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
            if isinstance(p_doc, dict) and "cost_model" in p_doc:
                bad_profiles.append(p.name)
        except Exception:
            # If profile cannot be parsed, fail-closed.
            bad_profiles.append(p.name)

    if bad_profiles:
        raise ValueError(
            "Profiles must not define cost_model (SSOT is instruments.yaml). "
            "Remove 'cost_model' from: " + ", ".join(bad_profiles)
        )
