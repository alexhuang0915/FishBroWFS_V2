import pytest
import json
import logging
from pathlib import Path
from research.plateau import load_candidates_from_file, PlateauCandidate

def test_load_candidates_rejects_small_topk(tmp_path, caplog):
    """L2-1: Verify that loading a small Top-K winners file triggers a warning."""
    d = tmp_path / "research"
    d.mkdir()
    p = d / "winners.json"
    
    # Create small topk
    data = {
        "topk": [{"candidate_id": f"c{i}", "score": 1.0} for i in range(20)]
    }
    p.write_text(json.dumps(data))
    
    with caplog.at_level(logging.WARNING):
        candidates = load_candidates_from_file(p)
        assert len(candidates) == 20
        assert "Plateau detection running on small candidate set" in caplog.text

def test_load_candidates_accepts_plateau_candidates_list(tmp_path):
    """L2-1: Verify support for plateau_candidates.json format (broad list)."""
    d = tmp_path / "research"
    d.mkdir()
    p = d / "plateau_candidates.json"
    
    # Create broad list
    data = {"plateau_candidates": [{"candidate_id": f"c{i}", "score": 1.0} for i in range(100)]}
    p.write_text(json.dumps(data))
    
    candidates = load_candidates_from_file(p)
    assert len(candidates) == 100

def test_load_candidates_accepts_raw_list(tmp_path):
    """L2-1: Verify support for raw list format."""
    p = tmp_path / "candidates_list.json"
    data = [{"candidate_id": f"c{i}", "score": 1.0} for i in range(50)]
    p.write_text(json.dumps(data))
    
    candidates = load_candidates_from_file(p)
    assert len(candidates) == 50
