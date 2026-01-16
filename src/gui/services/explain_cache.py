from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Dict, Optional

from gui.services.supervisor_client import get_client, SupervisorClient

DEFAULT_TTL_SECONDS = 2.0


@dataclass
class _ExplainCacheEntry:
    payload: Dict[str, Any]
    expires_at: float


class ExplainCache:
    """In-process TTL cache for job explain payloads."""

    def __init__(self, client: Optional[SupervisorClient] = None, ttl_seconds: float = DEFAULT_TTL_SECONDS):
        self.client = client or get_client()
        self.ttl_seconds = ttl_seconds
        self._cache: Dict[str, _ExplainCacheEntry] = {}

    def get(self, job_id: str) -> Dict[str, Any]:
        now = time.monotonic()
        entry = self._cache.get(job_id)
        if entry and entry.expires_at > now:
            return entry.payload

        payload = self.client.get_job_explain(job_id)
        self._cache[job_id] = _ExplainCacheEntry(payload=payload, expires_at=now + self.ttl_seconds)
        return payload

    def clear(self) -> None:
        """Clear the entire cache."""
        self._cache.clear()


# Singleton instance shared by GUI services
_explain_cache = ExplainCache()


def get_job_explain(job_id: str) -> Dict[str, Any]:
    """Return cached explain payload for the job."""
    return _explain_cache.get(job_id)


def get_cache_instance() -> ExplainCache:
    return _explain_cache
