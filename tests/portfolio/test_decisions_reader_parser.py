
"""Test decisions log parser.

Phase 11: Test tolerant parsing of decisions.log files.
"""

import pytest
from portfolio.decisions_reader import parse_decisions_log_lines


def test_parse_jsonl_normal():
    """Test normal JSONL parsing."""
    lines = [
        '{"run_id": "run1", "decision": "KEEP", "note": "Good results", "ts": "2024-01-01T00:00:00"}',
        '{"run_id": "run2", "decision": "DROP", "note": "Bad performance"}',
        '{"run_id": "run3", "decision": "ARCHIVE", "note": "For reference"}',
    ]
    
    results = parse_decisions_log_lines(lines)
    
    assert len(results) == 3
    
    # Check first entry
    assert results[0]["run_id"] == "run1"
    assert results[0]["decision"] == "KEEP"
    assert results[0]["note"] == "Good results"
    assert results[0]["ts"] == "2024-01-01T00:00:00"
    
    # Check second entry
    assert results[1]["run_id"] == "run2"
    assert results[1]["decision"] == "DROP"
    assert results[1]["note"] == "Bad performance"
    assert "ts" not in results[1]
    
    # Check third entry
    assert results[2]["run_id"] == "run3"
    assert results[2]["decision"] == "ARCHIVE"
    assert results[2]["note"] == "For reference"


def test_ignore_blank_lines():
    """Test that blank lines are ignored."""
    lines = [
        "",
        '{"run_id": "run1", "decision": "KEEP", "note": "Test"}',
        "   ",
        "\t\n",
        '{"run_id": "run2", "decision": "DROP", "note": ""}',
        "",
    ]
    
    results = parse_decisions_log_lines(lines)
    
    assert len(results) == 2
    assert results[0]["run_id"] == "run1"
    assert results[1]["run_id"] == "run2"


def test_parse_simple_format():
    """Test parsing of simple pipe-delimited format."""
    lines = [
        "run1|KEEP|Good results|2024-01-01",
        "run2|DROP|Bad performance",
        "run3|ARCHIVE||2024-01-02",
    ]
    
    results = parse_decisions_log_lines(lines)
    
    assert len(results) == 3
    
    # Check first entry
    assert results[0]["run_id"] == "run1"
    assert results[0]["decision"] == "KEEP"
    assert results[0]["note"] == "Good results"
    assert results[0]["ts"] == "2024-01-01"
    
    # Check second entry
    assert results[1]["run_id"] == "run2"
    assert results[1]["decision"] == "DROP"
    assert results[1]["note"] == "Bad performance"
    assert "ts" not in results[1]
    
    # Check third entry
    assert results[2]["run_id"] == "run3"
    assert results[2]["decision"] == "ARCHIVE"
    assert results[2]["note"] == ""
    assert results[2]["ts"] == "2024-01-02"


def test_bad_lines_ignored():
    """Test that bad lines are ignored without crashing."""
    lines = [
        '{"run_id": "run1", "decision": "KEEP"}',  # Good
        "not valid json",  # Bad
        "run2|KEEP",  # Good (simple format)
        "{invalid json}",  # Bad
        "",  # Blank
        "just a string",  # Bad
        '{"run_id": "run3", "decision": "DROP"}',  # Good
    ]
    
    results = parse_decisions_log_lines(lines)
    
    # Should parse 3 good lines
    assert len(results) == 3
    run_ids = {r["run_id"] for r in results}
    assert run_ids == {"run1", "run2", "run3"}


def test_note_trailing_spaces():
    """Test handling of trailing spaces in notes."""
    lines = [
        '{"run_id": "run1", "decision": "KEEP", "note": "  Good results  "}',
        "run2|KEEP|  Note with spaces  |2024-01-01",
    ]
    
    results = parse_decisions_log_lines(lines)
    
    assert len(results) == 2
    
    # JSONL: spaces should be stripped
    assert results[0]["run_id"] == "run1"
    assert results[0]["note"] == "Good results"
    
    # Simple format: spaces should be stripped
    assert results[1]["run_id"] == "run2"
    assert results[1]["note"] == "Note with spaces"


def test_decision_case_normalization():
    """Test that decision case is normalized to uppercase."""
    lines = [
        '{"run_id": "run1", "decision": "keep", "note": "lowercase"}',
        '{"run_id": "run2", "decision": "Keep", "note": "capitalized"}',
        '{"run_id": "run3", "decision": "KEEP", "note": "uppercase"}',
        "run4|drop|simple format",
    ]
    
    results = parse_decisions_log_lines(lines)
    
    assert len(results) == 4
    assert results[0]["decision"] == "KEEP"
    assert results[1]["decision"] == "KEEP"
    assert results[2]["decision"] == "KEEP"
    assert results[3]["decision"] == "DROP"


def test_missing_required_fields():
    """Test lines missing required fields are ignored."""
    lines = [
        '{"decision": "KEEP", "note": "Missing run_id"}',  # Missing run_id
        '{"run_id": "run2", "note": "Missing decision"}',  # Missing decision
        '{"run_id": "", "decision": "KEEP", "note": "Empty run_id"}',  # Empty run_id
        '{"run_id": "run3", "decision": "", "note": "Empty decision"}',  # Empty decision
        '{"run_id": "run4", "decision": "KEEP"}',  # Valid (note can be empty)
    ]
    
    results = parse_decisions_log_lines(lines)
    
    # Should only parse the valid line
    assert len(results) == 1
    assert results[0]["run_id"] == "run4"
    assert results[0]["decision"] == "KEEP"
    assert results[0]["note"] == ""


def test_mixed_formats():
    """Test parsing mixed JSONL and simple format lines."""
    lines = [
        '{"run_id": "run1", "decision": "KEEP", "note": "JSONL"}',
        "run2|DROP|Simple format",
        '{"run_id": "run3", "decision": "ARCHIVE", "note": "JSONL again"}',
        "run4|KEEP|Another simple|2024-01-01",
    ]
    
    results = parse_decisions_log_lines(lines)
    
    assert len(results) == 4
    assert results[0]["run_id"] == "run1"
    assert results[0]["decision"] == "KEEP"
    assert results[1]["run_id"] == "run2"
    assert results[1]["decision"] == "DROP"
    assert results[2]["run_id"] == "run3"
    assert results[2]["decision"] == "ARCHIVE"
    assert results[3]["run_id"] == "run4"
    assert results[3]["decision"] == "KEEP"
    assert results[3]["ts"] == "2024-01-01"


def test_deterministic_parsing():
    """Test that parsing is deterministic (same lines → same results)."""
    lines = [
        "",
        '{"run_id": "run1", "decision": "KEEP", "note": "Test"}',
        "run2|DROP|Note",
        "   ",
        '{"run_id": "run3", "decision": "ARCHIVE"}',
    ]
    
    # Parse multiple times
    results1 = parse_decisions_log_lines(lines)
    results2 = parse_decisions_log_lines(lines)
    results3 = parse_decisions_log_lines(lines)
    
    # All results should be identical
    assert results1 == results2 == results3
    assert len(results1) == 3
    
    # Verify order is preserved
    assert results1[0]["run_id"] == "run1"
    assert results1[1]["run_id"] == "run2"
    assert results1[2]["run_id"] == "run3"


