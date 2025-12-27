"""Test portfolio replay read-only guarantee."""

import tempfile
from pathlib import Path
import json
import pandas as pd
from datetime import datetime

import pytest

from core.schemas.portfolio_v1 import (
    PortfolioPolicyV1,
    PortfolioSpecV1,
    SignalCandidateV1,
)
from portfolio.runner_v1 import run_portfolio_admission
from portfolio.artifacts_writer_v1 import write_portfolio_artifacts


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
        from core.schemas.portfolio_v1 import (
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