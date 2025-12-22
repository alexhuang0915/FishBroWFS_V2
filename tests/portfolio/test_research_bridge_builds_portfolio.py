
"""Test research bridge builds portfolio correctly.

Phase 11: Test that research bridge correctly builds portfolio from research data.
"""

import json
import tempfile
from pathlib import Path
import pytest

from FishBroWFS_V2.portfolio.research_bridge import build_portfolio_from_research
from FishBroWFS_V2.portfolio.spec import PortfolioSpec


def test_build_portfolio_from_research_basic():
    """Test basic portfolio building from research data."""
    with tempfile.TemporaryDirectory() as tmpdir:
        outputs_root = Path(tmpdir)
        season = "2024Q1"
        
        # Create research directory structure
        research_dir = outputs_root / "seasons" / season / "research"
        research_dir.mkdir(parents=True)
        
        # Create fake research index
        research_index = {
            "entries": [
                {
                    "run_id": "run_mnq_001",
                    "keys": {
                        "symbol": "CME.MNQ",
                        "strategy_id": "strategy1",
                        "portfolio_id": "test"
                    },
                    "strategy_version": "1.0.0",
                    "timeframe_min": 60,
                    "session_profile": "default",
                    "score_final": 0.85,
                    "trades": 100
                },
                {
                    "run_id": "run_mxf_001",
                    "keys": {
                        "symbol": "TWF.MXF",
                        "strategy_id": "strategy2",
                        "portfolio_id": "test"
                    },
                    "strategy_version": "1.1.0",
                    "timeframe_min": 120,
                    "session_profile": "asia",
                    "score_final": 0.92,
                    "trades": 150
                },
                {
                    "run_id": "run_invalid_001",
                    "keys": {
                        "symbol": "INVALID.SYM",  # Not in allowlist
                        "strategy_id": "strategy3",
                        "portfolio_id": "test"
                    },
                    "strategy_version": "1.0.0",
                    "timeframe_min": 60,
                    "session_profile": "default"
                }
            ]
        }
        
        with open(research_dir / "research_index.json", 'w') as f:
            json.dump(research_index, f)
        
        # Create fake decisions.log
        decisions_log = [
            '{"run_id": "run_mnq_001", "decision": "KEEP", "note": "Good MNQ results"}',
            '{"run_id": "run_mxf_001", "decision": "KEEP", "note": "Excellent MXF"}',
            '{"run_id": "run_invalid_001", "decision": "KEEP", "note": "Invalid symbol"}',
            '{"run_id": "run_dropped_001", "decision": "DROP", "note": "Dropped run"}',
            '{"run_id": "run_archived_001", "decision": "ARCHIVE", "note": "Archived run"}',
        ]
        
        with open(research_dir / "decisions.log", 'w') as f:
            f.write('\n'.join(decisions_log))
        
        # Build portfolio
        portfolio_id, spec, manifest = build_portfolio_from_research(
            season=season,
            outputs_root=outputs_root,
            symbols_allowlist={"CME.MNQ", "TWF.MXF"}
        )
        
        # Verify results
        assert isinstance(spec, PortfolioSpec)
        assert spec.portfolio_id == portfolio_id
        assert spec.version == f"{season}_research"
        assert spec.data_tz == "Asia/Taipei"
        
        # Should have 2 legs (MNQ and MXF, not invalid symbol)
        assert len(spec.legs) == 2
        
        # Check leg details
        leg_symbols = {leg.symbol for leg in spec.legs}
        assert leg_symbols == {"CME.MNQ", "TWF.MXF"}
        
        # Check manifest
        assert manifest['portfolio_id'] == portfolio_id
        assert manifest['season'] == season
        assert 'generated_at' in manifest
        assert manifest['symbols_allowlist'] == ["CME.MNQ", "TWF.MXF"]
        
        # Check counts
        assert manifest['counts']['total_decisions'] == 5
        assert manifest['counts']['keep_decisions'] == 3  # 3 KEEP decisions
        assert manifest['counts']['num_legs_final'] == 2  # 2 after allowlist filter
        
        # Check symbols breakdown
        breakdown = manifest['counts']['symbols_breakdown']
        assert breakdown['CME.MNQ'] == 1
        assert breakdown['TWF.MXF'] == 1


