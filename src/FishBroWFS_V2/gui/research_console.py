"""Research Console Core Module.

Phase 10: Read-only UI for research artifacts with decision input.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

from FishBroWFS_V2.research.decision import append_decision


def load_research_artifacts(outputs_root: Path) -> dict:
    """
    Load:
    - outputs/research/research_index.json
    - outputs/research/canonical_results.json
    Raise if missing.
    """
    research_dir = outputs_root / "research"
    
    index_path = research_dir / "research_index.json"
    canonical_path = research_dir / "canonical_results.json"
    
    if not index_path.exists():
        raise FileNotFoundError(f"research_index.json not found at {index_path}")
    if not canonical_path.exists():
        raise FileNotFoundError(f"canonical_results.json not found at {canonical_path}")
    
    with open(index_path, "r", encoding="utf-8") as f:
        index_data = json.load(f)
    
    with open(canonical_path, "r", encoding="utf-8") as f:
        canonical_data = json.load(f)
    
    # Create a mapping from run_id to canonical result for quick lookup
    canonical_map = {}
    for result in canonical_data:
        run_id = result.get("run_id")
        if run_id:
            canonical_map[run_id] = result
    
    return {
        "index": index_data,
        "canonical_map": canonical_map,
        "index_path": index_path,
        "canonical_path": canonical_path,
        "index_mtime": index_path.stat().st_mtime if index_path.exists() else 0,
    }


def summarize_index(index: dict) -> list[dict]:
    """
    Convert research_index to flat rows for UI table.
    Pure function.
    """
    rows = []
    entries = index.get("entries", [])
    
    for entry in entries:
        run_id = entry.get("run_id", "")
        keys = entry.get("keys", {})
        
        row = {
            "run_id": run_id,
            "symbol": keys.get("symbol"),
            "strategy_id": keys.get("strategy_id"),
            "portfolio_id": keys.get("portfolio_id"),
            "score_final": entry.get("score_final", 0.0),
            "score_net_mdd": entry.get("score_net_mdd", 0.0),
            "trades": entry.get("trades", 0),
            "decision": entry.get("decision", "UNDECIDED"),
        }
        rows.append(row)
    
    return rows


def apply_filters(
    rows: list[dict],
    *,
    text: str | None,
    symbol: str | None,
    strategy_id: str | None,
    decision: str | None,
) -> list[dict]:
    """
    Deterministic filter.
    No IO.
    """
    filtered = rows
    
    # Text filter (case-insensitive search in run_id, symbol, strategy_id)
    if text:
        text_lower = text.lower()
        filtered = [
            row for row in filtered
            if (
                (row.get("run_id", "").lower().find(text_lower) >= 0) or
                (row.get("symbol", "").lower().find(text_lower) >= 0) or
                (row.get("strategy_id", "").lower().find(text_lower) >= 0)
            )
        ]
    
    # Symbol filter
    if symbol:
        filtered = [row for row in filtered if row.get("symbol") == symbol]
    
    # Strategy filter
    if strategy_id:
        filtered = [row for row in filtered if row.get("strategy_id") == strategy_id]
    
    # Decision filter
    if decision and decision != "ALL":
        filtered = [row for row in filtered if row.get("decision") == decision]
    
    return filtered


def load_run_detail(run_id: str, outputs_root: Path) -> dict:
    """
    Read-only load:
    - manifest.json
    - metrics.json
    - README.md (truncated)
    """
    # First find the run directory
    run_dir = None
    seasons_dir = outputs_root / "seasons"
    
    if seasons_dir.exists():
        for season_dir in seasons_dir.iterdir():
            if not season_dir.is_dir():
                continue
            
            runs_dir = season_dir / "runs"
            if not runs_dir.exists():
                continue
            
            potential_run_dir = runs_dir / run_id
            if potential_run_dir.exists() and potential_run_dir.is_dir():
                run_dir = potential_run_dir
                break
    
    if not run_dir:
        raise FileNotFoundError(f"Run directory not found for run_id: {run_id}")
    
    # Load manifest.json
    manifest = {}
    manifest_path = run_dir / "manifest.json"
    if manifest_path.exists():
        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                manifest = json.load(f)
        except json.JSONDecodeError:
            pass
    
    # Load metrics.json
    metrics = {}
    metrics_path = run_dir / "metrics.json"
    if metrics_path.exists():
        try:
            with open(metrics_path, "r", encoding="utf-8") as f:
                metrics = json.load(f)
        except json.JSONDecodeError:
            pass
    
    # Load README.md (truncated to first 1000 chars)
    readme_content = ""
    readme_path = run_dir / "README.md"
    if readme_path.exists():
        try:
            with open(readme_path, "r", encoding="utf-8") as f:
                content = f.read()
                # Truncate to 1000 characters
                if len(content) > 1000:
                    readme_content = content[:1000] + "... [truncated]"
                else:
                    readme_content = content
        except Exception:
            pass
    
    # Load winners.json if exists
    winners = {}
    winners_path = run_dir / "winners.json"
    if winners_path.exists():
        try:
            with open(winners_path, "r", encoding="utf-8") as f:
                winners = json.load(f)
        except json.JSONDecodeError:
            pass
    
    # Load winners_v2.json if exists
    winners_v2 = {}
    winners_v2_path = run_dir / "winners_v2.json"
    if winners_v2_path.exists():
        try:
            with open(winners_v2_path, "r", encoding="utf-8") as f:
                winners_v2 = json.load(f)
        except json.JSONDecodeError:
            pass
    
    return {
        "run_id": run_id,
        "manifest": manifest,
        "metrics": metrics,
        "winners": winners,
        "winners_v2": winners_v2,
        "readme": readme_content,
        "run_dir": str(run_dir),
    }


def submit_decision(
    *,
    outputs_root: Path,
    run_id: str,
    decision: Literal["KEEP", "DROP", "ARCHIVE"],
    note: str,
) -> None:
    """
    Must call:
    FishBroWFS_V2.research.decision.append_decision(...)
    """
    if len(note.strip()) < 5:
        raise ValueError("Note must be at least 5 characters long")
    
    research_dir = outputs_root / "research"
    append_decision(research_dir, run_id, decision, note)


def get_unique_values(rows: list[dict], field: str) -> list[str]:
    """
    Get unique non-empty values from rows for a given field.
    Used for dropdown filters.
    """
    values = set()
    for row in rows:
        value = row.get(field)
        if value:
            values.add(value)
    return sorted(list(values))
