
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


