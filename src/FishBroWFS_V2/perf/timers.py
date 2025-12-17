"""
Perf Harness Timer Helper (P2-1.8)

Provides granular timing breakdown for kernel stages.
"""
from __future__ import annotations

import time
from typing import Dict


class PerfTimers:
    """
    Performance timer helper for granular breakdown.
    
    Supports multiple start/stop calls for the same timer name (accumulates).
    All timings are in seconds with '_s' suffix.
    """
    
    def __init__(self) -> None:
        self._accumulated: Dict[str, float] = {}
        self._active: Dict[str, float] = {}
    
    def start(self, name: str) -> None:
        """
        Start a timer. If already running, does nothing (no nested timing).
        """
        if name not in self._active:
            self._active[name] = time.perf_counter()
    
    def stop(self, name: str) -> None:
        """
        Stop a timer and accumulate the elapsed time.
        If timer was not started, does nothing.
        """
        if name in self._active:
            elapsed = time.perf_counter() - self._active[name]
            self._accumulated[name] = self._accumulated.get(name, 0.0) + elapsed
            del self._active[name]
    
    def as_dict_seconds(self) -> Dict[str, float]:
        """
        Return accumulated timings as dict with '_s' suffix keys.
        
        Returns:
            dict with keys like "t_xxx_s": float (seconds)
        """
        result: Dict[str, float] = {}
        for name, seconds in self._accumulated.items():
            # Ensure '_s' suffix
            key = name if name.endswith("_s") else f"{name}_s"
            result[key] = float(seconds)
        return result
    
    def get(self, name: str, default: float = 0.0) -> float:
        """
        Get accumulated time for a timer name.
        """
        return self._accumulated.get(name, default)
