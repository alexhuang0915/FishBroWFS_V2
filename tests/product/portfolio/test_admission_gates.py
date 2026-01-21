"""
Test admission gates (integrity, diversity, correlation) and replacement mode.
"""
import pytest
from pathlib import Path
from unittest.mock import patch

from portfolio.models.governance_models import (
    StrategyIdentity,
    GovernanceParams,
    ReturnSeries,
)
from portfolio.governance.admission import (
    evaluate_diversity,
    evaluate_correlation,
    validate_dominance_proof,
    admit_candidate,
)


@pytest.fixture
def tmp_governance_root(tmp_path):
    with patch("portfolio.governance.governance_logging.governance_root") as mock_logging_root, \
         patch("portfolio.governance.admission.governance_root") as mock_admission_root:
        mock_logging_root.return_value = tmp_path / "governance"
        mock_admission_root.return_value = tmp_path / "governance"
        yield mock_logging_root


@pytest.fixture
def sample_params():
    return GovernanceParams(
        bucket_slots={"Trend": 2, "MeanRev": 1},
        corr_portfolio_hard_limit=0.7,
        corr_member_hard_limit=0.8,
        corr_min_samples=5,
    )


@pytest.fixture
def candidate_trend():
    return StrategyIdentity(
        strategy_id="S2_T1",
        version_hash="v1",
        universe={"symbol": "MNQ"},
        data_fingerprint="fp1",
        cost_model_id="cost",
        tags=["Trend"],
    )


@pytest.fixture
def candidate_meanrev():
    return StrategyIdentity(
        strategy_id="S2_M1",
        version_hash="v1",
        universe={"symbol": "MNQ"},
        data_fingerprint="fp2",
        cost_model_id="cost",
        tags=["MeanRev"],
    )


@pytest.fixture
def existing_identities():
    return [
        StrategyIdentity(
            strategy_id="S2_T0",
            version_hash="v0",
            universe={"symbol": "MNQ"},
            data_fingerprint="fp0",
            cost_model_id="cost",
            tags=["Trend"],
        ),
        StrategyIdentity(
            strategy_id="S2_T1",
            version_hash="v1",
            universe={"symbol": "MNQ"},
            data_fingerprint="fp1",
            cost_model_id="cost",
            tags=["Trend"],
        ),
    ]


class TestDiversityGate:
    def test_diversity_pass_when_slot_available(self, candidate_meanrev, existing_identities, sample_params):
        """Bucket MeanRev has capacity 1, currently 0 → pass."""
        result = evaluate_diversity(candidate_meanrev, existing_identities, sample_params)
        assert result["bucket"] == "MeanRev"
        assert result["used"] == 0
        assert result["capacity"] == 1
        assert result["pass"] is True

    def test_diversity_fail_when_bucket_full(self, candidate_trend, existing_identities, sample_params):
        """Bucket Trend already has 2 strategies, capacity 2 → full."""
        result = evaluate_diversity(candidate_trend, existing_identities, sample_params)
        assert result["bucket"] == "Trend"
        assert result["used"] == 2
        assert result["capacity"] == 2
        assert result["pass"] is False

    def test_diversity_waived_in_replacement_mode(self, candidate_trend, existing_identities, sample_params):
        """Even if bucket full, replacement mode waives the gate."""
        result = evaluate_diversity(
            candidate_trend,
            existing_identities,
            sample_params,
            replacement_mode=True,
        )
        assert result["pass"] is True
        assert "replacement_mode" in result["reason"]


class TestCorrelationGate:
    def test_correlation_pass_within_limits(self, sample_params):
        """Low correlation should pass."""
        candidate_returns = ReturnSeries(name="c", returns=[0.01, -0.02, 0.03, -0.01, 0.02])
        portfolio_returns = ReturnSeries(name="p", returns=[0.0, 0.0, 0.0, 0.0, 0.0])
        member_returns = [ReturnSeries(name="m", returns=[0.0, 0.0, 0.0, 0.0, 0.0])]

        result = evaluate_correlation(
            candidate_returns,
            portfolio_returns,
            member_returns,
            sample_params,
        )
        assert result["pass"] is True
        assert abs(result["corr_vs_portfolio"]) <= sample_params.corr_portfolio_hard_limit
        assert result["max_corr_vs_member"] <= sample_params.corr_member_hard_limit

    def test_correlation_fail_exceeds_portfolio_limit(self, sample_params):
        """High correlation vs portfolio should fail."""
        # Use identical series -> correlation = 1.0
        candidate_returns = ReturnSeries(name="c", returns=[0.1, 0.2, 0.3, 0.4, 0.5])
        portfolio_returns = ReturnSeries(name="p", returns=[0.1, 0.2, 0.3, 0.4, 0.5])
        member_returns = [ReturnSeries(name="m", returns=[0.0, 0.0, 0.0, 0.0, 0.0])]

        result = evaluate_correlation(
            candidate_returns,
            portfolio_returns,
            member_returns,
            sample_params,
        )
        assert result["pass"] is False
        assert abs(result["corr_vs_portfolio"]) > sample_params.corr_portfolio_hard_limit

    def test_insufficient_samples_returns_pass(self, sample_params):
        """If samples < corr_min_samples, gate passes with reason."""
        candidate_returns = ReturnSeries(name="c", returns=[0.01, 0.02])
        portfolio_returns = ReturnSeries(name="p", returns=[0.01, 0.02])
        member_returns = [ReturnSeries(name="m", returns=[0.0, 0.0])]

        result = evaluate_correlation(
            candidate_returns,
            portfolio_returns,
            member_returns,
            sample_params,
        )
        assert result["pass"] is True
        assert "insufficient samples" in result["reason"]


