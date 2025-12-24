"""
Season State Management - Freeze governance lock.

Phase 5: Deterministic Governance & Reproducibility Lock.
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, Optional, Literal, TypedDict
from dataclasses import dataclass, asdict

from .season_context import season_dir


class SeasonStateDict(TypedDict, total=False):
    """Season state schema (immutable)."""
    season: str
    state: Literal["OPEN", "FROZEN"]
    frozen_ts: Optional[str]  # ISO-8601 or null
    frozen_by: Optional[Literal["gui", "cli", "system"]]  # or null
    reason: Optional[str]  # string or null


@dataclass
class SeasonState:
    """Season state data class."""
    season: str
    state: Literal["OPEN", "FROZEN"] = "OPEN"
    frozen_ts: Optional[str] = None  # ISO-8601 or null
    frozen_by: Optional[Literal["gui", "cli", "system"]] = None  # or null
    reason: Optional[str] = None  # string or null
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SeasonState":
        """Create SeasonState from dictionary."""
        return cls(
            season=data["season"],
            state=data.get("state", "OPEN"),
            frozen_ts=data.get("frozen_ts"),
            frozen_by=data.get("frozen_by"),
            reason=data.get("reason"),
        )
    
    def to_dict(self) -> SeasonStateDict:
        """Convert to dictionary."""
        return {
            "season": self.season,
            "state": self.state,
            "frozen_ts": self.frozen_ts,
            "frozen_by": self.frozen_by,
            "reason": self.reason,
        }
    
    def is_frozen(self) -> bool:
        """Check if season is frozen."""
        return self.state == "FROZEN"
    
    def freeze(self, by: Literal["gui", "cli", "system"], reason: Optional[str] = None) -> None:
        """Freeze the season."""
        if self.is_frozen():
            raise ValueError(f"Season {self.season} is already frozen")
        
        self.state = "FROZEN"
        self.frozen_ts = datetime.now(timezone.utc).isoformat()
        self.frozen_by = by
        self.reason = reason
    
    def unfreeze(self, by: Literal["gui", "cli", "system"], reason: Optional[str] = None) -> None:
        """Unfreeze the season."""
        if not self.is_frozen():
            raise ValueError(f"Season {self.season} is not frozen")
        
        self.state = "OPEN"
        self.frozen_ts = None
        self.frozen_by = None
        self.reason = None


def get_season_state_path(season: Optional[str] = None) -> Path:
    """Get path to season_state.json."""
    season_path = season_dir(season)
    governance_dir = season_path / "governance"
    governance_dir.mkdir(parents=True, exist_ok=True)
    return governance_dir / "season_state.json"


def load_season_state(season: Optional[str] = None) -> SeasonState:
    """Load season state from file, or create default if not exists."""
    state_path = get_season_state_path(season)
    
    if not state_path.exists():
        # Get season from context if not provided
        if season is None:
            from .season_context import current_season
            season_str = current_season()
        else:
            season_str = season
        
        # Create default OPEN state
        state = SeasonState(season=season_str, state="OPEN")
        save_season_state(state, season)
        return state
    
    try:
        with open(state_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        # Validate required fields
        if "season" not in data:
            # Infer season from path
            if season is None:
                from .season_context import current_season
                season_str = current_season()
            else:
                season_str = season
            data["season"] = season_str
        
        return SeasonState.from_dict(data)
    except (json.JSONDecodeError, OSError, KeyError) as e:
        # If file is corrupted, create default
        if season is None:
            from .season_context import current_season
            season_str = current_season()
        else:
            season_str = season
        
        state = SeasonState(season=season_str, state="OPEN")
        save_season_state(state, season)
        return state


def save_season_state(state: SeasonState, season: Optional[str] = None) -> Path:
    """Save season state to file."""
    state_path = get_season_state_path(season)
    
    # Ensure directory exists
    state_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Convert to dict and write
    data = state.to_dict()
    
    # Write atomically
    temp_path = state_path.with_suffix(".tmp")
    with open(temp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    
    # Replace original
    temp_path.replace(state_path)
    
    return state_path


def check_season_not_frozen(season: Optional[str] = None, action: str = "action") -> None:
    """
    Check if season is not frozen, raise ValueError if frozen.
    
    Args:
        season: Season identifier (e.g., "2026Q1"). If None, uses current season.
        action: Action name for error message.
    
    Raises:
        ValueError: If season is frozen.
    """
    state = load_season_state(season)
    if state.is_frozen():
        frozen_info = f"frozen at {state.frozen_ts} by {state.frozen_by}"
        if state.reason:
            frozen_info += f" (reason: {state.reason})"
        raise ValueError(
            f"Cannot perform {action}: Season {state.season} is {frozen_info}"
        )


def freeze_season(
    season: Optional[str] = None,
    by: Literal["gui", "cli", "system"] = "system",
    reason: Optional[str] = None,
    create_snapshot: bool = True,
) -> SeasonState:
    """
    Freeze a season.
    
    Args:
        season: Season identifier (e.g., "2026Q1"). If None, uses current season.
        by: Who is freezing the season.
        reason: Optional reason for freezing.
        create_snapshot: Whether to create deterministic snapshot of artifacts.
    
    Returns:
        Updated SeasonState.
    """
    state = load_season_state(season)
    state.freeze(by=by, reason=reason)
    save_season_state(state, season)
    
    # Phase 5: Create deterministic snapshot
    if create_snapshot:
        try:
            from .snapshot import create_freeze_snapshot
            snapshot_path = create_freeze_snapshot(state.season)
            # Log snapshot creation (optional)
            print(f"Created freeze snapshot: {snapshot_path}")
        except Exception as e:
            # Don't fail freeze if snapshot fails, but log warning
            print(f"Warning: Failed to create freeze snapshot: {e}")
    
    return state


def unfreeze_season(
    season: Optional[str] = None,
    by: Literal["gui", "cli", "system"] = "system",
    reason: Optional[str] = None,
) -> SeasonState:
    """
    Unfreeze a season.
    
    Args:
        season: Season identifier (e.g., "2026Q1"). If None, uses current season.
        by: Who is unfreezing the season.
        reason: Optional reason for unfreezing.
    
    Returns:
        Updated SeasonState.
    """
    state = load_season_state(season)
    state.unfreeze(by=by, reason=reason)
    save_season_state(state, season)
    return state