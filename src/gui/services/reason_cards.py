"""
Reason Cards for explainable WARNs/FAILs.

Provides a structured datamodel for presenting actionable, SSOT-backed "Reason Cards"
that clearly state why a WARN/FAIL happened, its impact, and recommended action.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class ReasonCard:
    """A single explainable reason card for a WARN or FAIL."""
    code: str
    title: str
    severity: Literal["WARN", "FAIL"]
    why: str
    impact: str
    recommended_action: str
    evidence_artifact: str  # e.g., "data_alignment_report.json"
    evidence_path: str      # e.g., "$.forward_fill_ratio" or "$.dropped_rows"
    action_target: str      # url/path to open artifact or location