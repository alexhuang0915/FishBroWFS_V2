"""Session Profile and K-Bar Aggregation module.

Phase 6.6: Session Profile + K-Bar Aggregation with DST-safe timezone conversion.
Session classification and K-bar aggregation use exchange clock.
Raw ingest (Phase 6.5) remains unchanged - no timezone conversion at raw layer.
"""

from data.session.classify import classify_session, classify_sessions
from data.session.kbar import aggregate_kbar
from data.session.loader import load_session_profile
from data.session.schema import Session, SessionProfile, SessionWindow

__all__ = [
    "Session",
    "SessionProfile",
    "SessionWindow",
    "load_session_profile",
    "classify_session",
    "classify_sessions",
    "aggregate_kbar",
]
