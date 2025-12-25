FILE tests/portfolio/test_portfolio_replay_readonly.py
sha256(source_bytes) = 1934a9a51eca3a870f378f8b7207bd627babede5e3ee6fd85704fdec975d8464
bytes = 6540
redacted = False
--------------------------------------------------------------------------------
"""Test portfolio replay read-only guarantee."""

import tempfile
from pathlib import Path
import json
import pandas as pd
from datetime import datetime

import pytest

from FishBroWFS_V2.core.schemas.portfolio_v1 import (
    PortfolioPolicyV1,
    PortfolioSpecV1,
    SignalCandidateV1,
)
from FishBroWFS_V2.portfolio.runner_v1 import run_portfolio_admission
from FishBroWFS_V2.portfolio.artifacts_writer_v1 import write_portfolio_artifacts


def create_test_candidates() -> list[SignalCandidateV1]:
    """Create test candidates for portfolio admission."""
    return [
        SignalCandidateV1(
            strategy_id="S1",
            instrument_id="CME.MNQ",
            bar_ts=datetime(2025, 1, 1, 9, 0, 0),
            bar_index=0,
            signal_strength=0.9,
            candidate_score=0.0,
            required_margin_base=100000.0,
            required_slot=1,
        ),
        SignalCandidateV1(
            strategy_id="S2",
            instrument_id="TWF.MXF",
            bar_ts=datetime(2025, 1, 1, 10, 0, 0),
            bar_index=1,
            signal_strength=0.8,
            candidate_score=0.0,
            required_margin_base=150000.0,
            required_slot=1,
        ),
    ]


def test_replay_mode_no_writes():
    """Test that replay mode does not write any artifacts."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        
        # Create a mock outputs directory structure
        outputs_root = tmp_path / "outputs"
        outputs_root.mkdir()
        
        # Create policy and spec
        policy = PortfolioPolicyV1(
            version="PORTFOLIO_POLICY_V1",
            base_currency="TWD",
            instruments_config_sha256="test_sha256",
            max_slots_total=4,
            max_margin_ratio=0.35,
            max_notional_ratio=None,
            max_slots_by_instrument={},
            strategy_priority={"S1": 10, "S2": 20},
            signal_strength_field="signal_strength",
            allow_force_kill=False,
            allow_queue=False,
        )
        
        spec = PortfolioSpecV1(
            version="PORTFOLIO_SPEC_V1",
            seasons=["2026Q1"],
            strategy_ids=["S1", "S2"],
            instrument_ids=["CME.MNQ", "TWF.MXF"],
            start_date=None,
            end_date=None,
            policy_sha256="test_policy_sha256",
            spec_sha256="test_spec_sha256",
        )
        
        # Create a mock signal series file to avoid warnings
        season_dir = outputs_root / "2026Q1"
        season_dir.mkdir()
        
        # Run portfolio admission in normal mode (should write artifacts)
        output_dir_normal = tmp_path / "output_normal"
        equity_base = 1_000_000.0
        
        # We need to mock the assemble_candidates function to return our test candidates
        # Instead, we'll directly test the artifacts writer with replay mode
        
        # Create test decisions and bar_states
        from FishBroWFS_V2.core.schemas.portfolio_v1 import (
            AdmissionDecisionV1,
            PortfolioStateV1,
            PortfolioSummaryV1,
            OpenPositionV1,
        )
        
        decisions = [
            AdmissionDecisionV1(
                version="ADMISSION_DECISION_V1",
                strategy_id="S1",
                instrument_id="CME.MNQ",
                bar_ts=datetime(2025, 1, 1, 9, 0, 0),
                bar_index=0,
                signal_strength=0.9,
                candidate_score=0.0,
                signal_series_sha256=None,
                accepted=True,
                reason="ACCEPT",
                sort_key_used="priority=-10,signal_strength=0.9,strategy_id=S1",
                slots_after=1,
                margin_after_base=100000.0,
            )
        ]
        
        bar_states = {
            (0, datetime(2025, 1, 1, 9, 0, 0)): PortfolioStateV1(
                bar_ts=datetime(2025, 1, 1, 9, 0, 0),
                bar_index=0,
                equity_base=1_000_000.0,
                slots_used=1,
                margin_used_base=100000.0,
                notional_used_base=50000.0,
                open_positions=[
                    OpenPositionV1(
                        strategy_id="S1",
                        instrument_id="CME.MNQ",
                        slots=1,
                        margin_base=100000.0,
                        notional_base=50000.0,
                        entry_bar_index=0,
                        entry_bar_ts=datetime(2025, 1, 1, 9, 0, 0),
                    )
                ],
                reject_count=0,
            )
        }
        
        summary = PortfolioSummaryV1(
            total_candidates=2,
            accepted_count=1,
            rejected_count=1,
            reject_reasons={"REJECT_MARGIN": 1},
            final_slots_used=1,
            final_margin_used_base=100000.0,
            final_margin_ratio=0.1,
            policy_sha256="test_policy_sha256",
            spec_sha256="test_spec_sha256",
        )
        
        # Test 1: Normal mode should write artifacts
        hashes_normal = write_portfolio_artifacts(
            output_dir=output_dir_normal,
            decisions=decisions,
            bar_states=bar_states,
            summary=summary,
            policy=policy,
            spec=spec,
            replay_mode=False,
        )
        
        # Check that artifacts were created
        assert output_dir_normal.exists()
        assert (output_dir_normal / "portfolio_summary.json").exists()
        assert (output_dir_normal / "portfolio_manifest.json").exists()
        assert len(hashes_normal) > 0
        
        # Test 2: Replay mode should NOT write artifacts
        output_dir_replay = tmp_path / "output_replay"
        hashes_replay = write_portfolio_artifacts(
            output_dir=output_dir_replay,
            decisions=decisions,
            bar_states=bar_states,
            summary=summary,
            policy=policy,
            spec=spec,
            replay_mode=True,
        )
        
        # Check that no artifacts were created in replay mode
        assert not output_dir_replay.exists()
        assert hashes_replay == {}


def test_replay_consistency():
    """Test that replay produces same results as original run."""
    # This test would require a full portfolio run with actual signal series data
    # Since we don't have that, we'll skip it for now but document the requirement
    pass


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
--------------------------------------------------------------------------------

FILE tests/portfolio/test_portfolio_writer_outputs.py
sha256(source_bytes) = 255831dbfad7d777e37e2ca785f1bc0c375f0e9e38bc39684f0bac942d7f47f4
bytes = 16632
redacted = False
--------------------------------------------------------------------------------

"""Test portfolio writer outputs.

