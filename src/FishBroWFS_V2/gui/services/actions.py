"""
UI Actions Service - Single entry point for UI-triggered actions.

Phase 4: UI must trigger actions via this service, not direct subprocess calls.
Phase 5: Respect season freeze state - actions cannot run on frozen seasons.
"""

import json
import os
import subprocess
import sys
import tempfile
import threading
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import List, Literal, Optional, Dict, Any

from FishBroWFS_V2.core.season_context import current_season, outputs_root
from FishBroWFS_V2.core.season_state import check_season_not_frozen
from .audit_log import append_audit_event


ActionName = Literal[
    "generate_research",
    "build_portfolio_from_research",
    "export_season_package",
]


class ActionStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"


@dataclass(frozen=True)
class ActionResult:
    """Result of an action execution."""
    ok: bool
    action: ActionName
    season: str
    started_ts: str
    finished_ts: str
    stdout_tail: List[str]
    stderr_tail: List[str]
    artifacts_written: List[str]
    audit_event_path: str


def _get_venv_python() -> Path:
    """Return path to venv python executable."""
    venv_python = Path(".venv/bin/python")
    if venv_python.exists():
        return venv_python
    
    # Fallback to system python if venv not found
    return Path(sys.executable)


def _run_subprocess_with_timeout(
    cmd: List[str],
    timeout_seconds: int = 300,
    cwd: Optional[Path] = None,
) -> tuple[int, List[str], List[str]]:
    """Run subprocess and capture stdout/stderr with timeout.
    
    Returns:
        Tuple of (exit_code, stdout_lines, stderr_lines)
    """
    if cwd is None:
        cwd = Path.cwd()
    
    try:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_seconds,
        )
        stdout_lines = result.stdout.splitlines() if result.stdout else []
        stderr_lines = result.stderr.splitlines() if result.stderr else []
        return result.returncode, stdout_lines, stderr_lines
    except subprocess.TimeoutExpired:
        return -1, ["Action timed out"], ["Timeout after {} seconds".format(timeout_seconds)]
    except Exception as e:
        return -2, [], [f"Subprocess error: {str(e)}"]


def _tail_lines(lines: List[str], max_lines: int = 200) -> List[str]:
    """Return last N lines from list."""
    return lines[-max_lines:] if len(lines) > max_lines else lines


def _build_action_command(action: ActionName, season: str, legacy_copy: bool = False) -> List[str]:
    """Build command line for the given action."""
    venv_python = _get_venv_python()
    cmd = [str(venv_python)]
    
    if action == "generate_research":
        cmd.extend([
            "-m", "scripts.generate_research",
            "--season", season,
            "--outputs-root", outputs_root(),
        ])
        if legacy_copy:
            cmd.append("--legacy-copy")
    
    elif action == "build_portfolio_from_research":
        cmd.extend([
            "-m", "scripts.build_portfolio_from_research",
            "--season", season,
            "--outputs-root", outputs_root(),
        ])
    
    elif action == "export_season_package":
        # Placeholder for future export functionality
        cmd.extend([
            "-c", "print('Export season package not yet implemented')"
        ])
    
    else:
        raise ValueError(f"Unknown action: {action}")
    
    return cmd


def _collect_artifacts(action: ActionName, season: str) -> List[str]:
    """Collect key artifact paths written by the action."""
    season_dir = Path(outputs_root()) / "seasons" / season
    artifacts = []
    
    if action == "generate_research":
        research_dir = season_dir / "research"
        if research_dir.exists():
            for file in ["canonical_results.json", "research_index.json"]:
                path = research_dir / file
                if path.exists():
                    artifacts.append(str(path))
    
    elif action == "build_portfolio_from_research":
        portfolio_dir = season_dir / "portfolio"
        if portfolio_dir.exists():
            for file in ["portfolio_summary.json", "portfolio_manifest.json"]:
                path = portfolio_dir / file
                if path.exists():
                    artifacts.append(str(path))
            # Also include run-specific directories
            for item in portfolio_dir.iterdir():
                if item.is_dir() and len(item.name) == 12:  # portfolio_id pattern
                    for spec_file in ["portfolio_spec.json", "portfolio_manifest.json"]:
                        spec_path = item / spec_file
                        if spec_path.exists():
                            artifacts.append(str(spec_path))
    
    return artifacts


