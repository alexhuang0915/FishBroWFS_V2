"""
WorkerBridge - Single audited gateway for UI pages to access worker status and control.

UI pages must ONLY call methods on this class; no direct ControlAPIClient.get()/.post() calls.
This eliminates "whack-a-mole" NameErrors by providing a stable, validated contract.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, Optional, Tuple
from dataclasses import dataclass

from FishBroWFS_V2.gui.adapters.control_client import get_control_client, ControlAPIError

logger = logging.getLogger(__name__)


def _get_control_client_safe():
    """Get ControlAPIClient instance safely for use by other bridges."""
    return get_control_client()


@dataclass(frozen=True)
class WorkerStatus:
    """Worker status data structure."""
    alive: bool
    pid: Optional[int]
    reason: str
    heartbeat_age_sec: Optional[float]
    can_spawn: bool
    error: Optional[str] = None


@dataclass(frozen=True)
class WorkerStopResult:
    """Result of worker stop operation."""
    stopped: bool
    message: str
    error: Optional[str] = None


class WorkerBridgeError(RuntimeError):
    """Raised when WorkerBridge encounters an error."""
    pass


class WorkerBridge:
    """
    Single audited gateway for UI pages to access worker status and control.
    
    UI pages must ONLY call methods on this class; no direct ControlAPIClient.get()/.post() calls.
    All methods are synchronous for UI compatibility.
    """
    
    def __init__(self, client_factory=get_control_client):
        """
        Initialize with a client factory.
        
        Args:
            client_factory: Function that returns a ControlAPIClient instance.
        """
        self._client_factory = client_factory
        self._client = None
    
    def _get_client(self):
        """Get or create ControlAPIClient instance."""
        if self._client is None:
            self._client = self._client_factory()
        return self._client
    
    def _run_async(self, coro):
        """Run async coroutine synchronously for UI compatibility."""
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            # Create new event loop if none exists
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        return loop.run_until_complete(coro)
    
    def get_worker_status(self) -> WorkerStatus:
        """
        Get worker daemon status.
        
        Returns:
            WorkerStatus object with worker state.
            
        Raises:
            WorkerBridgeError: If unable to communicate with Control API.
        """
        try:
            client = self._get_client()
            data = self._run_async(client.worker_status())
            
            return WorkerStatus(
                alive=data.get("alive", False),
                pid=data.get("pid"),
                reason=data.get("reason", "unknown"),
                heartbeat_age_sec=data.get("last_heartbeat_age_sec"),
                can_spawn=data.get("can_spawn", False)
            )
        except ControlAPIError as e:
            logger.warning(f"Control API error getting worker status: {e}")
            return WorkerStatus(
                alive=False,
                pid=None,
                reason=f"API error: {e.status_code}",
                heartbeat_age_sec=None,
                can_spawn=False,
                error=str(e)
            )
        except Exception as e:
            logger.exception("Unexpected error getting worker status")
            return WorkerStatus(
                alive=False,
                pid=None,
                reason=f"Unexpected error: {str(e)}",
                heartbeat_age_sec=None,
                can_spawn=False,
                error=str(e)
            )
    
    def stop_worker(self, force: bool = True, reason: str = "") -> WorkerStopResult:
        """
        Stop worker daemon.
        
        Args:
            force: Whether to force stop (SIGKILL after timeout).
            reason: Optional reason for stopping.
            
        Returns:
            WorkerStopResult object with stop operation result.
            
        Raises:
            WorkerBridgeError: If unable to communicate with Control API.
        """
        try:
            client = self._get_client()
            data = self._run_async(client.worker_stop(force=force, reason=reason))
            
            return WorkerStopResult(
                stopped=data.get("stopped", False),
                message=data.get("message", "Stop command sent"),
                error=data.get("error")
            )
        except ControlAPIError as e:
            logger.warning(f"Control API error stopping worker: {e}")
            return WorkerStopResult(
                stopped=False,
                message=f"API error: {e.status_code}",
                error=str(e)
            )
        except Exception as e:
            logger.exception("Unexpected error stopping worker")
            return WorkerStopResult(
                stopped=False,
                message=f"Unexpected error: {str(e)}",
                error=str(e)
            )
    
    def is_worker_alive(self) -> bool:
        """
        Quick check if worker is alive.
        
        Returns:
            True if worker is alive, False otherwise.
        """
        status = self.get_worker_status()
        return status.alive
    
    def get_worker_status_dict(self) -> Dict[str, Any]:
        """
        Get worker status as dictionary for UI display.
        
        Returns:
            Dictionary with worker status information.
        """
        status = self.get_worker_status()
        return {
            "alive": status.alive,
            "pid": status.pid,
            "reason": status.reason,
            "heartbeat_age_sec": status.heartbeat_age_sec,
            "can_spawn": status.can_spawn,
            "error": status.error
        }


# Singleton instance
_worker_bridge_instance: Optional[WorkerBridge] = None


def get_worker_bridge() -> WorkerBridge:
    """
    Get singleton WorkerBridge instance.
    
    This is the main entry point for UI pages.
    
    Returns:
        WorkerBridge instance.
    """
    global _worker_bridge_instance
    if _worker_bridge_instance is None:
        _worker_bridge_instance = WorkerBridge()
    return _worker_bridge_instance


def reset_worker_bridge() -> None:
    """Reset the singleton WorkerBridge instance (for testing)."""
    global _worker_bridge_instance
    _worker_bridge_instance = None