Phase 11: Test that writer creates correct artifacts.
"""

import json
import tempfile
from pathlib import Path
import pytest

from FishBroWFS_V2.portfolio.writer import write_portfolio_artifacts
from FishBroWFS_V2.portfolio.spec import PortfolioSpec, PortfolioLeg


def test_writer_creates_files():
    """Test that writer creates all required files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        outputs_root = Path(tmpdir)
        season = "2024Q1"
        
        # Create a test portfolio spec
        legs = [
            PortfolioLeg(
                leg_id="mnq_60_s1",
                symbol="CME.MNQ",
                timeframe_min=60,
                session_profile="default",
                strategy_id="strategy1",
                strategy_version="1.0.0",
                params={"param1": 1.0, "param2": 2.0},
                enabled=True,
                tags=["research_generated", season]
            ),
            PortfolioLeg(
                leg_id="mxf_120_s2",
                symbol="TWF.MXF",
                timeframe_min=120,
                session_profile="asia",
                strategy_id="strategy2",
                strategy_version="1.1.0",
                params={"param1": 1.5},
                enabled=True,
                tags=["research_generated", season]
            )
        ]
        
        spec = PortfolioSpec(
            portfolio_id="test12345678",
            version=f"{season}_research",
            legs=legs
        )
        
        # Create manifest
        manifest = {
            'portfolio_id': 'test12345678',
            'season': season,
            'generated_at': '2024-01-01T00:00:00Z',
            'symbols_allowlist': ['CME.MNQ', 'TWF.MXF'],
            'inputs': {
                'decisions_log_path': 'seasons/2024Q1/research/decisions.log',
                'decisions_log_sha1': 'abc123def456',
                'research_index_path': 'seasons/2024Q1/research/research_index.json',
                'research_index_sha1': 'def456abc123',
            },
            'counts': {
                'total_decisions': 10,
                'keep_decisions': 5,
                'num_legs_final': 2,
                'symbols_breakdown': {'CME.MNQ': 1, 'TWF.MXF': 1},
            },
            'warnings': {
                'missing_run_ids': [],
            }
        }
        
        # Write artifacts
        portfolio_dir = write_portfolio_artifacts(
            outputs_root=outputs_root,
            season=season,
            spec=spec,
            manifest=manifest
        )
        
        # Check directory was created
        assert portfolio_dir.exists()
        assert portfolio_dir.is_dir()
        
        # Check all files exist
        spec_path = portfolio_dir / "portfolio_spec.json"
        manifest_path = portfolio_dir / "portfolio_manifest.json"
        readme_path = portfolio_dir / "README.md"
        
        assert spec_path.exists()
        assert manifest_path.exists()
        assert readme_path.exists()


def test_json_files_parseable():
    """Test that JSON files are valid and parseable."""
    with tempfile.TemporaryDirectory() as tmpdir:
        outputs_root = Path(tmpdir)
        season = "2024Q1"
        
        # Create a simple test spec
        legs = [
            PortfolioLeg(
                leg_id="test_leg",
                symbol="CME.MNQ",
                timeframe_min=60,
                session_profile="default",
                strategy_id="s1",
                strategy_version="1.0",
                params={},
                enabled=True,
                tags=[]
            )
        ]
        
        spec = PortfolioSpec(
            portfolio_id="test123",
            version=f"{season}_research",
            legs=legs
        )
        
        manifest = {
            'portfolio_id': 'test123',
            'season': season,
            'generated_at': '2024-01-01T00:00:00Z',
            'symbols_allowlist': ['CME.MNQ'],
            'inputs': {
                'decisions_log_path': 'seasons/2024Q1/research/decisions.log',
                'decisions_log_sha1': 'test',
                'research_index_path': 'seasons/2024Q1/research/research_index.json',
                'research_index_sha1': 'test',
            },
            'counts': {
                'total_decisions': 1,
                'keep_decisions': 1,
                'num_legs_final': 1,
                'symbols_breakdown': {'CME.MNQ': 1},
            },
            'warnings': {
                'missing_run_ids': [],
            }
        }
        
        portfolio_dir = write_portfolio_artifacts(
            outputs_root=outputs_root,
            season=season,
            spec=spec,
            manifest=manifest
        )
        
        # Parse portfolio_spec.json
        spec_path = portfolio_dir / "portfolio_spec.json"
        with open(spec_path, 'r', encoding='utf-8') as f:
            spec_data = json.load(f)
        
        assert "portfolio_id" in spec_data
        assert spec_data["portfolio_id"] == "test123"
        assert "version" in spec_data
        assert spec_data["version"] == f"{season}_research"
        assert "data_tz" in spec_data
        assert spec_data["data_tz"] == "Asia/Taipei"
        assert "legs" in spec_data
        assert len(spec_data["legs"]) == 1
        
        # Parse portfolio_manifest.json
        manifest_path = portfolio_dir / "portfolio_manifest.json"
        with open(manifest_path, 'r', encoding='utf-8') as f:
            manifest_data = json.load(f)
        
        assert "portfolio_id" in manifest_data
        assert "generated_at" in manifest_data
        assert "inputs" in manifest_data
        assert "counts" in manifest_data