def test_portfolio_id_deterministic():
    """Test that portfolio ID is deterministic."""
    with tempfile.TemporaryDirectory() as tmpdir:
        outputs_root = Path(tmpdir)
        season = "2024Q1"
        
        # Create research directory structure
        research_dir = outputs_root / "seasons" / season / "research"
        research_dir.mkdir(parents=True)
        
        # Create simple research index
        research_index = {
            "entries": [
                {
                    "run_id": "run1",
                    "keys": {
                        "symbol": "CME.MNQ",
                        "strategy_id": "s1",
                        "portfolio_id": "test"
                    },
                    "strategy_version": "1.0",
                    "timeframe_min": 60,
                    "session_profile": "default"
                }
            ]
        }
        
        with open(research_dir / "research_index.json", 'w') as f:
            json.dump(research_index, f)
        
        # Create decisions.log
        decisions_log = [
            '{"run_id": "run1", "decision": "KEEP", "note": "Test"}',
        ]
        
        with open(research_dir / "decisions.log", 'w') as f:
            f.write('\n'.join(decisions_log))
        
        # Build portfolio twice
        portfolio_id1, spec1, manifest1 = build_portfolio_from_research(
            season=season,
            outputs_root=outputs_root,
            symbols_allowlist={"CME.MNQ", "TWF.MXF"}
        )
        
        portfolio_id2, spec2, manifest2 = build_portfolio_from_research(
            season=season,
            outputs_root=outputs_root,
            symbols_allowlist={"CME.MNQ", "TWF.MXF"}
        )
        
        # Should be identical
        assert portfolio_id1 == portfolio_id2
        assert spec1.portfolio_id == spec2.portfolio_id
        assert len(spec1.legs) == len(spec2.legs) == 1
        
        # Manifest should be identical except for generated_at
        manifest1_copy = manifest1.copy()
        manifest2_copy = manifest2.copy()
        
        # Remove non-deterministic fields
        manifest1_copy.pop('generated_at')
        manifest2_copy.pop('generated_at')
        
        assert manifest1_copy == manifest2_copy


