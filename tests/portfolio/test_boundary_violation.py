"""
Phase Portfolio Bridge: Boundary violation tests.

Tests that Research OS cannot leak trading details through CandidateSpec.
"""

import pytest

from FishBroWFS_V2.portfolio.candidate_spec import CandidateSpec, CandidateExport
from FishBroWFS_V2.portfolio.candidate_export import export_candidates, load_candidates


def test_candidate_spec_rejects_trading_details():
    """Test that CandidateSpec rejects metadata with trading details."""
    # Should succeed with non-trading metadata
    CandidateSpec(
        candidate_id="candidate1",
        strategy_id="sma_cross_v1",
        param_hash="abc123",
        research_score=1.5,
        metadata={"research_note": "good performance"},
    )
    
    # Should fail with trading details in metadata
    with pytest.raises(ValueError, match="boundary violation"):
        CandidateSpec(
            candidate_id="candidate2",
            strategy_id="sma_cross_v1",
            param_hash="abc123",
            research_score=1.5,
            metadata={"symbol": "CME.MNQ"},  # trading detail
        )
    
    with pytest.raises(ValueError, match="boundary violation"):
        CandidateSpec(
            candidate_id="candidate3",
            strategy_id="sma_cross_v1",
            param_hash="abc123",
            research_score=1.5,
            metadata={"timeframe": "60"},  # trading detail
        )
    
    with pytest.raises(ValueError, match="boundary violation"):
        CandidateSpec(
            candidate_id="candidate4",
            strategy_id="sma_cross_v1",
            param_hash="abc123",
            research_score=1.5,
            metadata={"session_profile": "CME_MNQ_v2"},  # trading detail
        )
    
    # Case-insensitive check
    with pytest.raises(ValueError, match="boundary violation"):
        CandidateSpec(
            candidate_id="candidate5",
            strategy_id="sma_cross_v1",
            param_hash="abc123",
            research_score=1.5,
            metadata={"TRADING": "yes"},  # uppercase
        )


def test_candidate_spec_validation():
    """Test CandidateSpec validation rules."""
    # Valid candidate
    CandidateSpec(
        candidate_id="candidate1",
        strategy_id="sma_cross_v1",
        param_hash="abc123",
        research_score=1.5,
        research_confidence=0.8,
    )
    
    # Invalid candidate_id
    with pytest.raises(ValueError, match="candidate_id cannot be empty"):
        CandidateSpec(
            candidate_id="",
            strategy_id="sma_cross_v1",
            param_hash="abc123",
            research_score=1.5,
        )
    
    # Invalid strategy_id
    with pytest.raises(ValueError, match="strategy_id cannot be empty"):
        CandidateSpec(
            candidate_id="candidate1",
            strategy_id="",
            param_hash="abc123",
            research_score=1.5,
        )
    
    # Invalid param_hash
    with pytest.raises(ValueError, match="param_hash cannot be empty"):
        CandidateSpec(
            candidate_id="candidate1",
            strategy_id="sma_cross_v1",
            param_hash="",
            research_score=1.5,
        )
    
    # Invalid research_score type
    with pytest.raises(ValueError, match="research_score must be numeric"):
        CandidateSpec(
            candidate_id="candidate1",
            strategy_id="sma_cross_v1",
            param_hash="abc123",
            research_score="high",  # string instead of number
        )
    
    # Invalid research_confidence range
    with pytest.raises(ValueError, match="research_confidence must be between"):
        CandidateSpec(
            candidate_id="candidate1",
            strategy_id="sma_cross_v1",
            param_hash="abc123",
            research_score=1.5,
            research_confidence=1.5,  # > 1.0
        )


def test_candidate_export_validation():
    """Test CandidateExport validation rules."""
    candidates = [
        CandidateSpec(
            candidate_id="candidate1",
            strategy_id="sma_cross_v1",
            param_hash="abc123",
            research_score=1.5,
        ),
        CandidateSpec(
            candidate_id="candidate2",
            strategy_id="mean_revert_v1",
            param_hash="def456",
            research_score=1.2,
        ),
    ]
    
    # Valid export
    CandidateExport(
        export_id="export1",
        generated_at="2025-12-21T00:00:00Z",
        season="2026Q1",
        candidates=candidates,
    )
    
    # Duplicate candidate_id
    with pytest.raises(ValueError, match="Duplicate candidate_id"):
        CandidateExport(
            export_id="export2",
            generated_at="2025-12-21T00:00:00Z",
            season="2026Q1",
            candidates=[
                CandidateSpec(
                    candidate_id="duplicate",
                    strategy_id="sma_cross_v1",
                    param_hash="abc123",
                    research_score=1.5,
                ),
                CandidateSpec(
                    candidate_id="duplicate",  # duplicate
                    strategy_id="mean_revert_v1",
                    param_hash="def456",
                    research_score=1.2,
                ),
            ],
        )
    
    # Missing export_id
    with pytest.raises(ValueError, match="export_id cannot be empty"):
        CandidateExport(
            export_id="",
            generated_at="2025-12-21T00:00:00Z",
            season="2026Q1",
            candidates=candidates,
        )
    
    # Missing generated_at
    with pytest.raises(ValueError, match="generated_at cannot be empty"):
        CandidateExport(
            export_id="export3",
            generated_at="",
            season="2026Q1",
            candidates=candidates,
        )
    
    # Missing season
    with pytest.raises(ValueError, match="season cannot be empty"):
        CandidateExport(
            export_id="export4",
            generated_at="2025-12-21T00:00:00Z",
            season="",
            candidates=candidates,
        )


