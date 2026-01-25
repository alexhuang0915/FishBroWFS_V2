from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class StrategyRegistryEntry:
    strategy_id: str
    config_file: str
    raw: dict[str, Any]


@lru_cache(maxsize=1)
def load_strategy_registry_yaml() -> dict[str, StrategyRegistryEntry]:
    """
    SSOT: configs/registry/strategies.yaml

    Returns a mapping: strategy_id -> registry entry.
    """
    reg_path = REPO_ROOT / "configs" / "registry" / "strategies.yaml"
    if not reg_path.exists():
        return {}
    try:
        import yaml  # type: ignore
    except Exception as e:  # pragma: no cover
        raise RuntimeError("PyYAML is required to load strategy registry") from e

    doc = yaml.safe_load(reg_path.read_text(encoding="utf-8")) or {}
    out: dict[str, StrategyRegistryEntry] = {}
    for item in doc.get("strategies", []) or []:
        if not isinstance(item, dict):
            continue
        sid = str(item.get("id") or "").strip()
        cfg = str(item.get("config_file") or "").strip()
        if not sid or not cfg:
            continue
        out[sid] = StrategyRegistryEntry(strategy_id=sid, config_file=cfg, raw=item)
    return out


def get_strategy_config_path(strategy_id: str) -> Path:
    registry = load_strategy_registry_yaml()
    entry = registry.get(strategy_id)
    if entry is None:
        raise KeyError(f"Unknown strategy_id '{strategy_id}' (not in configs/registry/strategies.yaml)")
    path = REPO_ROOT / "configs" / "strategies" / entry.config_file
    if not path.exists():
        raise FileNotFoundError(f"Strategy config_file missing for '{strategy_id}': {path}")
    return path


def load_strategy_config(strategy_id: str) -> dict[str, Any]:
    path = get_strategy_config_path(strategy_id)
    try:
        import yaml  # type: ignore
    except Exception as e:  # pragma: no cover
        raise RuntimeError("PyYAML is required to load strategy configs") from e
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}

