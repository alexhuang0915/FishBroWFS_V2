from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True, slots=True)
class TimeframeSpec:
    id: str
    minutes: int
    label: str = ""


@dataclass(frozen=True, slots=True)
class TimeframeRegistry:
    version: str
    timeframes: tuple[TimeframeSpec, ...]
    default_id: str

    @property
    def allowed_timeframes(self) -> list[int]:
        return [tf.minutes for tf in self.timeframes]

    @property
    def default_minutes(self) -> int:
        for tf in self.timeframes:
            if tf.id == self.default_id:
                return tf.minutes
        # Fallback: first
        return self.timeframes[0].minutes if self.timeframes else 60


def _workspace_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _parse_timeframe_to_min(value: Any) -> int:
    if value is None:
        raise ValueError("timeframe is required")
    if isinstance(value, int):
        return value
    s = str(value).strip().lower()
    if not s:
        raise ValueError("timeframe is empty")
    if s.endswith("m"):
        return int(s[:-1])
    if s.endswith("h"):
        return int(s[:-1]) * 60
    return int(s)


def load_timeframes(path: Path | None = None) -> TimeframeRegistry:
    """
    Load timeframe registry from configs/registry/timeframes.yaml.

    Supports both:
      - New schema: {version, timeframes:[{id, minutes, label}], default:"60m"}
      - Legacy schema: {version, allowed_timeframes:[15,...], default:60}
    """
    if path is None:
        path = _workspace_root() / "configs" / "registry" / "timeframes.yaml"
    doc = yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else {}
    if not isinstance(doc, dict):
        doc = {}

    version = str(doc.get("version") or "unknown")

    # New schema
    tfs = doc.get("timeframes")
    if isinstance(tfs, list) and tfs:
        specs: list[TimeframeSpec] = []
        for item in tfs:
            if not isinstance(item, dict):
                continue
            tf_id = str(item.get("id") or "").strip()
            minutes = item.get("minutes")
            if not tf_id or minutes is None:
                continue
            specs.append(TimeframeSpec(id=tf_id, minutes=int(minutes), label=str(item.get("label") or tf_id)))
        if not specs:
            raise ValueError(f"No valid timeframes in {path}")
        default_id = str(doc.get("default") or specs[0].id)
        # If default is numeric, map to matching id
        try:
            default_min = _parse_timeframe_to_min(default_id)
            match = next((s.id for s in specs if s.minutes == default_min), None)
            if match:
                default_id = match
        except Exception:
            pass
        return TimeframeRegistry(version=version, timeframes=tuple(specs), default_id=default_id)

    # Legacy schema
    allowed = doc.get("allowed_timeframes")
    if isinstance(allowed, list) and allowed:
        specs = [TimeframeSpec(id=f"{int(m)}m", minutes=int(m), label=f"{int(m)}m") for m in allowed]
        d = doc.get("default")
        default_min = _parse_timeframe_to_min(d if d is not None else specs[0].minutes)
        default_id = next((s.id for s in specs if s.minutes == default_min), specs[0].id)
        return TimeframeRegistry(version=version, timeframes=tuple(specs), default_id=default_id)

    raise ValueError(f"Unsupported timeframe registry schema in {path}")

