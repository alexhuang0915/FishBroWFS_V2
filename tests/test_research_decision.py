
"""Tests for research decision module."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from FishBroWFS_V2.research.decision import append_decision, load_decisions


def test_append_decision_new(tmp_path: Path) -> None:
    """Test appending a new decision."""
    out_dir = tmp_path / "research"
    
    log_path = append_decision(out_dir, "test-run-123", "KEEP", "Good results")
    
    # Verify log file exists
    assert log_path.exists()
    
    # Verify log content (JSONL)
    with open(log_path, "r", encoding="utf-8") as f:
        lines = [line.strip() for line in f if line.strip()]
        assert len(lines) == 1
        entry = json.loads(lines[0])
        assert entry["run_id"] == "test-run-123"
        assert entry["decision"] == "KEEP"
        assert entry["note"] == "Good results"
        assert "decided_at" in entry


def test_append_decision_multiple(tmp_path: Path) -> None:
    """Test appending multiple decisions (same run_id allowed)."""
    out_dir = tmp_path / "research"
    
    # Append first decision
    log_path = append_decision(out_dir, "test-run-123", "KEEP", "First decision")
    
    # Append second decision (same run_id, different decision)
    append_decision(out_dir, "test-run-123", "DROP", "Changed mind")
    
    # Verify log has 2 lines
    with open(log_path, "r", encoding="utf-8") as f:
        lines = [line.strip() for line in f if line.strip()]
        assert len(lines) == 2
    
    # Verify both entries exist
    entries = []
    with open(log_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                entries.append(json.loads(line))
    
    assert len(entries) == 2
    assert entries[0]["decision"] == "KEEP"
    assert entries[1]["decision"] == "DROP"
    assert entries[1]["run_id"] == "test-run-123"


def test_load_decisions_empty(tmp_path: Path) -> None:
    """Test loading decisions when log doesn't exist."""
    out_dir = tmp_path / "research"
    
    decisions = load_decisions(out_dir)
    assert decisions == []


def test_load_decisions_multiple(tmp_path: Path) -> None:
    """Test loading multiple decisions."""
    out_dir = tmp_path / "research"
    
    # Append multiple decisions
    append_decision(out_dir, "run-1", "KEEP", "Note 1")
    append_decision(out_dir, "run-2", "DROP", "Note 2")
    append_decision(out_dir, "run-3", "ARCHIVE", "Note 3")
    
    # Load decisions
    decisions = load_decisions(out_dir)
    
    assert len(decisions) == 3
    
    # Verify all decisions are present
    run_ids = {d["run_id"] for d in decisions}
    assert run_ids == {"run-1", "run-2", "run-3"}
    
    # Verify decisions
    decision_map = {d["run_id"]: d["decision"] for d in decisions}
    assert decision_map["run-1"] == "KEEP"
    assert decision_map["run-2"] == "DROP"
    assert decision_map["run-3"] == "ARCHIVE"


def test_load_decisions_same_run_multiple_times(tmp_path: Path) -> None:
    """Test loading decisions when same run_id appears multiple times."""
    out_dir = tmp_path / "research"
    
    # Append same run_id multiple times
    append_decision(out_dir, "run-1", "KEEP", "First")
    append_decision(out_dir, "run-1", "DROP", "Second")
    append_decision(out_dir, "run-1", "ARCHIVE", "Third")
    
    # Load decisions - should return all entries
    decisions = load_decisions(out_dir)
    
    assert len(decisions) == 3
    # All should have same run_id
    assert all(d["run_id"] == "run-1" for d in decisions)
    # Decisions should be in order
    assert decisions[0]["decision"] == "KEEP"
    assert decisions[1]["decision"] == "DROP"
    assert decisions[2]["decision"] == "ARCHIVE"


