
"""Decisions log parser for portfolio generation.

Parses append-only decisions.log lines. Supports JSONL + pipe format.
Invalid lines are ignored.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _as_stripped_text(v: Any) -> str:
    """Convert value to trimmed string. None -> ''."""
    if v is None:
        return ""
    if isinstance(v, str):
        return v.strip()
    return str(v).strip()


def _parse_pipe_line(s: str) -> dict | None:
    """
    Parse simple pipe-delimited lines:
      - run_id|DECISION
      - run_id|DECISION|note
      - run_id|DECISION|note|ts
    note may be empty. ts may be missing.
    """
    parts = [p.strip() for p in s.split("|")]
    if len(parts) < 2:
        return None

    run_id = parts[0].strip()
    decision_raw = parts[1].strip()
    note = parts[2].strip() if len(parts) >= 3 else ""
    ts = parts[3].strip() if len(parts) >= 4 else ""

    if not run_id:
        return None
    if not decision_raw:
        return None

    out = {
        "run_id": run_id,
        "decision": decision_raw.upper(),
        "note": note,
    }
    if ts:
        out["ts"] = ts
    return out


def parse_decisions_log_lines(lines: list[str]) -> list[dict]:
    """Parse decisions.log lines. Supports JSONL + pipe format. Invalid lines ignored.
    
    Required:
      - run_id (non-empty after strip)
      - decision (non-empty after strip; normalized to upper)
    Optional:
      - note (may be missing/empty)
      - ts   (kept if present)
    """
    out: list[dict] = []

    for raw in lines:
        if not isinstance(raw, str):
            continue
        s = raw.strip()
        if not s:
            continue
            
        # 1) Try JSONL first
        parsed: dict | None = None
        try:
            obj = json.loads(s)
            if isinstance(obj, dict):
                run_id = _as_stripped_text(obj.get("run_id"))
                decision_raw = _as_stripped_text(obj.get("decision"))
                note = _as_stripped_text(obj.get("note"))
                ts = _as_stripped_text(obj.get("ts"))

                if not run_id:
                    continue
                if not decision_raw:
                    continue

                parsed = {
                    "run_id": run_id,
                    "decision": decision_raw.upper(),
                    "note": note,
                }
                if ts:
                    parsed["ts"] = ts
        except Exception:
            # Not JSON -> try pipe
            parsed = None

        # 2) Pipe fallback
        if parsed is None:
            parsed = _parse_pipe_line(s)

        if parsed is None:
            continue

        out.append(parsed)

    return out


def read_decisions_log(decisions_log_path: Path) -> list[dict]:
    """Read decisions.log file and parse its contents.
    
    Args:
        decisions_log_path: Path to decisions.log file
        
    Returns:
        List of parsed decision entries. Returns empty list if file doesn't exist.
    """
    if not decisions_log_path.exists():
        return []
    
    try:
        with open(decisions_log_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        return parse_decisions_log_lines(lines)
    except Exception:
        # If any error occurs (permission, encoding, etc.), return empty list
        return []


