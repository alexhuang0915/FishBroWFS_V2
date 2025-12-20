"""Research Decision - manage KEEP/DROP/ARCHIVE decisions.

Phase 9: Append-only decision log with notes and timestamps.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Literal

DecisionType = Literal["KEEP", "DROP", "ARCHIVE"]


def append_decision(out_dir: Path, run_id: str, decision: DecisionType, note: str) -> Path:
    """
    Append a decision to decisions.log (JSONL format).
    
    Same run_id can have multiple decisions (append-only).
    The research_index.json will show the last decision (last-write-wins view).
    
    Args:
        out_dir: Research output directory
        run_id: Run ID
        decision: Decision type (KEEP, DROP, ARCHIVE)
        note: Note explaining the decision
        
    Returns:
        Path to decisions.log
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    
    # Append to log (JSONL format)
    decisions_log_path = out_dir / "decisions.log"
    
    decision_entry = {
        "run_id": run_id,
        "decision": decision,
        "note": note,
        "decided_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    
    with open(decisions_log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(decision_entry, ensure_ascii=False, sort_keys=True) + "\n")
    
    return decisions_log_path


def load_decisions(out_dir: Path) -> List[Dict[str, Any]]:
    """
    Load all decisions from decisions.log.
    
    Args:
        out_dir: Research output directory
        
    Returns:
        List of decision entries (all entries, including duplicates for same run_id)
    """
    decisions_log_path = out_dir / "decisions.log"
    
    if not decisions_log_path.exists():
        return []
    
    decisions = []
    try:
        with open(decisions_log_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    decisions.append(entry)
                except json.JSONDecodeError:
                    # Skip invalid lines
                    continue
    except Exception:
        pass
    
    return decisions
