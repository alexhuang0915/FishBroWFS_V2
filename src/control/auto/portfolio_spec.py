from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class PortfolioSpecV1:
    version: str
    seasons: list[str]
    instrument_ids: list[str]
    strategy_ids: list[str]


def load_portfolio_spec_v1(path: Path) -> PortfolioSpecV1:
    try:
        import yaml  # type: ignore
    except Exception as e:  # pragma: no cover
        raise RuntimeError("PyYAML is required") from e

    doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(doc, dict):
        raise ValueError("portfolio spec must be a mapping")

    version = str(doc.get("version") or "").strip()
    if version != "PORTFOLIO_SPEC_V1":
        raise ValueError(f"Unsupported portfolio spec version: {version!r}")

    seasons = [str(x).strip() for x in (doc.get("seasons") or []) if str(x).strip()]
    instrument_ids = [str(x).strip() for x in (doc.get("instrument_ids") or []) if str(x).strip()]
    strategy_ids = [str(x).strip() for x in (doc.get("strategy_ids") or []) if str(x).strip()]

    if not seasons:
        raise ValueError("portfolio spec missing seasons[]")
    if not instrument_ids:
        raise ValueError("portfolio spec missing instrument_ids[]")
    if not strategy_ids:
        raise ValueError("portfolio spec missing strategy_ids[]")

    return PortfolioSpecV1(
        version=version,
        seasons=seasons,
        instrument_ids=instrument_ids,
        strategy_ids=strategy_ids,
    )

@lru_cache(maxsize=1)
def _instrument_ids_from_registry() -> set[str]:
    try:
        import yaml  # type: ignore
    except Exception as e:  # pragma: no cover
        raise RuntimeError("PyYAML is required") from e

    p = Path("configs/registry/instruments.yaml")
    if not p.exists():
        return set()
    doc = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    out: set[str] = set()
    for item in (doc.get("instruments") or []):
        if isinstance(item, dict):
            v = str(item.get("id") or "").strip()
            if v:
                out.add(v)
    return out


def _load_data2_pairs_ssot(path: Path | None = None) -> dict[str, dict[str, Any]]:
    """
    Load configs/registry/data2_pairs.yaml.
    Returns: mapping data1_id -> {"primary": str|None, "candidates": list[str]}
    """
    try:
        import yaml  # type: ignore
    except Exception as e:  # pragma: no cover
        raise RuntimeError("PyYAML is required") from e

    p = path or Path("configs/registry/data2_pairs.yaml")
    if not p.exists():
        return {}
    doc = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    if not isinstance(doc, dict):
        raise ValueError("data2_pairs SSOT must be a mapping")
    pairs = doc.get("data2_pairs") or {}
    if not isinstance(pairs, dict):
        raise ValueError("data2_pairs must be a mapping")
    out: dict[str, dict[str, Any]] = {}
    for k, v in pairs.items():
        kk = str(k).strip()
        if not kk:
            continue
        out[kk] = v if isinstance(v, dict) else {}
    return out


def data2_candidates_by_data1(instrument_ids: list[str]) -> dict[str, list[str]]:
    """
    SSOT resolver for matrix runs: returns data1 -> candidates[] (possibly empty).
    """
    ids = [str(x).strip() for x in instrument_ids if str(x).strip()]
    pairs = _load_data2_pairs_ssot()
    known = _instrument_ids_from_registry()

    out: dict[str, list[str]] = {}
    for data1 in ids:
        entry = pairs.get(data1) or {}
        cand_raw = entry.get("candidates") or []
        if not isinstance(cand_raw, list):
            cand_raw = [cand_raw]
        cands = [str(x).strip() for x in cand_raw if str(x).strip()]

        seen: set[str] = set()
        normalized: list[str] = []
        for x in cands:
            if x == data1:
                continue
            if x in seen:
                continue
            seen.add(x)
            normalized.append(x)

        for x in normalized:
            if known and x not in known:
                raise ValueError(f"data2 candidate not found in instruments registry: {data1} -> {x}")

        out[data1] = normalized

    return out


def data2_primary_by_data1(instrument_ids: list[str]) -> dict[str, str | None]:
    """
    SSOT resolver for single runs: returns data1 -> primary (or None if not defined).
    """
    ids = [str(x).strip() for x in instrument_ids if str(x).strip()]
    pairs = _load_data2_pairs_ssot()
    known = _instrument_ids_from_registry()

    out: dict[str, str | None] = {}
    for data1 in ids:
        entry = pairs.get(data1) or {}
        primary = str(entry.get("primary") or "").strip() or None
        candidates = data2_candidates_by_data1([data1]).get(data1, [])
        chosen = primary or (candidates[0] if candidates else None)
        if chosen and known and chosen not in known:
            raise ValueError(f"data2 primary not found in instruments registry: {data1} -> {chosen}")
        out[data1] = chosen
    return out


def default_data2_pairing(instrument_ids: list[str]) -> dict[str, str | None]:
    """
    Legacy fallback pairing without extra SSOT:
    - If 0..1 instruments: data2=None
    - If >=2 instruments: cycle to the next instrument
    """
    ids = [str(x).strip() for x in instrument_ids if str(x).strip()]
    if len(ids) <= 1:
        return {ids[0]: None} if ids else {}
    out: dict[str, str | None] = {}
    for i, ins in enumerate(ids):
        out[ins] = ids[(i + 1) % len(ids)]
    return out


def ensure_list_str(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(x).strip() for x in value if str(x).strip()]
    return [str(value).strip()] if str(value).strip() else []
