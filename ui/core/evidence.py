"""EvidenceLink for tracing KPI sources.

Immutable dataclass used by both UI and VM layers.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EvidenceLink:
    """
    Immutable evidence link pointing to a specific KPI value.
    
    Used to trace any KPI back to its source artifact and JSON pointer.
    """
    source_path: str  # Path to source artifact file (e.g., "winners_v2.json")
    json_pointer: str  # JSON pointer to the value (e.g., "/rows/0/net_profit")
    note: str = ""  # Optional human-readable note