def test_manifest_fields_exist():
    """Test that manifest contains all required fields."""
    with tempfile.TemporaryDirectory() as tmpdir:
        outputs_root = Path(tmpdir)
        season = "2024Q1"
        
        legs = [
            PortfolioLeg(
                leg_id="mnq_leg",
                symbol="CME.MNQ",
                timeframe_min=60,
                session_profile="default",
                strategy_id="s1",
                strategy_version="1.0",
                params={},
                enabled=True,
                tags=[]
            ),
            PortfolioLeg(
                leg_id="mxf_leg",
                symbol="TWF.MXF",
                timeframe_min=60,
                session_profile="default",
                strategy_id="s2",
                strategy_version="1.0",
                params={},
                enabled=True,
                tags=[]
            )
        ]
        
        spec = PortfolioSpec(
            portfolio_id="test456",
            version=f"{season}_research",
            legs=legs
        )
        
        inputs_digest = "sha1_abc123"
        
        manifest = {
            'portfolio_id': 'test456',
            'season': season,
            'generated_at': '2024-01-01T00:00:00Z',
            'symbols_allowlist': ['CME.MNQ', 'TWF.MXF'],
            'inputs': {
                'decisions_log_path': 'seasons/2024Q1/research/decisions.log',
                'decisions_log_sha1': inputs_digest,
                'research_index_path': 'seasons/2024Q1/research/research_index.json',
                'research_index_sha1': inputs_digest,
            },
            'counts': {
                'total_decisions': 5,
                'keep_decisions': 2,
                'num_legs_final': 2,
                'symbols_breakdown': {'CME.MNQ': 1, 'TWF.MXF': 1},
            },
            'warnings': {
                'missing_run_ids': ['run_missing_1'],
            }
        }
        
        portfolio_dir = write_portfolio_artifacts(
            outputs_root=outputs_root,
            season=season,
            spec=spec,
            manifest=manifest
        )
        
        manifest_path = portfolio_dir / "portfolio_manifest.json"
        with open(manifest_path, 'r', encoding='utf-8') as f:
            manifest_data = json.load(f)
        
        # Check top-level fields
        assert manifest_data["portfolio_id"] == "test456"
        assert manifest_data["season"] == season
        assert "generated_at" in manifest_data
        assert isinstance(manifest_data["generated_at"], str)
        assert manifest_data["symbols_allowlist"] == ["CME.MNQ", "TWF.MXF"]
        
        # Check inputs section
        assert "inputs" in manifest_data
        inputs = manifest_data["inputs"]
        assert "decisions_log_path" in inputs
        assert "decisions_log_sha1" in inputs
        assert inputs["decisions_log_sha1"] == inputs_digest
        assert "research_index_path" in inputs
        assert "research_index_sha1" in inputs
        
        # Check counts section
        assert "counts" in manifest_data
        counts = manifest_data["counts"]
        assert "total_decisions" in counts
        assert counts["total_decisions"] == 5
        assert "keep_decisions" in counts
        assert counts["keep_decisions"] == 2
        assert "num_legs_final" in counts
        assert counts["num_legs_final"] == 2
        assert "symbols_breakdown" in counts
        
        # Check symbols breakdown
        breakdown = counts["symbols_breakdown"]
        assert "CME.MNQ" in breakdown
        assert breakdown["CME.MNQ"] == 1
        assert "TWF.MXF" in breakdown
        assert breakdown["TWF.MXF"] == 1
        
        # Check warnings
        assert "warnings" in manifest_data
        warnings = manifest_data["warnings"]
        assert "missing_run_ids" in warnings
        assert "run_missing_1" in warnings["missing_run_ids"]


