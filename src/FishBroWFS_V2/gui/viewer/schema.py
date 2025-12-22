
"""Viewer schema definitions.

Public types for Viewer and Audit schema.
"""

from __future__ import annotations

from pydantic import BaseModel


class EvidenceLink(BaseModel):
    """Evidence link pointing to a specific KPI value."""
    artifact: str  # Artifact name (e.g., "winners_v2", "governance")
    json_pointer: str  # JSON pointer to the value (e.g., "/summary/net_profit")
    description: str | None = None  # Optional human-readable description


