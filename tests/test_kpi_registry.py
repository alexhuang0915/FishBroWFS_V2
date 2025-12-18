"""Tests for KPI Registry.

Tests registry key → EvidenceLink mapping and defensive behavior.
"""

from __future__ import annotations

import pytest

from FishBroWFS_V2.gui.viewer.kpi_registry import (
    KPI_EVIDENCE_REGISTRY,
    get_evidence_link,
    has_evidence,
    EvidenceLink,
)


def test_registry_keys_exist() -> None:
    """Test that registry keys map to correct EvidenceLink."""
    # Test net_profit
    link = get_evidence_link("net_profit")
    assert link is not None
    assert link.artifact == "winners_v2"
    assert link.json_pointer == "/summary/net_profit"
    assert "profit" in link.description.lower()
    
    # Test max_drawdown
    link = get_evidence_link("max_drawdown")
    assert link is not None
    assert link.artifact == "winners_v2"
    assert link.json_pointer == "/summary/max_drawdown"
    
    # Test num_trades
    link = get_evidence_link("num_trades")
    assert link is not None
    assert link.artifact == "winners_v2"
    assert link.json_pointer == "/summary/num_trades"
    
    # Test final_score
    link = get_evidence_link("final_score")
    assert link is not None
    assert link.artifact == "governance"
    assert link.json_pointer == "/scoring/final_score"


def test_unknown_kpi_returns_none() -> None:
    """Test that unknown KPI names return None without crashing."""
    link = get_evidence_link("unknown_kpi")
    assert link is None
    
    link = get_evidence_link("")
    assert link is None
    
    link = get_evidence_link("nonexistent")
    assert link is None


def test_has_evidence() -> None:
    """Test has_evidence function."""
    assert has_evidence("net_profit") is True
    assert has_evidence("max_drawdown") is True
    assert has_evidence("num_trades") is True
    assert has_evidence("final_score") is True
    
    assert has_evidence("unknown_kpi") is False
    assert has_evidence("") is False


def test_registry_never_raises() -> None:
    """Test that registry functions never raise exceptions."""
    # Test with invalid input types
    try:
        get_evidence_link(None)  # type: ignore
    except Exception:
        pytest.fail("get_evidence_link should not raise")
    
    try:
        has_evidence(None)  # type: ignore
    except Exception:
        pytest.fail("has_evidence should not raise")


def test_registry_structure() -> None:
    """Test that registry has correct structure."""
    assert isinstance(KPI_EVIDENCE_REGISTRY, dict)
    assert len(KPI_EVIDENCE_REGISTRY) > 0
    
    for kpi_name, link in KPI_EVIDENCE_REGISTRY.items():
        assert isinstance(kpi_name, str)
        assert isinstance(link, EvidenceLink)
        assert link.artifact in ("manifest", "winners_v2", "governance")
        assert link.json_pointer.startswith("/")
        assert isinstance(link.description, str)
