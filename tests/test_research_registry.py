"""Tests for research registry module."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from FishBroWFS_V2.research.registry import build_research_index


def test_build_research_index_empty(tmp_path: Path) -> None:
    """Test building index with empty outputs."""
    outputs_root = tmp_path / "outputs"
    outputs_root.mkdir()
    out_dir = tmp_path / "research"
    
    index_path = build_research_index(outputs_root, out_dir)
    
    # Verify files created
    assert index_path.exists()
    assert (out_dir / "canonical_results.json").exists()
    
    # Verify content
    with open(index_path, "r", encoding="utf-8") as f:
        index_data = json.load(f)
    
    assert index_data["total_runs"] == 0
    assert index_data["entries"] == []


def test_build_research_index_with_runs(tmp_path: Path) -> None:
    """Test building index with multiple runs, verify sorting."""
    outputs_root = tmp_path / "outputs"
    
    # Create two runs with different scores
    run1_dir = outputs_root / "seasons" / "2026Q1" / "runs" / "run-1"
    run1_dir.mkdir(parents=True)
    
    run2_dir = outputs_root / "seasons" / "2026Q1" / "runs" / "run-2"
    run2_dir.mkdir(parents=True)
    
    # Run 1: Higher score_final
    manifest1 = {
        "run_id": "run-1",
        "bars": 1000,
        "created_at": "2025-01-01T00:00:00Z",
    }
    with open(run1_dir / "manifest.json", "w", encoding="utf-8") as f:
        json.dump(manifest1, f)
    
    with open(run1_dir / "metrics.json", "w", encoding="utf-8") as f:
        json.dump({}, f)
    
    winners1 = {
        "schema": "v2",
        "topk": [
            {
                "candidate_id": "test:1",
                "metrics": {
                    "net_profit": 200.0,
                    "max_dd": -50.0,
                    "trades": 20,  # Higher trades -> higher score_final
                },
            },
        ],
    }
    with open(run1_dir / "winners.json", "w", encoding="utf-8") as f:
        json.dump(winners1, f)
    
    # Run 2: Lower score_final
    manifest2 = {
        "run_id": "run-2",
        "bars": 1000,
        "created_at": "2025-01-01T00:00:00Z",
    }
    with open(run2_dir / "manifest.json", "w", encoding="utf-8") as f:
        json.dump(manifest2, f)
    
    with open(run2_dir / "metrics.json", "w", encoding="utf-8") as f:
        json.dump({}, f)
    
    winners2 = {
        "schema": "v2",
        "topk": [
            {
                "candidate_id": "test:2",
                "metrics": {
                    "net_profit": 100.0,
                    "max_dd": -50.0,
                    "trades": 10,  # Lower trades -> lower score_final
                },
            },
        ],
    }
    with open(run2_dir / "winners.json", "w", encoding="utf-8") as f:
        json.dump(winners2, f)
    
    # Build index
    out_dir = tmp_path / "research"
    index_path = build_research_index(outputs_root, out_dir)
    
    # Verify files created
    assert index_path.exists()
    canonical_path = out_dir / "canonical_results.json"
    assert canonical_path.exists()
    
    # Verify canonical_results.json
    with open(canonical_path, "r", encoding="utf-8") as f:
        canonical_data = json.load(f)
    
    assert len(canonical_data) == 2
    
    # Verify research_index.json is sorted (score_final desc)
    with open(index_path, "r", encoding="utf-8") as f:
        index_data = json.load(f)
    
    assert index_data["total_runs"] == 2
    entries = index_data["entries"]
    assert len(entries) == 2
    
    # Verify sorting: run-1 should be first (higher score_final)
    assert entries[0]["run_id"] == "run-1"
    assert entries[1]["run_id"] == "run-2"
    assert entries[0]["score_final"] > entries[1]["score_final"]


def test_build_research_index_preserves_decisions(tmp_path: Path) -> None:
    """Test that building index preserves decisions from decisions.log."""
    outputs_root = tmp_path / "outputs"
    out_dir = tmp_path / "research"
    out_dir.mkdir()
    
    # Create a run
    run_dir = outputs_root / "seasons" / "2026Q1" / "runs" / "run-1"
    run_dir.mkdir(parents=True)
    
    manifest = {
        "run_id": "run-1",
        "bars": 1000,
        "created_at": "2025-01-01T00:00:00Z",
    }
    with open(run_dir / "manifest.json", "w", encoding="utf-8") as f:
        json.dump(manifest, f)
    
    with open(run_dir / "metrics.json", "w", encoding="utf-8") as f:
        json.dump({}, f)
    
    winners = {
        "schema": "v2",
        "topk": [
            {
                "candidate_id": "test:1",
                "metrics": {
                    "net_profit": 100.0,
                    "max_dd": -50.0,
                    "trades": 10,
                },
            },
        ],
    }
    with open(run_dir / "winners.json", "w", encoding="utf-8") as f:
        json.dump(winners, f)
    
    # Add a decision
    from FishBroWFS_V2.research.decision import append_decision
    
    append_decision(out_dir, "run-1", "KEEP", "Good results")
    
    # Build index
    index_path = build_research_index(outputs_root, out_dir)
    
    # Verify decision is preserved
    with open(index_path, "r", encoding="utf-8") as f:
        index_data = json.load(f)
    
    assert index_data["entries"][0]["decision"] == "KEEP"