class TestDominanceProof:
    def test_valid_dominance_proof(self):
        proof = {
            "expected_score_new": 0.15,
            "expected_score_old": 0.10,
            "risk_adj_new": 0.12,
            "risk_adj_old": 0.12,
        }
        valid, reason = validate_dominance_proof(proof)
        assert valid is True
        assert "dominance proven" in reason

    def test_missing_keys(self):
        proof = {"expected_score_new": 0.15}
        valid, reason = validate_dominance_proof(proof)
        assert valid is False
        assert "missing keys" in reason

    def test_new_score_not_higher(self):
        proof = {
            "expected_score_new": 0.10,
            "expected_score_old": 0.15,
            "risk_adj_new": 0.12,
            "risk_adj_old": 0.12,
        }
        valid, reason = validate_dominance_proof(proof)
        assert valid is False
        assert "expected_score_new" in reason

    def test_risk_adj_lower(self):
        proof = {
            "expected_score_new": 0.15,
            "expected_score_old": 0.10,
            "risk_adj_new": 0.10,
            "risk_adj_old": 0.12,
        }
        valid, reason = validate_dominance_proof(proof)
        assert valid is False
        assert "risk_adj_new" in reason


class TestAdmissionIntegration:
    def test_integrity_gate_denies_all(self, candidate_trend, sample_params, tmp_governance_root):
        """If integrity_ok is False, candidate is denied regardless of other gates."""
        candidate_returns = ReturnSeries(name="c", returns=[0.01] * 10)
        portfolio_returns = ReturnSeries(name="p", returns=[0.005] * 10)
        member_returns = [ReturnSeries(name="m", returns=[0.0] * 10)]

        approved, report_path, repl_path = admit_candidate(
            candidate=candidate_trend,
            params=sample_params,
            integrity_ok=False,
            candidate_returns=candidate_returns,
            portfolio_returns=portfolio_returns,
            member_returns=member_returns,
            existing_identities=[],
        )
        assert approved is False
        assert report_path is not None
        assert repl_path is None

    def test_replacement_mode_requires_target(self, candidate_trend, sample_params, tmp_governance_root):
        """Replacement mode without target key → denial."""
        candidate_returns = ReturnSeries(name="c", returns=[0.01] * 10)
        portfolio_returns = ReturnSeries(name="p", returns=[0.005] * 10)
        member_returns = [ReturnSeries(name="m", returns=[0.0] * 10)]

        approved, _, _ = admit_candidate(
            candidate=candidate_trend,
            params=sample_params,
            integrity_ok=True,
            candidate_returns=candidate_returns,
            portfolio_returns=portfolio_returns,
            member_returns=member_returns,
            existing_identities=[],
            replacement_mode=True,
            replacement_target_key=None,
        )
        assert approved is False

    def test_replacement_mode_with_dominance_overrides_correlation(
        self, candidate_trend, sample_params, tmp_governance_root
    ):
        """Even if correlation high, dominance proof can override."""
        # High correlation series
        candidate_returns = ReturnSeries(name="c", returns=[0.1] * 10)
        portfolio_returns = ReturnSeries(name="p", returns=[0.1] * 10)
        member_returns = [ReturnSeries(name="m", returns=[0.1] * 10)]

        dominance_proof = {
            "expected_score_new": 0.15,
            "expected_score_old": 0.10,
            "risk_adj_new": 0.12,
            "risk_adj_old": 0.12,
        }

        approved, report_path, repl_path = admit_candidate(
            candidate=candidate_trend,
            params=sample_params,
            integrity_ok=True,
            candidate_returns=candidate_returns,
            portfolio_returns=portfolio_returns,
            member_returns=member_returns,
            existing_identities=[],
            replacement_mode=True,
            replacement_target_key="old_key",
            dominance_proof=dominance_proof,
        )
        # Should be approved because dominance proof overrides correlation
        assert approved is True
        assert repl_path is not None  # replacement report written

    def test_admission_writes_artifacts(self, candidate_trend, sample_params, tmp_governance_root):
        """Admission always writes an admission report artifact."""
        candidate_returns = ReturnSeries(name="c", returns=[0.01] * 10)
        portfolio_returns = ReturnSeries(name="p", returns=[0.005] * 10)
        member_returns = [ReturnSeries(name="m", returns=[0.0] * 10)]

        approved, report_path, repl_path = admit_candidate(
            candidate=candidate_trend,
            params=sample_params,
            integrity_ok=True,
            candidate_returns=candidate_returns,
            portfolio_returns=portfolio_returns,
            member_returns=member_returns,
            existing_identities=[],
        )
        assert report_path is not None
        # Ensure file exists
        full_path = tmp_governance_root.return_value / report_path
        assert full_path.exists()
        assert full_path.suffix == ".json"