def test_export_candidates_deterministic(tmp_path):
    """Test that export produces deterministic output."""
    candidates = [
        CandidateSpec(
            candidate_id="candidateB",
            strategy_id="sma_cross_v1",
            param_hash="abc123",
            research_score=1.5,
            tags=["tag1"],
        ),
        CandidateSpec(
            candidate_id="candidateA",
            strategy_id="mean_revert_v1",
            param_hash="def456",
            research_score=1.2,
            tags=["tag2"],
        ),
    ]
    
    # Export twice
    path1 = export_candidates(
        candidates,
        export_id="test_export",
        season="2026Q1",
        exports_root=tmp_path,
    )
    
    path2 = export_candidates(
        candidates,
        export_id="test_export",
        season="2026Q1",
        exports_root=tmp_path / "second",
    )
    
    # Load both exports
    export1 = load_candidates(path1)
    export2 = load_candidates(path2)
    
    # Verify deterministic ordering (candidate_id asc)
    candidate_ids1 = [c.candidate_id for c in export1.candidates]
    candidate_ids2 = [c.candidate_id for c in export2.candidates]
    
    assert candidate_ids1 == ["candidateA", "candidateB"]
    assert candidate_ids1 == candidate_ids2
    
    # Verify JSON content is identical (except generated_at timestamp)
    content1 = path1.read_text(encoding="utf-8")
    content2 = path2.read_text(encoding="utf-8")
    
    # Parse JSON and compare except generated_at
    import json
    data1 = json.loads(content1)
    data2 = json.loads(content2)
    
    # Remove generated_at for comparison
    data1.pop("generated_at")
    data2.pop("generated_at")
    
    assert data1 == data2


def test_load_candidates_file_not_found(tmp_path):
    """Test FileNotFoundError when loading non-existent file."""
    with pytest.raises(FileNotFoundError):
        load_candidates(tmp_path / "nonexistent.json")


def test_create_candidate_from_research():
    """Test create_candidate_from_research helper."""
    from FishBroWFS_V2.portfolio.candidate_spec import create_candidate_from_research
    
    candidate = create_candidate_from_research(
        candidate_id="candidate1",
        strategy_id="sma_cross_v1",
        params={"fast": 10, "slow": 30},
        research_score=1.5,
        season="2026Q1",
        batch_id="batchA",
        job_id="job1",
        tags=["topk"],
        metadata={"research_note": "good"},
    )
    
    assert candidate.candidate_id == "candidate1"
    assert candidate.strategy_id == "sma_cross_v1"
    assert candidate.param_hash  # should be computed
    assert candidate.research_score == 1.5
    assert candidate.season == "2026Q1"
    assert candidate.batch_id == "batchA"
    assert candidate.job_id == "job1"
    assert candidate.tags == ["topk"]
    assert candidate.metadata == {"research_note": "good"}


def test_boundary_safe_metadata():
    """Test that metadata can contain research details but not trading details."""
    # Allowed research metadata
    CandidateSpec(
        candidate_id="candidate1",
        strategy_id="sma_cross_v1",
        param_hash="abc123",
        research_score=1.5,
        metadata={
            "research_note": "good performance",
            "dataset_id": "CME_MNQ_v2",  # dataset is research detail, not trading
            "param_grid_id": "grid1",
            "funnel_stage": "stage2",
        },
    )
    
    # Trading details should be rejected
    trading_keys = [
        "symbol",
        "timeframe",
        "session_profile",
        "market",
        "exchange",
        "trading",
        "TRADING",  # uppercase
        "Symbol",   # mixed case
    ]
    
    for key in trading_keys:
        with pytest.raises(ValueError, match="boundary violation"):
            CandidateSpec(
                candidate_id="candidate1",
                strategy_id="sma_cross_v1",
                param_hash="abc123",
                research_score=1.5,
                metadata={key: "value"},
            )