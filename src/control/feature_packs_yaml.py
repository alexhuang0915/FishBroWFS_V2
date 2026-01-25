from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]


@lru_cache(maxsize=1)
def load_feature_packs_yaml() -> dict[str, dict[str, Any]]:
    """
    SSOT: configs/registry/feature_packs.yaml

    Returns: pack_id -> pack_doc (must include `features: []`).
    """
    path = REPO_ROOT / "configs" / "registry" / "feature_packs.yaml"
    if not path.exists():
        return {}
    try:
        import yaml  # type: ignore
    except Exception as e:  # pragma: no cover
        raise RuntimeError("PyYAML is required to load feature packs") from e

    doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    packs = doc.get("packs") or {}
    if not isinstance(packs, dict):
        return {}
    out: dict[str, dict[str, Any]] = {}
    for k, v in packs.items():
        if isinstance(k, str) and isinstance(v, dict):
            out[k] = v
    return out


def get_pack_features(pack_id: str) -> list[dict[str, Any]]:
    packs = load_feature_packs_yaml()
    pack = packs.get(pack_id)
    if pack is None:
        raise KeyError(f"Unknown feature pack '{pack_id}' (not in configs/registry/feature_packs.yaml)")
    feats = pack.get("features") or []
    if not isinstance(feats, list):
        raise ValueError(f"feature pack '{pack_id}' has invalid features list")
    out: list[dict[str, Any]] = []
    for item in feats:
        if isinstance(item, dict):
            out.append(item)
    return out


def expand_pack_with_overrides(
    *,
    pack_id: str | None,
    add: list[dict[str, Any]] | None,
    remove: list[str] | None,
) -> list[dict[str, Any]]:
    """
    Expand (pack_id + add/remove) into a single feature list.
    - remove matches by `name`
    - add entries override by `name` (last writer wins)
    """
    features: list[dict[str, Any]] = []
    if pack_id:
        features.extend(get_pack_features(pack_id))

    remove_set = {str(n).strip() for n in (remove or []) if str(n).strip()}
    if remove_set:
        features = [f for f in features if str(f.get("name") or "").strip() not in remove_set]

    merged: dict[str, dict[str, Any]] = {}
    for f in features:
        name = str(f.get("name") or "").strip()
        if not name:
            continue
        merged[name] = dict(f)

    for f in add or []:
        if not isinstance(f, dict):
            continue
        name = str(f.get("name") or "").strip()
        if not name:
            continue
        merged[name] = dict(f)

    # Stable order: pack order first, then new additions at end.
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for f in features:
        name = str(f.get("name") or "").strip()
        if not name or name in seen or name not in merged:
            continue
        result.append(merged[name])
        seen.add(name)
    for name in sorted(set(merged.keys()) - seen):
        result.append(merged[name])
    return result

