from __future__ import annotations
import time
from typing import Any, Dict
from ..job_handler import BaseJobHandler, JobContext


class PingHandler(BaseJobHandler):
    """PING handler for testing."""
    
    def validate_params(self, params: Dict[str, Any]) -> None:
        """Validate PING parameters."""
        if "sleep_sec" in params:
            sleep_sec = params["sleep_sec"]
            if not isinstance(sleep_sec, (int, float)):
                raise ValueError("sleep_sec must be numeric")
            if sleep_sec < 0:
                raise ValueError("sleep_sec must be non-negative")
            if sleep_sec > 3600:
                raise ValueError("sleep_sec too large (max 3600)")
    
    def execute(self, params: Dict[str, Any], context: JobContext) -> Dict[str, Any]:
        """Execute PING job."""
        sleep_sec = params.get("sleep_sec", 0.1)
        increment = 0.1  # seconds between heartbeats
        
        elapsed = 0.0
        while elapsed < sleep_sec:
            # Check for abort request
            if context.is_abort_requested():
                return {"aborted": True, "elapsed": elapsed, "sleep_requested": sleep_sec}
            
            # Sleep in small increments
            chunk = min(increment, sleep_sec - elapsed)
            time.sleep(chunk)
            elapsed += chunk
            
            # Send heartbeat with progress
            progress = elapsed / sleep_sec if sleep_sec > 0 else 1.0
            context.heartbeat(progress=progress, phase=f"sleeping_{elapsed:.1f}s")
        
        return {"ok": True, "elapsed": elapsed, "sleep_requested": sleep_sec}


# Register handler
ping_handler = PingHandler()