def run_action(
    action: ActionName,
    season: Optional[str] = None,
    *,
    legacy_copy: bool = False,
    timeout_seconds: int = 300,
    check_integrity: bool = True,
) -> ActionResult:
    """
    Runs the action via subprocess using venv python.
    
    Must be deterministic in its file outputs given same inputs.
    Must write audit event jsonl for every action (success or fail).
    
    Phase 5: First line checks season freeze state - cannot run on frozen seasons.
    Phase 5: Optional integrity check for frozen seasons.
    
    Args:
        action: Action name.
        season: Season identifier (e.g., "2026Q1"). If None, uses current season.
        legacy_copy: Whether to enable legacy copy for generate_research.
        timeout_seconds: Timeout for subprocess execution.
        check_integrity: Whether to verify season integrity before action (for frozen seasons).
    
    Returns:
        ActionResult with execution details.
    """
    # Phase 5: Check season freeze state before any action
    check_season_not_frozen(season, action=action)
    
    # Phase 5: Optional integrity check for frozen seasons
    if check_integrity:
        try:
            from FishBroWFS_V2.core.season_state import load_season_state
            from FishBroWFS_V2.core.snapshot import verify_snapshot_integrity
            
            season_str = season or current_season()
            state = load_season_state(season_str)
            if state.is_frozen():
                # Season is frozen, verify integrity
                integrity_result = verify_snapshot_integrity(season_str)
                if not integrity_result["ok"]:
                    # Log integrity violation but don't block action (frozen season already blocks)
                    print(f"WARNING: Season {season_str} integrity check failed for frozen season")
                    print(f"  Missing files: {len(integrity_result['missing_files'])}")
                    print(f"  Changed files: {len(integrity_result['changed_files'])}")
        except ImportError:
            # snapshot module may not be available in older versions
            pass
        except Exception as e:
            # Don't fail action on integrity check errors
            print(f"WARNING: Integrity check failed: {e}")
    
    if season is None:
        season = current_season()
    
    started_ts = datetime.now(timezone.utc).isoformat()
    
    # Build command
    cmd = _build_action_command(action, season, legacy_copy)
    
    # Run subprocess
    exit_code, stdout_lines, stderr_lines = _run_subprocess_with_timeout(
        cmd, timeout_seconds=timeout_seconds
    )
    
    finished_ts = datetime.now(timezone.utc).isoformat()
    ok = exit_code == 0
    
    # Collect artifacts
    artifacts_written = _collect_artifacts(action, season) if ok else []
    
    # Prepare audit event
    audit_event = {
        "ts": finished_ts,
        "actor": "gui",
        "action": action,
        "season": season,
        "ok": ok,
        "exit_code": exit_code,
        "inputs": {
            "action": action,
            "season": season,
            "legacy_copy": legacy_copy,
            "timeout_seconds": timeout_seconds,
        },
        "artifacts_written": artifacts_written,
    }
    
    if not ok:
        audit_event["error"] = {
            "exit_code": exit_code,
            "stderr_tail": _tail_lines(stderr_lines, 10),
        }
    
    # Write audit log
    audit_event_path = append_audit_event(audit_event, season=season)
    
    # Create result
    result = ActionResult(
        ok=ok,
        action=action,
        season=season,
        started_ts=started_ts,
        finished_ts=finished_ts,
        stdout_tail=_tail_lines(stdout_lines),
        stderr_tail=_tail_lines(stderr_lines),
        artifacts_written=artifacts_written,
        audit_event_path=audit_event_path,
    )
    
    return result


# Convenience functions for common actions
def generate_research(season: Optional[str] = None, legacy_copy: bool = False) -> ActionResult:
    """Generate research artifacts for a season."""
    return run_action("generate_research", season, legacy_copy=legacy_copy)


def build_portfolio_from_research(season: Optional[str] = None) -> ActionResult:
    """Build portfolio from research results."""
    return run_action("build_portfolio_from_research", season)


def get_action_status(action_id: str) -> Optional[Dict[str, Any]]:
    """Get status of a previously executed action (placeholder).
    
    Note: In a real implementation, this would track async actions.
    For now, actions are synchronous, so this returns None.
    """
    return None


def list_recent_actions(season: Optional[str] = None, limit: int = 20) -> List[Dict[str, Any]]:
    """List recent actions from audit log."""
    from .audit_log import read_audit_tail
    
    events = read_audit_tail(season, max_lines=limit * 2)  # Read extra to filter
    action_events = []
    
    for event in events:
        if event.get("actor") == "gui" and "action" in event:
            action_events.append(event)
            if len(action_events) >= limit:
                break
    
    return action_events