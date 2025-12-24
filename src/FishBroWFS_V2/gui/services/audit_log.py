"""
Audit Log - Append-only JSONL logging for UI actions.

Phase 4: Every UI Action / Archive / Clone must write an audit event.
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, Optional

from FishBroWFS_V2.core.season_context import outputs_root, season_dir


def append_audit_event(event: Dict[str, Any], *, season: Optional[str] = None) -> str:
    """Append one JSON line to outputs/seasons/{season}/governance/ui_audit.jsonl; return path.
    
    Args:
        event: Audit event dictionary (must be JSON-serializable)
        season: Season identifier (e.g., "2026Q1"). If None, uses current season.
    
    Returns:
        Path to the audit log file.
    
    Raises:
        OSError: If file cannot be written.
    """
    # Ensure event has required fields
    if "ts" not in event:
        event["ts"] = datetime.now(timezone.utc).isoformat()
    if "actor" not in event:
        event["actor"] = "gui"
    
    # Get season directory
    season_path = season_dir(season)
    audit_dir = season_path / "governance"
    audit_dir.mkdir(parents=True, exist_ok=True)
    
    audit_path = audit_dir / "ui_audit.jsonl"
    
    # Append JSON line
    with open(audit_path, "a", encoding="utf-8") as f:
        json_line = json.dumps(event, ensure_ascii=False, separators=(",", ":"))
        f.write(json_line + "\n")
    
    return str(audit_path)


def read_audit_tail(season: Optional[str] = None, max_lines: int = 200) -> list[Dict[str, Any]]:
    """Read last N lines from audit log.
    
    Args:
        season: Season identifier (e.g., "2026Q1"). If None, uses current season.
        max_lines: Maximum number of lines to read.
    
    Returns:
        List of audit events (most recent first).
    """
    season_path = season_dir(season)
    audit_path = season_path / "governance" / "ui_audit.jsonl"
    
    if not audit_path.exists():
        return []
    
    # Read file and parse last N lines
    lines = []
    try:
        with open(audit_path, "r", encoding="utf-8") as f:
            # Read all lines efficiently for small files
            all_lines = f.readlines()
            # Take last max_lines
            tail_lines = all_lines[-max_lines:] if len(all_lines) > max_lines else all_lines
        
        for line in tail_lines:
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
                lines.append(event)
            except json.JSONDecodeError:
                # Skip malformed lines
                continue
    except (OSError, UnicodeDecodeError):
        return []
    
    # Return in chronological order (oldest first)
    return lines


def get_audit_events_for_run_id(run_id: str, season: Optional[str] = None, max_lines: int = 200) -> list[Dict[str, Any]]:
    """Filter audit events for a specific run_id.
    
    Args:
        run_id: Run ID to filter by.
        season: Season identifier (e.g., "2026Q1"). If None, uses current season.
        max_lines: Maximum number of lines to read from log.
    
    Returns:
        List of audit events related to the run_id.
    """
    all_events = read_audit_tail(season, max_lines)
    filtered = []
    
    for event in all_events:
        # Check if event is related to run_id
        inputs = event.get("inputs", {})
        artifacts = event.get("artifacts_written", [])
        
        # Check inputs for run_id
        if isinstance(inputs, dict) and inputs.get("run_id") == run_id:
            filtered.append(event)
            continue
        
        # Check artifacts for run_id pattern
        if isinstance(artifacts, list):
            for artifact in artifacts:
                if run_id in str(artifact):
                    filtered.append(event)
                    break
    
    return filtered