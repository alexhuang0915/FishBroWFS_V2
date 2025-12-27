"""Session Profile schema.

Phase 6.6: Session Profile schema with DST-safe timezone conversion.
Session times are defined in exchange timezone, classification uses exchange clock.

Supports two modes:
- FIXED_TPE: Direct Taiwan time string comparison (e.g., TWF.MXF)
- EXCHANGE_RULE: Exchange timezone + rules, dynamically compute TPE windows (e.g., CME.MNQ)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal


@dataclass(frozen=True)
class SessionWindow:
    """Session window definition with state.
    
    Phase 6.6: Only allows TRADING and BREAK states.
    Session times are defined in exchange timezone (format: "HH:MM:SS").
    
    Attributes:
        state: Session state - "TRADING" or "BREAK"
        start: Session start time (exchange timezone, "HH:MM:SS")
        end: Session end time (exchange timezone, "HH:MM:SS")
    """
    state: Literal["TRADING", "BREAK"]
    start: str  # Exchange timezone "HH:MM:SS"
    end: str    # Exchange timezone "HH:MM:SS"


@dataclass(frozen=True)
class Session:
    """Trading session definition.
    
    Session times are defined in exchange timezone (format: "HH:MM:SS").
    
    Attributes:
        name: Session name (e.g., "DAY", "NIGHT", "TRADING", "BREAK", "MAINTENANCE")
        start: Session start time (exchange timezone, "HH:MM:SS")
        end: Session end time (exchange timezone, "HH:MM:SS")
    """
    name: str
    start: str  # Exchange timezone "HH:MM:SS"
    end: str    # Exchange timezone "HH:MM:SS"


@dataclass(frozen=True)
class SessionProfile:
    """Session profile for a symbol.
    
    Contains trading sessions defined in exchange timezone.
    Classification converts local time to exchange time for comparison.
    
    Phase 6.6: data_tz defaults to "Asia/Taipei", exchange_tz must be specified.
    
    Attributes:
        symbol: Symbol identifier (e.g., "CME.MNQ", "TWF.MXF")
        version: Profile version (e.g., "v1", "v2")
        mode: Profile mode - "FIXED_TPE" (direct TPE comparison), "EXCHANGE_RULE" (exchange rules), or "tz_convert" (timezone conversion with BREAK priority)
        exchange_tz: Exchange timezone (IANA, e.g., "America/Chicago")
        data_tz: Data timezone (IANA, default: "Asia/Taipei")
        local_tz: Local timezone (default: "Asia/Taipei")
        sessions: List of trading sessions (for FIXED_TPE mode)
        windows: List of session windows with TRADING/BREAK states (Phase 6.6)
        rules: Exchange rules dict (for EXCHANGE_RULE mode, e.g., daily_maintenance, trading_week)
        break_start: BREAK session start time (HH:MM:SS in exchange timezone) for tz_convert mode
        break_end: BREAK session end time (HH:MM:SS in exchange timezone) for tz_convert mode
    """
    symbol: str
    version: str
    mode: Literal["FIXED_TPE", "EXCHANGE_RULE", "tz_convert"]
    exchange_tz: str  # IANA timezone (e.g., "America/Chicago") - required
    data_tz: str = "Asia/Taipei"  # Data timezone (default: "Asia/Taipei")
    local_tz: str = "Asia/Taipei"  # Default to Taiwan time
    sessions: List[Session] = field(default_factory=list)  # For FIXED_TPE mode
    windows: List[SessionWindow] = field(default_factory=list)  # Phase 6.6: Windows with TRADING/BREAK states
    rules: Dict[str, Any] = field(default_factory=dict)  # For EXCHANGE_RULE mode
    break_start: str | None = None  # BREAK start (HH:MM:SS in exchange timezone) for tz_convert mode
    break_end: str | None = None  # BREAK end (HH:MM:SS in exchange timezone) for tz_convert mode
    
    def _time_in_range(self, time_str: str, start: str, end: str) -> bool:
        """Check if time_str is within [start, end) using string comparison.
        
        Handles both normal sessions (start <= end) and overnight sessions (start > end).
        
        Args:
            time_str: Time to check ("HH:MM:SS") in exchange timezone
            start: Start time ("HH:MM:SS") in exchange timezone
            end: End time ("HH:MM:SS") in exchange timezone
            
        Returns:
            True if time_str falls within the session range
        """
        if start <= end:
            # Non-overnight session (e.g., DAY: 08:45:00 - 13:45:00)
            return start <= time_str < end
        else:
            # Overnight session (e.g., NIGHT: 21:00:00 - 06:00:00)
            # time_str >= start OR time_str < end
            return time_str >= start or time_str < end
