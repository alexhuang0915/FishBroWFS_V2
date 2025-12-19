"""Session Profile loader.

Phase 6.6: Load session profiles from YAML files.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from FishBroWFS_V2.data.session.schema import Session, SessionProfile, SessionWindow


def load_session_profile(profile_path: Path) -> SessionProfile:
    """Load session profile from YAML file.
    
    Args:
        profile_path: Path to YAML profile file
        
    Returns:
        SessionProfile loaded from YAML
        
    Raises:
        FileNotFoundError: If profile file does not exist
        ValueError: If profile structure is invalid
    """
    if not profile_path.exists():
        raise FileNotFoundError(f"Session profile not found: {profile_path}")
    
    with profile_path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    
    if not isinstance(data, dict):
        raise ValueError(f"Invalid profile format: expected dict, got {type(data)}")
    
    symbol = data.get("symbol")
    version = data.get("version")
    mode = data.get("mode", "FIXED_TPE")  # Default to FIXED_TPE for backward compatibility
    exchange_tz = data.get("exchange_tz")
    data_tz = data.get("data_tz", "Asia/Taipei")  # Phase 6.6: Default to Asia/Taipei
    local_tz = data.get("local_tz", "Asia/Taipei")
    sessions_data = data.get("sessions", [])
    windows_data = data.get("windows", [])  # Phase 6.6: Windows with TRADING/BREAK states
    rules = data.get("rules", {})
    break_start = data.get("break", {}).get("start") if isinstance(data.get("break"), dict) else None
    break_end = data.get("break", {}).get("end") if isinstance(data.get("break"), dict) else None
    
    if not symbol:
        raise ValueError("Profile missing 'symbol' field")
    if not version:
        raise ValueError("Profile missing 'version' field")
    
    # Phase 6.6: exchange_tz is required
    if not exchange_tz:
        raise ValueError("Profile missing 'exchange_tz' field (required in Phase 6.6)")
    
    if mode not in ["FIXED_TPE", "EXCHANGE_RULE", "tz_convert"]:
        raise ValueError(f"Invalid mode: {mode}. Must be 'FIXED_TPE', 'EXCHANGE_RULE', or 'tz_convert'")
    
    # Phase 6.6: Load windows (preferred method)
    windows = []
    if windows_data:
        if not isinstance(windows_data, list):
            raise ValueError(f"Profile 'windows' must be list, got {type(windows_data)}")
        
        for win_data in windows_data:
            if not isinstance(win_data, dict):
                raise ValueError(f"Window must be dict, got {type(win_data)}")
            
            state = win_data.get("state")
            start = win_data.get("start")
            end = win_data.get("end")
            
            if state not in ["TRADING", "BREAK"]:
                raise ValueError(f"Window state must be 'TRADING' or 'BREAK', got {state}")
            if not start or not end:
                raise ValueError(f"Window missing required fields: state={state}, start={start}, end={end}")
            
            windows.append(SessionWindow(state=state, start=start, end=end))
    
    # Backward compatibility: Load sessions for legacy modes
    sessions = []
    if sessions_data:
        if not isinstance(sessions_data, list):
            raise ValueError(f"Profile 'sessions' must be list, got {type(sessions_data)}")
        
        for sess_data in sessions_data:
            if not isinstance(sess_data, dict):
                raise ValueError(f"Session must be dict, got {type(sess_data)}")
            
            name = sess_data.get("name")
            start = sess_data.get("start")
            end = sess_data.get("end")
            
            if not name or not start or not end:
                raise ValueError(f"Session missing required fields: name={name}, start={start}, end={end}")
            
            sessions.append(Session(name=name, start=start, end=end))
    elif mode == "EXCHANGE_RULE":
        if not isinstance(rules, dict):
            raise ValueError(f"Profile 'rules' must be dict for EXCHANGE_RULE mode, got {type(rules)}")
    elif mode == "tz_convert":
        # Legacy requirement only applies when windows are NOT provided
        # Phase 6.6: If windows_data exists, windows-driven mode doesn't need break.start/end
        if (not windows_data) and (not break_start or not break_end):
            raise ValueError(f"tz_convert mode requires 'break.start' and 'break.end' fields (or 'windows' for Phase 6.6)")
    
    return SessionProfile(
        symbol=symbol,
        version=version,
        mode=mode,
        exchange_tz=exchange_tz,
        data_tz=data_tz,
        local_tz=local_tz,
        sessions=sessions,
        windows=windows,
        rules=rules,
        break_start=break_start,
        break_end=break_end,
    )
