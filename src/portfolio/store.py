"""
Portfolio persistence layer (Article VI).

Implements atomic writes and immutable snapshots for PortfolioManager state.
"""
from __future__ import annotations
from dataclasses import asdict, is_dataclass
from pathlib import Path
from datetime import datetime, timezone
from typing import Any, Dict, Optional, TYPE_CHECKING
import json
import os
import logging
import math

import pandas as pd

from portfolio.governance_state import StrategyRecord

if TYPE_CHECKING:
    from portfolio.manager import PortfolioManager
    from portfolio.audit import AuditTrail

logger = logging.getLogger(__name__)


class PortfolioStore:
    """Atomic persistence + snapshot store for PortfolioManager state."""

    def __init__(self, root_dir: str = "outputs/portfolio_store", audit: Optional["AuditTrail"] = None) -> None:
        self.root = Path(root_dir)
        self.root.mkdir(parents=True, exist_ok=True)
        self.snapshots_dir = self.root / "snapshots"
        self.snapshots_dir.mkdir(parents=True, exist_ok=True)
        self.current_state_path = self.root / "current_state.json"
        self.audit = audit

    def _dump_record(self, record: StrategyRecord) -> Dict[str, Any]:
        """Serialize a StrategyRecord to a JSON‑compatible dict."""
        if hasattr(record, "model_dump"):
            # Pydantic v2
            return record.model_dump(mode="json")
        if is_dataclass(record):
            return asdict(record)
        # fallback: best‑effort dict
        if hasattr(record, "__dict__"):
            return dict(record.__dict__)
        raise TypeError(f"Unsupported StrategyRecord type: {type(record)}")

    def _load_record(self, raw: Dict[str, Any]) -> StrategyRecord:
        """Reconstruct a StrategyRecord from a dict."""
        # Pydantic/dataclass construction works with **raw
        return StrategyRecord(**raw)

    def _dump_returns(self, s: Optional[pd.Series]) -> Optional[Dict[str, Any]]:
        """Serialize a pandas Series to a JSON‑compatible dict."""
        if s is None or getattr(s, "empty", False):
            return None
        ss = s.dropna()
        if len(ss) == 0:
            return None
        # encode as explicit pairs
        idx = ss.index
        # convert index to ISO strings
        idx_iso = [pd.Timestamp(x).isoformat() for x in pd.to_datetime(idx)]
        vals = [
            float(v) if v is not None and not (isinstance(v, float) and math.isnan(v))
            else None
            for v in ss.values
        ]
        return {"index_iso": idx_iso, "values": vals}

    def _load_returns(self, payload: Optional[Dict[str, Any]]) -> Optional[pd.Series]:
        """Reconstruct a pandas Series from a dict."""
        if not payload:
            return None
        idx = pd.to_datetime(payload["index_iso"])
        vals = payload["values"]
        s = pd.Series(vals, index=idx, dtype="float64")
        s = s.sort_index()
        return s

    def save_state(self, manager: "PortfolioManager") -> None:
        """
        Atomically write the current PortfolioManager state to disk.

        Uses a temporary file + fsync + os.replace for crash safety.
        """
        strategies_data = {
            sid: self._dump_record(rec) for sid, rec in manager.strategies.items()
        }
        returns_data = self._dump_returns(manager.portfolio_returns)

        now = datetime.now(timezone.utc).isoformat()
        payload = {
            "schema_version": 1,
            "updated_at": now,
            "strategies": strategies_data,
            "portfolio_returns": returns_data,
        }

        tmp = self.current_state_path.with_suffix(".json.tmp")
        # Write with fsync for crash safety
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, self.current_state_path)

        if self.audit:
            from portfolio.audit import make_save_state_event
            self.audit.append(make_save_state_event(
                strategy_count=len(manager.strategies),
                has_returns=manager.portfolio_returns is not None,
            ))

    def load_state(self) -> Dict[str, object]:
        """
        Load the persisted state from disk.

        Returns:
            dict with keys:
                - "strategies": Dict[str, StrategyRecord]
                - "portfolio_returns": Optional[pd.Series]
        """
        if not self.current_state_path.exists():
            return {"strategies": {}, "portfolio_returns": None}

        with open(self.current_state_path, "r", encoding="utf-8") as f:
            payload = json.load(f)

        strategies_raw = payload.get("strategies", {}) or {}
        strategies = {
            sid: self._load_record(raw) for sid, raw in strategies_raw.items()
        }
        returns = self._load_returns(payload.get("portfolio_returns"))
        return {"strategies": strategies, "portfolio_returns": returns}

    def snapshot(self, manager: "PortfolioManager", tag: str = "manual") -> Path:
        """
        Create an immutable snapshot of the current state.

        Args:
            manager: PortfolioManager instance
            tag: human‑readable label (will be sanitized)

        Returns:
            Path to the created snapshot file.
        """
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        # sanitize tag: keep alnum, dash, underscore; replace others with underscore
        safe_tag = "".join(
            c if c.isalnum() or c in ("-", "_") else "_" for c in tag
        )[:40]
        path = self.snapshots_dir / f"{ts}_{safe_tag}.json"

        payload = {
            "schema_version": 1,
            "timestamp": ts,
            "tag": tag,
            "strategies": {
                sid: self._dump_record(rec) for sid, rec in manager.strategies.items()
            },
            "portfolio_returns": self._dump_returns(manager.portfolio_returns),
        }

        # Write with fsync for crash safety
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())

        if self.audit:
            from portfolio.audit import make_snapshot_event
            self.audit.append(make_snapshot_event(
                tag=tag,
                strategy_count=len(manager.strategies),
                has_returns=manager.portfolio_returns is not None,
            ))

        return path