def test_missing_decisions_log():
    """Test handling of missing decisions.log file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        outputs_root = Path(tmpdir)
        season = "2024Q1"
        
        # Create research directory with only index
        research_dir = outputs_root / "seasons" / season / "research"
        research_dir.mkdir(parents=True)
        
        # Create empty research index
        research_index = {"entries": []}
        with open(research_dir / "research_index.json", 'w') as f:
            json.dump(research_index, f)
        
        # Build portfolio (decisions.log doesn't exist)
        portfolio_id, spec, manifest = build_portfolio_from_research(
            season=season,
            outputs_root=outputs_root,
            symbols_allowlist={"CME.MNQ", "TWF.MXF"}
        )
        
        # Should still work with empty portfolio
        assert isinstance(spec, PortfolioSpec)
        assert len(spec.legs) == 0
        assert manifest['counts']['total_decisions'] == 0
        assert manifest['counts']['keep_decisions'] == 0
        assert manifest['counts']['num_legs_final'] == 0


def test_missing_required_metadata():
    """Test handling of entries missing required metadata."""
    with tempfile.TemporaryDirectory() as tmpdir:
        outputs_root = Path(tmpdir)
        season = "2024Q1"
        
        # Create research directory
        research_dir = outputs_root / "seasons" / season / "research"
        research_dir.mkdir(parents=True)
        
        # Create research index with missing strategy_id
        research_index = {
            "entries": [
                {
                    "run_id": "run_missing_strategy",
                    "keys": {
                        "symbol": "CME.MNQ",
                        # Missing strategy_id
                        "portfolio_id": "test"
                    },
                    "strategy_version": "1.0.0",
                    "timeframe_min": 60,
                    "session_profile": "default"
                }
            ]
        }
        
        with open(research_dir / "research_index.json", 'w') as f:
            json.dump(research_index, f)
        
        # Create decisions.log with KEEP for this run
        decisions_log = [
            '{"run_id": "run_missing_strategy", "decision": "KEEP", "note": "Missing strategy"}',
        ]
        
        with open(research_dir / "decisions.log", 'w') as f:
            f.write('\n'.join(decisions_log))
        
        # Build portfolio
        portfolio_id, spec, manifest = build_portfolio_from_research(
            season=season,
            outputs_root=outputs_root,
            symbols_allowlist={"CME.MNQ", "TWF.MXF"}
        )
        
        # Should have 0 legs (missing required metadata)
        assert len(spec.legs) == 0
        
        # Should have warning about missing run ID
        assert 'warnings' in manifest
        assert 'missing_run_ids' in manifest['warnings']
        assert "run_missing_strategy" in manifest['warnings']['missing_run_ids']


def test_multiple_decisions_same_run():
    """Test that last decision wins for same run_id."""
    with tempfile.TemporaryDirectory() as tmpdir:
        outputs_root = Path(tmpdir)
        season = "2024Q1"
        
        # Create research directory
        research_dir = outputs_root / "seasons" / season / "research"
        research_dir.mkdir(parents=True)
        
        # Create research index
        research_index = {
            "entries": [
                {
                    "run_id": "run1",
                    "keys": {
                        "symbol": "CME.MNQ",
                        "strategy_id": "s1",
                        "portfolio_id": "test"
                    },
                    "strategy_version": "1.0",
                    "timeframe_min": 60,
                    "session_profile": "default"
                }
            ]
        }
        
        with open(research_dir / "research_index.json", 'w') as f:
            json.dump(research_index, f)
        
        # Create decisions.log with multiple decisions for same run
        decisions_log = [
            '{"run_id": "run1", "decision": "DROP", "note": "First decision"}',
            '{"run_id": "run1", "decision": "KEEP", "note": "Second decision"}',
            '{"run_id": "run1", "decision": "ARCHIVE", "note": "Third decision"}',
        ]
        
        with open(research_dir / "decisions.log", 'w') as f:
            f.write('\n'.join(decisions_log))
        
        # Build portfolio
        portfolio_id, spec, manifest = build_portfolio_from_research(
            season=season,
            outputs_root=outputs_root,
            symbols_allowlist={"CME.MNQ", "TWF.MXF"}
        )
        
        # Last decision was ARCHIVE, so should have 0 legs
        assert len(spec.legs) == 0
        assert manifest['counts']['keep_decisions'] == 0


def test_pipe_format_decisions():
    """Test parsing of pipe-delimited decisions format."""
    with tempfile.TemporaryDirectory() as tmpdir:
        outputs_root = Path(tmpdir)
        season = "2024Q1"
        
        # Create research directory
        research_dir = outputs_root / "seasons" / season / "research"
        research_dir.mkdir(parents=True)
        
        # Create research index
        research_index = {
            "entries": [
                {
                    "run_id": "run_pipe_1",
                    "keys": {
                        "symbol": "CME.MNQ",
                        "strategy_id": "s1",
                        "portfolio_id": "test"
                    },
                    "strategy_version": "1.0",
                    "timeframe_min": 60,
                    "session_profile": "default"
                },
                {
                    "run_id": "run_pipe_2",
                    "keys": {
                        "symbol": "TWF.MXF",
                        "strategy_id": "s2",
                        "portfolio_id": "test"
                    },
                    "strategy_version": "1.0",
                    "timeframe_min": 60,
                    "session_profile": "default"
                }
            ]
        }
        
        with open(research_dir / "research_index.json", 'w') as f:
            json.dump(research_index, f)
        
        # Create decisions.log with pipe format
        decisions_log = [
            'run_pipe_1|KEEP|Note for MNQ|2024-01-01',
            'run_pipe_2|keep|Note for MXF',  # lowercase keep
        ]
        
        with open(research_dir / "decisions.log", 'w') as f:
            f.write('\n'.join(decisions_log))
        
        # Build portfolio
        portfolio_id, spec, manifest = build_portfolio_from_research(
            season=season,
            outputs_root=outputs_root,
            symbols_allowlist={"CME.MNQ", "TWF.MXF"}
        )
        
        # Should have 2 legs
        assert len(spec.legs) == 2
        assert manifest['counts']['total_decisions'] == 2
        assert manifest['counts']['keep_decisions'] == 2
        assert manifest['counts']['num_legs_final'] == 2


