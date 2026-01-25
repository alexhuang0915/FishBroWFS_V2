from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class PackFeature:
    name: str
    timeframe: int | None
    required: bool


def _load_yaml(path: Path) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        doc = yaml.safe_load(f) or {}
    if not isinstance(doc, dict):
        raise ValueError(f"YAML root must be a mapping: {path}")
    return doc


def _pack_feature_list(pack: dict[str, Any]) -> list[PackFeature]:
    out: list[PackFeature] = []
    for it in (pack.get("features") or []):
        if isinstance(it, dict):
            name = str(it.get("name") or "").strip()
            if not name:
                continue
            tf = it.get("timeframe")
            timeframe = int(tf) if tf is not None else None
            required = bool(it.get("required", True))
            out.append(PackFeature(name=name, timeframe=timeframe, required=required))
    return out


def _strategy_declared_packs(strategy_cfg: dict[str, Any]) -> dict[str, str | None]:
    feat = strategy_cfg.get("features") or {}
    if not isinstance(feat, dict):
        return {"data1": None, "data2": None, "cross": None}
    out: dict[str, str | None] = {}
    for k in ("data1", "data2", "cross"):
        section = feat.get(k) or {}
        if isinstance(section, dict):
            pack = section.get("pack")
            out[k] = str(pack) if pack else None
        else:
            out[k] = None
    return out


def main() -> int:
    repo_root = Path(__file__).resolve().parents[2]
    strategies_registry_path = repo_root / "configs" / "registry" / "strategies.yaml"
    packs_path = repo_root / "configs" / "registry" / "feature_packs.yaml"
    strategies_dir = repo_root / "configs" / "strategies"
    output_doc = repo_root / "docs" / "REF_STRATEGY_FEATURE_MAP.md"

    reg = _load_yaml(strategies_registry_path)
    packs_doc = _load_yaml(packs_path)

    strategies = reg.get("strategies") or []
    if not isinstance(strategies, list):
        raise ValueError("configs/registry/strategies.yaml: strategies must be a list")

    packs = packs_doc.get("packs") or {}
    if not isinstance(packs, dict):
        raise ValueError("configs/registry/feature_packs.yaml: packs must be a mapping")

    pack_features: dict[str, list[PackFeature]] = {}
    for pack_id, pack in packs.items():
        if not isinstance(pack, dict):
            continue
        pack_features[str(pack_id)] = _pack_feature_list(pack)

    active_strategies = [s for s in strategies if isinstance(s, dict) and str(s.get("status", "")).lower() == "active"]

    lines: list[str] = []
    lines.append("# Strategy & Feature Map (Generated)")
    lines.append("")
    lines.append("This is a **generated** reference snapshot for humans and AIs.")
    lines.append("Authoritative semantics live in `docs/SPEC_ENGINE_V1.md`.")
    lines.append("")
    lines.append("Regenerate:")
    lines.append("```bash")
    lines.append("PYTHONPATH=src python3 scripts/dev/generate_strategy_feature_map.py")
    lines.append("```")
    lines.append("")

    lines.append("## Summary")
    lines.append(f"- Active strategies: **{len(active_strategies)}**")
    lines.append(f"- Feature packs: **{len(pack_features)}**")
    lines.append("")

    lines.append("## Strategy Catalog")
    lines.append("")
    lines.append("| Strategy ID | Config | Status | Packs (data1/cross) | Data2 Required |")
    lines.append("| --- | --- | --- | --- | --- |")

    for s in sorted(active_strategies, key=lambda x: str(x.get("id") or "")):
        sid = str(s.get("id") or "").strip()
        cfg_file = str(s.get("config_file") or "").strip()
        status = str(s.get("status") or "").strip()
        cfg_path = strategies_dir / cfg_file if cfg_file else None

        packs_used = {"data1": None, "data2": None, "cross": None}
        if cfg_path and cfg_path.exists():
            try:
                cfg_doc = _load_yaml(cfg_path)
                packs_used = _strategy_declared_packs(cfg_doc)
            except Exception:
                packs_used = {"data1": None, "data2": None, "cross": None}

        data1_pack = packs_used.get("data1") or "—"
        cross_pack = packs_used.get("cross") or "—"
        data2_required = "YES" if packs_used.get("cross") else "NO"

        cfg_display = f"`configs/strategies/{cfg_file}`" if cfg_file else "—"
        lines.append(f"| `{sid}` | {cfg_display} | `{status}` | `{data1_pack}` / `{cross_pack}` | {data2_required} |")

    lines.append("")

    lines.append("## Feature Packs")
    lines.append("")
    for pack_id in sorted(pack_features.keys()):
        feats = pack_features[pack_id]
        names = sorted({f.name for f in feats})
        tfs = sorted({f.timeframe for f in feats if f.timeframe is not None})
        tf_str = ", ".join(f"{tf}m" for tf in tfs) if tfs else "—"
        lines.append(f"### `{pack_id}`")
        lines.append(f"- Features: **{len(names)}**")
        lines.append(f"- Timeframes: {tf_str}")
        lines.append("")
        lines.append("```")
        for name in names:
            lines.append(name)
        lines.append("```")
        lines.append("")

    output_doc.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