def test_readme_exists_and_non_empty():
    """Test that README.md exists and contains content."""
    with tempfile.TemporaryDirectory() as tmpdir:
        outputs_root = Path(tmpdir)
        season = "2024Q1"
        
        legs = [
            PortfolioLeg(
                leg_id="test_leg",
                symbol="CME.MNQ",
                timeframe_min=60,
                session_profile="test_profile",
                strategy_id="test_strategy",
                strategy_version="1.0.0",
                params={"param": 1.0},
                enabled=True,
                tags=["research_generated", season]
            )
        ]
        
        spec = PortfolioSpec(
            portfolio_id="readme_test",
            version=f"{season}_research",
            legs=legs
        )
        
        manifest = {
            'portfolio_id': 'readme_test',
            'season': season,
            'generated_at': '2024-01-01T00:00:00Z',
            'symbols_allowlist': ['CME.MNQ'],
            'inputs': {
                'decisions_log_path': 'seasons/2024Q1/research/decisions.log',
                'decisions_log_sha1': 'test_digest_123',
                'research_index_path': 'seasons/2024Q1/research/research_index.json',
                'research_index_sha1': 'test_digest_123',
            },
            'counts': {
                'total_decisions': 3,
                'keep_decisions': 1,
                'num_legs_final': 1,
                'symbols_breakdown': {'CME.MNQ': 1},
            },
            'warnings': {
                'missing_run_ids': [],
            }
        }
        
        portfolio_dir = write_portfolio_artifacts(
            outputs_root=outputs_root,
            season=season,
            spec=spec,
            manifest=manifest
        )
        
        readme_path = portfolio_dir / "README.md"
        
        # Check file exists
        assert readme_path.exists()
        
        # Read content
        with open(readme_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Check it's not empty
        assert len(content) > 0
        
        # Check for expected sections
        assert "# Portfolio:" in content
        assert "## Purpose" in content
        assert "## Inputs" in content
        assert "## Legs" in content
        assert "## Summary" in content
        assert "## Reproducibility" in content
        
        # Check for specific content
        assert "readme_test" in content  # portfolio_id
        assert season in content
        assert "CME.MNQ" in content  # symbol
        assert "test_digest_123" in content  # inputs digest


def test_directory_structure():
    """Test that directory structure follows the规范."""
    with tempfile.TemporaryDirectory() as tmpdir:
        outputs_root = Path(tmpdir)
        season = "2024Q4"
        portfolio_id = "abc123def456"
        
        legs = [
            PortfolioLeg(
                leg_id="test_leg",
                symbol="CME.MNQ",
                timeframe_min=60,
                session_profile="default",
                strategy_id="s1",
                strategy_version="1.0",
                params={},
                enabled=True,
                tags=[]
            )
        ]
        
        spec = PortfolioSpec(
            portfolio_id=portfolio_id,
            version=f"{season}_research",
            legs=legs
        )
        
        manifest = {
            'portfolio_id': portfolio_id,
            'season': season,
            'generated_at': '2024-01-01T00:00:00Z',
            'symbols_allowlist': ['CME.MNQ'],
            'inputs': {
                'decisions_log_path': 'seasons/2024Q4/research/decisions.log',
                'decisions_log_sha1': 'digest',
                'research_index_path': 'seasons/2024Q4/research/research_index.json',
                'research_index_sha1': 'digest',
            },
            'counts': {
                'total_decisions': 1,
                'keep_decisions': 1,
                'num_legs_final': 1,
                'symbols_breakdown': {'CME.MNQ': 1},
            },
            'warnings': {
                'missing_run_ids': [],
            }
        }
        
        portfolio_dir = write_portfolio_artifacts(
            outputs_root=outputs_root,
            season=season,
            spec=spec,
            manifest=manifest
        )
        
        # Check path structure
        expected_path = outputs_root / "seasons" / season / "portfolio" / portfolio_id
        assert portfolio_dir == expected_path
        
        # Check files in directory
        files = list(portfolio_dir.iterdir())
        file_names = {f.name for f in files}
        
        assert "portfolio_spec.json" in file_names
        assert "portfolio_manifest.json" in file_names
        assert "README.md" in file_names
        assert len(files) == 3  # Only these 3 files


def test_empty_portfolio():
    """Test writing an empty portfolio (no legs)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        outputs_root = Path(tmpdir)
        season = "2024Q1"
        
        spec = PortfolioSpec(
            portfolio_id="empty_portfolio",
            version=f"{season}_research",
            legs=[]  # Empty legs
        )
        
        manifest = {
            'portfolio_id': 'empty_portfolio',
            'season': season,
            'generated_at': '2024-01-01T00:00:00Z',
            'symbols_allowlist': ['CME.MNQ', 'TWF.MXF'],
            'inputs': {
                'decisions_log_path': 'seasons/2024Q1/research/decisions.log',
                'decisions_log_sha1': 'empty_digest',
                'research_index_path': 'seasons/2024Q1/research/research_index.json',
                'research_index_sha1': 'empty_digest',
            },
            'counts': {
                'total_decisions': 0,
                'keep_decisions': 0,
                'num_legs_final': 0,
                'symbols_breakdown': {},
            },
            'warnings': {
                'missing_run_ids': [],
            }
        }
        
        portfolio_dir = write_portfolio_artifacts(
            outputs_root=outputs_root,
            season=season,
            spec=spec,
            manifest=manifest
        )
        
        # Should still create all files
        spec_path = portfolio_dir / "portfolio_spec.json"
        manifest_path = portfolio_dir / "portfolio_manifest.json"
        readme_path = portfolio_dir / "README.md"
        
        assert spec_path.exists()
        assert manifest_path.exists()
        assert readme_path.exists()
        
        # Check manifest counts
        with open(manifest_path, 'r', encoding='utf-8') as f:
            manifest_data = json.load(f)
        
        assert manifest_data["counts"]["num_legs_final"] == 0
        assert manifest_data["counts"]["symbols_breakdown"] == {}



--------------------------------------------------------------------------------

FILE tests/portfolio/test_research_bridge_builds_portfolio.py
sha256(source_bytes) = b2a4079533211d7d5b99a0615906d66b9aae55abc201c8d21fccc8ed7cef4940
bytes = 13888
redacted = False
--------------------------------------------------------------------------------

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



--------------------------------------------------------------------------------

FILE tests/portfolio/test_signal_series_exporter_v1.py
sha256(source_bytes) = 64345915edc000762a84004a3848e39deea749c601f99a2358cb9092bd24d9e4
bytes = 13314
redacted = False
--------------------------------------------------------------------------------
"""Tests for signal series exporter V1."""

import pandas as pd
import numpy as np
import pytest
from pathlib import Path

from FishBroWFS_V2.engine.signal_exporter import build_signal_series_v1, REQUIRED_COLUMNS
from FishBroWFS_V2.portfolio.instruments import load_instruments_config


def test_mnq_usd_fx_to_base_32():
    """MNQ (USD): fx_to_base=32 時 margin_base 正確"""
    # Create test data
    bars_df = pd.DataFrame({
        "ts": pd.date_range("2025-01-01", periods=5, freq="5min"),
        "close": [15000.0, 15010.0, 15020.0, 15030.0, 15040.0],
    })
    
    fills_df = pd.DataFrame({
        "ts": [bars_df["ts"][0], bars_df["ts"][2]],
        "qty": [1.0, -1.0],
    })
    
    # MNQ parameters (USD) - updated values from instruments.yaml (exchange_maintenance)
    df = build_signal_series_v1(
        instrument="CME.MNQ",
        bars_df=bars_df,
        fills_df=fills_df,
        timeframe="5min",
        tz="UTC",
        base_currency="TWD",
        instrument_currency="USD",
        fx_to_base=32.0,
        multiplier=2.0,
        initial_margin_per_contract=4000.0,
        maintenance_margin_per_contract=3500.0,
    )
    
    # Check columns
    assert list(df.columns) == REQUIRED_COLUMNS
    
    # Check fx_to_base is 32.0 for all rows
    assert (df["fx_to_base"] == 32.0).all()
    
    # Check close_base = close * 32.0
    assert np.allclose(df["close_base"].values, df["close"].values * 32.0)
    
    # Check margin calculations
    # Row 0: position=1, margin_initial_base = 1 * 4000.0 * 32 = 128000.0
    assert np.isclose(df.loc[0, "margin_initial_base"], 1 * 4000.0 * 32.0)
    assert np.isclose(df.loc[0, "margin_maintenance_base"], 1 * 3500.0 * 32.0)
    
    # Row 2: position=0 (after exit), margin should be 0
    assert np.isclose(df.loc[2, "margin_initial_base"], 0.0)
    assert np.isclose(df.loc[2, "margin_maintenance_base"], 0.0)
    
    # Check notional_base = position * close_base * multiplier
    # Row 0: position=1, close_base=15000*32=480000, multiplier=2, notional=960000
    expected_notional = 1 * 15000.0 * 32.0 * 2.0
    assert np.isclose(df.loc[0, "notional_base"], expected_notional)


def test_mxf_twd_fx_to_base_1():
    """MXF (TWD): fx_to_base=1 時 margin_base 正確"""
    bars_df = pd.DataFrame({
        "ts": pd.date_range("2025-01-01", periods=3, freq="5min"),
        "close": [18000.0, 18050.0, 18100.0],
    })
    
    fills_df = pd.DataFrame({
        "ts": [bars_df["ts"][0]],
        "qty": [2.0],
    })
    
    # MXF parameters (TWD) - updated values from instruments.yaml (conservative_over_exchange)
    df = build_signal_series_v1(
        instrument="TWF.MXF",
        bars_df=bars_df,
        fills_df=fills_df,
        timeframe="5min",
        tz="UTC",
        base_currency="TWD",
        instrument_currency="TWD",
        fx_to_base=1.0,
        multiplier=50.0,
        initial_margin_per_contract=88000.0,
        maintenance_margin_per_contract=80000.0,
    )
    
    # Check fx_to_base is 1.0 for all rows
    assert (df["fx_to_base"] == 1.0).all()
    
    # Check close_base = close * 1.0 (same)
    assert np.allclose(df["close_base"].values, df["close"].values)
    
    # Check margin calculations (no FX conversion)
    # Row 0: position=2, margin_initial_base = 2 * 88000 * 1 = 176000
    assert np.isclose(df.loc[0, "margin_initial_base"], 2 * 88000.0)
    assert np.isclose(df.loc[0, "margin_maintenance_base"], 2 * 80000.0)
    
    # Check notional_base
    expected_notional = 2 * 18000.0 * 1.0 * 50.0
    assert np.isclose(df.loc[0, "notional_base"], expected_notional)


def test_multiple_fills_same_bar():
    """同一 bar 多 fills（+1, +2, -1）→ position 正確"""
    bars_df = pd.DataFrame({
        "ts": pd.date_range("2025-01-01", periods=3, freq="5min"),
        "close": [100.0, 101.0, 102.0],
    })
    
    # Three fills at same timestamp (first bar)
    fill_ts = bars_df["ts"][0]
    fills_df = pd.DataFrame({
        "ts": [fill_ts, fill_ts, fill_ts],
        "qty": [1.0, 2.0, -1.0],  # Net +2
    })
    
    df = build_signal_series_v1(
        instrument="TEST",
        bars_df=bars_df,
        fills_df=fills_df,
        timeframe="5min",
        tz="UTC",
        base_currency="TWD",
        instrument_currency="USD",
        fx_to_base=1.0,
        multiplier=1.0,
        initial_margin_per_contract=1000.0,
        maintenance_margin_per_contract=800.0,
    )
    
    # Check position_contracts
    # Bar 0: position = 1 + 2 - 1 = 2
    assert np.isclose(df.loc[0, "position_contracts"], 2.0)
    # Bar 1 and 2: position stays 2 (no more fills)
    assert np.isclose(df.loc[1, "position_contracts"], 2.0)
    assert np.isclose(df.loc[2, "position_contracts"], 2.0)


def test_fills_between_bars_merge_asof():
    """fills 落在兩根 bar 中間 → merge_asof 對齊規則正確"""
    # Create bars at 00:00, 00:05, 00:10
    bars_df = pd.DataFrame({
        "ts": pd.to_datetime(["2025-01-01 00:00", "2025-01-01 00:05", "2025-01-01 00:10"]),
        "close": [100.0, 101.0, 102.0],
    })
    
    # Fill at 00:02 (between bar 0 and bar 1)
    # Should be assigned to bar 0 (backward fill, <= fill_ts 的最近 bar ts)
    fills_df = pd.DataFrame({
        "ts": pd.to_datetime(["2025-01-01 00:02"]),
        "qty": [1.0],
    })
    
    df = build_signal_series_v1(
        instrument="TEST",
        bars_df=bars_df,
        fills_df=fills_df,
        timeframe="5min",
        tz="UTC",
        base_currency="TWD",
        instrument_currency="USD",
        fx_to_base=1.0,
        multiplier=1.0,
        initial_margin_per_contract=1000.0,
        maintenance_margin_per_contract=800.0,
    )
    
    # Check position_contracts
    # Bar 0: position = 1 (fill assigned to bar 0)
    assert np.isclose(df.loc[0, "position_contracts"], 1.0)
    # Bar 1 and 2: position stays 1
    assert np.isclose(df.loc[1, "position_contracts"], 1.0)
    assert np.isclose(df.loc[2, "position_contracts"], 1.0)
    
    # Test fill at 00:07 (between bar 1 and bar 2)
    fills_df2 = pd.DataFrame({
        "ts": pd.to_datetime(["2025-01-01 00:07"]),
        "qty": [2.0],
    })
    
    df2 = build_signal_series_v1(
        instrument="TEST",
        bars_df=bars_df,
        fills_df=fills_df2,
        timeframe="5min",
        tz="UTC",
        base_currency="TWD",
        instrument_currency="USD",
        fx_to_base=1.0,
        multiplier=1.0,
        initial_margin_per_contract=1000.0,
        maintenance_margin_per_contract=800.0,
    )
    
    # Bar 0: position = 0
    assert np.isclose(df2.loc[0, "position_contracts"], 0.0)
    # Bar 1: position = 2 (fill at 00:07 assigned to bar 1 at 00:05)
    assert np.isclose(df2.loc[1, "position_contracts"], 2.0)
    # Bar 2: position stays 2
    assert np.isclose(df2.loc[2, "position_contracts"], 2.0)


def test_deterministic_same_input():
    """deterministic：同 input 連跑兩次 df.equals(True)"""
    bars_df = pd.DataFrame({
        "ts": pd.date_range("2025-01-01", periods=10, freq="5min"),
        "close": np.random.randn(10) * 100 + 15000.0,
    })
    
    fills_df = pd.DataFrame({
        "ts": bars_df["ts"].sample(5, random_state=42).sort_values(),
        "qty": np.random.choice([-1.0, 1.0], 5),
    })
    
    # First run
    df1 = build_signal_series_v1(
        instrument="CME.MNQ",
        bars_df=bars_df,
        fills_df=fills_df,
        timeframe="5min",
        tz="UTC",
        base_currency="TWD",
        instrument_currency="USD",
        fx_to_base=32.0,
        multiplier=2.0,
        initial_margin_per_contract=4000.0,
        maintenance_margin_per_contract=3500.0,
    )
    
    # Second run with same input
    df2 = build_signal_series_v1(
        instrument="CME.MNQ",
        bars_df=bars_df,
        fills_df=fills_df,
        timeframe="5min",
        tz="UTC",
        base_currency="TWD",
        instrument_currency="USD",
        fx_to_base=32.0,
        multiplier=2.0,
        initial_margin_per_contract=4000.0,
        maintenance_margin_per_contract=3500.0,
    )
    
    # DataFrames should be equal
    pd.testing.assert_frame_equal(df1, df2)


def test_columns_complete_no_nan():
    """欄位完整且無 NaN（close_base/notional/margins）"""
    bars_df = pd.DataFrame({
        "ts": pd.date_range("2025-01-01", periods=3, freq="5min"),
        "close": [100.0, 101.0, 102.0],
    })
    
    fills_df = pd.DataFrame({
        "ts": [bars_df["ts"][0], bars_df["ts"][2]],
        "qty": [1.0, -1.0],
    })
    
    df = build_signal_series_v1(
        instrument="TEST",
        bars_df=bars_df,
        fills_df=fills_df,
        timeframe="5min",
        tz="UTC",
        base_currency="TWD",
        instrument_currency="USD",
        fx_to_base=1.0,
        multiplier=1.0,
        initial_margin_per_contract=1000.0,
        maintenance_margin_per_contract=800.0,
    )
    
    # Check all required columns present
    assert set(df.columns) == set(REQUIRED_COLUMNS)
    
    # Check no NaN values in numeric columns
    numeric_cols = df.select_dtypes(include=[np.number]).columns
    assert not df[numeric_cols].isna().any().any()
    
    # Specifically check calculated columns
    assert not df["close_base"].isna().any()
    assert not df["notional_base"].isna().any()
    assert not df["margin_initial_base"].isna().any()
    assert not df["margin_maintenance_base"].isna().any()


def test_instruments_config_loader():
    """Test instruments config loader with SHA256."""
    config_path = Path("configs/portfolio/instruments.yaml")
    
    # Load config
    cfg = load_instruments_config(config_path)
    
    # Check basic structure
    assert cfg.version == 1
    assert cfg.base_currency == "TWD"
    assert "USD" in cfg.fx_rates
    assert "TWD" in cfg.fx_rates
    assert cfg.fx_rates["TWD"] == 1.0
    
    # Check instruments
    assert "CME.MNQ" in cfg.instruments
    assert "TWF.MXF" in cfg.instruments
    
    mnq = cfg.instruments["CME.MNQ"]
    assert mnq.currency == "USD"
    assert mnq.multiplier == 2.0
    assert mnq.initial_margin_per_contract == 4000.0
    assert mnq.maintenance_margin_per_contract == 3500.0
    assert mnq.margin_basis == "exchange_maintenance"
    
    mxf = cfg.instruments["TWF.MXF"]
    assert mxf.currency == "TWD"
    assert mxf.multiplier == 50.0
    assert mxf.initial_margin_per_contract == 88000.0
    assert mxf.maintenance_margin_per_contract == 80000.0
    assert mxf.margin_basis == "conservative_over_exchange"
    
    # Check SHA256 is present and non-empty
    assert cfg.sha256
    assert len(cfg.sha256) == 64  # SHA256 hex length
    
    # Test that modifying config changes SHA256
    import tempfile
    import yaml
    
    # Create a modified config
    with open(config_path, "r") as f:
        original_data = yaml.safe_load(f)
    
    modified_data = original_data.copy()
    modified_data["fx_rates"]["USD"] = 33.0  # Change FX rate
    
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as tmp:
        yaml.dump(modified_data, tmp)
        tmp_path = Path(tmp.name)
    
    try:
        cfg2 = load_instruments_config(tmp_path)
        # SHA256 should be different
        assert cfg2.sha256 != cfg.sha256
    finally:
        tmp_path.unlink()


def test_anti_regression_margin_minimums():
    """防回歸測試：確保保證金不低於交易所 maintenance 等級"""
    config_path = Path("configs/portfolio/instruments.yaml")
    cfg = load_instruments_config(config_path)
    
    # MNQ: 必須大於 3000 USD (避免被改回 day margin)
    mnq = cfg.instruments["CME.MNQ"]
    assert mnq.maintenance_margin_per_contract > 3000.0, \
        f"MNQ maintenance margin ({mnq.maintenance_margin_per_contract}) must be > 3000 USD to avoid day margin"
    assert mnq.initial_margin_per_contract > mnq.maintenance_margin_per_contract, \
        f"MNQ initial margin ({mnq.initial_margin_per_contract}) must be > maintenance margin"
    
    # MXF: 必須 ≥ TAIFEX 官方 maintenance (64,750 TWD)
    mxf = cfg.instruments["TWF.MXF"]
    taifex_official_maintenance = 64750.0
    assert mxf.maintenance_margin_per_contract >= taifex_official_maintenance, \
        f"MXF maintenance margin ({mxf.maintenance_margin_per_contract}) must be >= TAIFEX official ({taifex_official_maintenance})"
    
    # MXF: 必須 ≥ TAIFEX 官方 initial (84,500 TWD)
    taifex_official_initial = 84500.0
    assert mxf.initial_margin_per_contract >= taifex_official_initial, \
        f"MXF initial margin ({mxf.initial_margin_per_contract}) must be >= TAIFEX official ({taifex_official_initial})"
    
    # 檢查 margin_basis 符合預期
    assert mnq.margin_basis in ["exchange_maintenance", "conservative_over_exchange"], \
        f"MNQ margin_basis must be exchange_maintenance or conservative_over_exchange, got {mnq.margin_basis}"
    assert mxf.margin_basis in ["exchange_maintenance", "conservative_over_exchange"], \
        f"MXF margin_basis must be exchange_maintenance or conservative_over_exchange, got {mxf.margin_basis}"
    
    # 禁止使用 broker_day
    assert mnq.margin_basis != "broker_day", "MNQ must not use broker_day margin basis"
    assert mxf.margin_basis != "broker_day", "MXF must not use broker_day margin basis"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
--------------------------------------------------------------------------------

FILE tests/strategy/test_strategy_registry.py
sha256(source_bytes) = b9766f08a7df65c18340cf4244447d40db2fa25e59ae29d522ba2fb750daf3bf
bytes = 8587
redacted = False
--------------------------------------------------------------------------------

"""Tests for Strategy Registry (Phase 12)."""

from __future__ import annotations

from typing import Any, Dict

import pytest

from FishBroWFS_V2.strategy.param_schema import ParamSpec
from FishBroWFS_V2.strategy.registry import (
    StrategySpecForGUI,
    StrategyRegistryResponse,
    convert_to_gui_spec,
    get_strategy_registry,
    register,
    clear,
    load_builtin_strategies,
)
from FishBroWFS_V2.strategy.spec import StrategySpec


def create_dummy_strategy_fn(context: Dict[str, Any], params: Dict[str, float]) -> Dict[str, Any]:
    """Dummy strategy function for testing."""
    return {"intents": [], "debug": {}}


def test_param_spec_schema() -> None:
    """Test ParamSpec schema validation."""
    # Test int parameter
    int_param = ParamSpec(
        name="window",
        type="int",
        min=5,
        max=100,
        step=5,
        default=20,
        help="Lookback window size"
    )
    assert int_param.name == "window"
    assert int_param.type == "int"
    assert int_param.min == 5
    assert int_param.max == 100
    assert int_param.default == 20
    
    # Test float parameter
    float_param = ParamSpec(
        name="threshold",
        type="float",
        min=0.0,
        max=1.0,
        step=0.1,
        default=0.5,
        help="Signal threshold"
    )
    assert float_param.type == "float"
    assert float_param.min == 0.0
    
    # Test enum parameter
    enum_param = ParamSpec(
        name="mode",
        type="enum",
        choices=["fast", "slow", "adaptive"],
        default="fast",
        help="Operation mode"
    )
    assert enum_param.type == "enum"
    assert enum_param.choices == ["fast", "slow", "adaptive"]
    
    # Test bool parameter
    bool_param = ParamSpec(
        name="enabled",
        type="bool",
        default=True,
        help="Enable feature"
    )
    assert bool_param.type == "bool"
    assert bool_param.default is True


def test_strategy_spec_for_gui() -> None:
    """Test StrategySpecForGUI schema."""
    params = [
        ParamSpec(
            name="window",
            type="int",
            min=10,
            max=200,
            default=50,
            help="Window size"
        )
    ]
    
    spec = StrategySpecForGUI(
        strategy_id="test_strategy_v1",
        params=params
    )
    
    assert spec.strategy_id == "test_strategy_v1"
    assert len(spec.params) == 1
    assert spec.params[0].name == "window"


def test_strategy_registry_response() -> None:
    """Test StrategyRegistryResponse schema."""
    params = [
        ParamSpec(
            name="param1",
            type="int",
            default=10,
            help="Test parameter"
        )
    ]
    
    strategy = StrategySpecForGUI(
        strategy_id="test_strategy",
        params=params
    )
    
    response = StrategyRegistryResponse(
        strategies=[strategy]
    )
    
    assert len(response.strategies) == 1
    assert response.strategies[0].strategy_id == "test_strategy"


def test_convert_to_gui_spec() -> None:
    """Test conversion from internal StrategySpec to GUI format."""
    # Create a dummy strategy spec
    internal_spec = StrategySpec(
        strategy_id="dummy_strategy_v1",
        version="v1",
        param_schema={
            "window": {
                "type": "int",
                "minimum": 10,
                "maximum": 100,
                "step": 5,
                "description": "Lookback window"
            },
            "threshold": {
                "type": "float",
                "minimum": 0.0,
                "maximum": 1.0,
                "description": "Signal threshold"
            }
        },
        defaults={
            "window": 20,
            "threshold": 0.5
        },
        fn=create_dummy_strategy_fn
    )
    
    # Convert to GUI spec
    gui_spec = convert_to_gui_spec(internal_spec)
    
    assert gui_spec.strategy_id == "dummy_strategy_v1"
    assert len(gui_spec.params) == 2
    
    # Check window parameter
    window_param = next(p for p in gui_spec.params if p.name == "window")
    assert window_param.type == "int"
    assert window_param.min == 10
    assert window_param.max == 100
    assert window_param.step == 5
    assert window_param.default == 20
    assert "Lookback window" in window_param.help
    
    # Check threshold parameter
    threshold_param = next(p for p in gui_spec.params if p.name == "threshold")
    assert threshold_param.type == "float"
    assert threshold_param.min == 0.0
    assert threshold_param.max == 1.0
    assert threshold_param.default == 0.5


def test_get_strategy_registry_with_dummy() -> None:
    """Test get_strategy_registry with dummy strategy."""
    # Clear any existing strategies
    clear()
    
    # Register a dummy strategy
    dummy_spec = StrategySpec(
        strategy_id="test_gui_strategy_v1",
        version="v1",
        param_schema={
            "param1": {
                "type": "int",
                "minimum": 1,
                "maximum": 10,
                "description": "Test parameter 1"
            }
        },
        defaults={"param1": 5},
        fn=create_dummy_strategy_fn
    )
    
    register(dummy_spec)
    
    # Get registry response
    response = get_strategy_registry()
    
    assert len(response.strategies) == 1
    gui_spec = response.strategies[0]
    assert gui_spec.strategy_id == "test_gui_strategy_v1"
    assert len(gui_spec.params) == 1
    assert gui_spec.params[0].name == "param1"
    
    # Clean up
    clear()


def test_get_strategy_registry_with_builtin() -> None:
    """Test get_strategy_registry with built-in strategies."""
    # Clear and load built-in strategies
    clear()
    load_builtin_strategies()
    
    # Get registry response
    response = get_strategy_registry()
    
    # Should have at least the built-in strategies
    assert len(response.strategies) >= 3
    
    # Check that all strategies have params
    for strategy in response.strategies:
        assert strategy.strategy_id
        assert isinstance(strategy.params, list)
        
        # Each param should have required fields
        for param in strategy.params:
            assert param.name
            assert param.type in ["int", "float", "enum", "bool"]
            assert param.help
    
    # Clean up
    clear()


def test_meta_strategies_endpoint_compatibility() -> None:
    """Test that registry response is compatible with /meta/strategies endpoint."""
    # This test ensures the response structure matches what the API expects
    clear()
    
    # Register a simple strategy
    simple_spec = StrategySpec(
        strategy_id="simple_v1",
        version="v1",
        param_schema={
            "enabled": {
                "type": "bool",
                "description": "Enable strategy"
            }
        },
        defaults={"enabled": True},
        fn=create_dummy_strategy_fn
    )
    
    register(simple_spec)
    
    # Get response and verify structure
    response = get_strategy_registry()
    
    # Response should be JSON serializable
    import json
    json_str = response.model_dump_json()
    data = json.loads(json_str)
    
    assert "strategies" in data
    assert isinstance(data["strategies"], list)
    assert len(data["strategies"]) == 1
    
    strategy_data = data["strategies"][0]
    assert strategy_data["strategy_id"] == "simple_v1"
    assert "params" in strategy_data
    assert isinstance(strategy_data["params"], list)
    
    # Clean up
    clear()


def test_param_spec_validation() -> None:
    """Test ParamSpec validation rules."""
    # Valid int param
    ParamSpec(
        name="valid_int",
        type="int",
        min=0,
        max=100,
        default=50,
        help="Valid integer"
    )
    
    # Valid float param
    ParamSpec(
        name="valid_float",
        type="float",
        min=0.0,
        max=1.0,
        default=0.5,
        help="Valid float"
    )
    
    # Valid enum param
    ParamSpec(
        name="valid_enum",
        type="enum",
        choices=["a", "b", "c"],
        default="a",
        help="Valid enum"
    )
    
    # Valid bool param
    ParamSpec(
        name="valid_bool",
        type="bool",
        default=True,
        help="Valid boolean"
    )
    
    # Test invalid type
    with pytest.raises(ValueError):
        ParamSpec(
            name="invalid",
            type="invalid_type",  # type: ignore
            default=1,
            help="Invalid type"
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])



--------------------------------------------------------------------------------

FILE tests/wfs/test_wfs_no_io.py
sha256(source_bytes) = 844ae3073a62b8f043f11f058e1a1510132f70fd5e4f1017d0e66b3a3b228055
bytes = 2872
redacted = False
--------------------------------------------------------------------------------

import builtins
from pathlib import Path

import numpy as np
import pytest

from FishBroWFS_V2.core.feature_bundle import FeatureSeries, FeatureBundle
import FishBroWFS_V2.wfs.runner as wfs_runner


class _DummySpec:
    """
    Minimal strategy spec object for tests.
    Must provide:
      - defaults: dict
      - fn(strategy_input: dict, params: dict) -> dict with {"intents": [...]}
    """
    def __init__(self):
        self.defaults = {}

        def _fn(strategy_input, params):
            # Must not do IO; return valid structure for run_strategy().
            return {"intents": []}

        self.fn = _fn


def test_run_wfs_with_features_disallows_file_io_without_real_strategy(monkeypatch):
    # 1) Hard deny all file IO primitives
    def _deny(*args, **kwargs):
        raise RuntimeError("IO is forbidden in run_wfs_with_features")

    monkeypatch.setattr(builtins, "open", _deny, raising=True)
    monkeypatch.setattr(Path, "open", _deny, raising=True)
    monkeypatch.setattr(Path, "read_text", _deny, raising=True)
    monkeypatch.setattr(Path, "exists", _deny, raising=True)

    # 2) Inject dummy strategy spec so we don't rely on repo strategy registry/ids
    # Primary patch target: symbol referenced by wfs_runner module
    monkeypatch.setattr(wfs_runner, "get_strategy_spec", lambda strategy_id: _DummySpec(), raising=False)

    # If get_strategy_spec isn't used in this repo layout, add fallback patches:
    # These should be kept harmless by raising=False.
    try:
        import FishBroWFS_V2.strategy.registry as strat_registry
        monkeypatch.setattr(strat_registry, "get", lambda strategy_id: _DummySpec(), raising=False)
    except Exception:
        pass

    try:
        import FishBroWFS_V2.strategy.runner as strat_runner
        monkeypatch.setattr(strat_runner, "get", lambda strategy_id: _DummySpec(), raising=False)
    except Exception:
        pass

    # 3) Build a minimal FeatureBundle
    ts = np.array(
        ["2025-01-01T00:00:00", "2025-01-01T00:01:00", "2025-01-01T00:02:00"],
        dtype="datetime64[s]",
    )
    v = np.array([1.0, 2.0, 3.0], dtype=np.float64)

    s1 = FeatureSeries(ts=ts, values=v, name="atr_14", timeframe_min=60)
    s2 = FeatureSeries(ts=ts, values=v, name="ret_z_200", timeframe_min=60)
    s3 = FeatureSeries(ts=ts, values=v, name="session_vwap", timeframe_min=60)

    # FeatureBundle requires meta dict with ts_dtype and breaks_policy
    meta = {
        "ts_dtype": "datetime64[s]",
        "breaks_policy": "drop",
    }
    bundle = FeatureBundle(
        dataset_id="D",
        season="S",
        series={(s.name, s.timeframe_min): s for s in [s1, s2, s3]},
        meta=meta,
    )

    out = wfs_runner.run_wfs_with_features(
        strategy_id="__dummy__",
        feature_bundle=bundle,
        config={"params": {}},
    )

    assert isinstance(out, dict)


--------------------------------------------------------------------------------

FILE tmp_data/CME.MNQ HOT-Minute-Trade.txt
sha256(source_bytes) = 8b89faab0849b861a061c28c48fc6cf9424eaf28b5948b29f7ace614c0185347
bytes = 255
redacted = False
--------------------------------------------------------------------------------
"Date","Time","Open","High","Low","Close","TotalVolume"
2013/1/1,00:01:00,132.812500,132.812500,132.812500,132.812500,156
2013/1/1,00:02:00,132.812500,132.812500,132.812500,132.812500,756
2013/1/1,00:03:00,132.812500,132.812500,132.781250,132.796875,1497

--------------------------------------------------------------------------------

