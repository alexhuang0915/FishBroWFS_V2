"""
Test deterministic weight allocation (vol‑targeting model).
"""
import pytest
from portfolio.models.governance_models import GovernanceParams
from portfolio.governance.allocation import allocate_weights


@pytest.fixture
def sample_params():
    return GovernanceParams(
        risk_model="vol_target",
        vol_floor=0.02,
        w_min=0.0,
        w_max=0.35,
    )


class TestAllocationDeterminism:
    def test_weights_sum_to_one(self, sample_params):
        """Allocated weights must sum to 1.0 within tolerance."""
        strategy_keys = ["A", "B", "C"]
        vol_ests = {"A": 0.10, "B": 0.15, "C": 0.20}
        weights = allocate_weights(strategy_keys, vol_ests, sample_params)
        total = sum(weights.values())
        assert pytest.approx(total, rel=1e-9) == 1.0

    def test_deterministic_ordering(self, sample_params):
        """Same inputs produce identical weights regardless of key order."""
        vol_ests = {"A": 0.10, "B": 0.15, "C": 0.20}
        weights1 = allocate_weights(["A", "B", "C"], vol_ests, sample_params)
        weights2 = allocate_weights(["C", "A", "B"], vol_ests, sample_params)
        # Because sorting is applied internally, order should not affect final mapping
        assert weights1["A"] == weights2["A"]
        assert weights1["B"] == weights2["B"]
        assert weights1["C"] == weights2["C"]

    def test_clamping_respects_w_max(self, sample_params):
        """No single weight exceeds w_max."""
        # Make one volatility extremely low → raw weight huge
        strategy_keys = ["A", "B"]
        vol_ests = {"A": 0.001, "B": 0.50}
        params = GovernanceParams(
            risk_model="vol_target",
            vol_floor=0.02,
            w_min=0.0,
            w_max=0.5,  # w_max * n >= 1 ensures feasibility
        )
        weights = allocate_weights(strategy_keys, vol_ests, params)
        for w in weights.values():
            assert w <= params.w_max + 1e-12

    def test_clamping_respects_w_min(self, sample_params):
        """If w_min > 0, no weight falls below w_min."""
        strategy_keys = ["A", "B", "C"]
        vol_ests = {"A": 0.10, "B": 0.15, "C": 0.20}
        params = GovernanceParams(
            risk_model="vol_target",
            vol_floor=0.02,
            w_min=0.10,
            w_max=0.50,
        )
        weights = allocate_weights(strategy_keys, vol_ests, params)
        for w in weights.values():
            assert w >= params.w_min - 1e-12

    def test_vol_floor_prevents_infinite(self, sample_params):
        """Extremely low volatility is floored to vol_floor."""
        strategy_keys = ["A", "B"]
        vol_ests = {"A": 0.001, "B": 0.50}
        params = GovernanceParams(
            risk_model="vol_target",
            vol_floor=0.05,
            w_min=0.0,
            w_max=1.0,
        )
        weights = allocate_weights(strategy_keys, vol_ests, params)
        # A's raw weight = 1 / max(0.001, 0.05) = 1 / 0.05 = 20
        # B's raw weight = 1 / 0.50 = 2
        # total raw = 22, weight A = 20/22 ≈ 0.909
        expected_a = 20.0 / 22.0
        assert pytest.approx(weights["A"], rel=1e-9) == expected_a

    def test_equal_vols_yield_equal_weights(self, sample_params):
        """If all volatilities are equal, weights should be equal."""
        strategy_keys = ["A", "B", "C", "D"]
        vol_ests = {k: 0.12 for k in strategy_keys}
        weights = allocate_weights(strategy_keys, vol_ests, sample_params)
        for w in weights.values():
            assert pytest.approx(w, rel=1e-9) == 0.25

    def test_missing_vol_est_uses_floor(self, sample_params):
        """If a key is missing from vol_ests, treat as vol_floor."""
        strategy_keys = ["A", "B"]
        vol_ests = {"A": 0.10}  # B missing
        params = GovernanceParams(
            risk_model="vol_target",
            vol_floor=0.05,
            w_min=0.0,
            w_max=1.0,
        )
        weights = allocate_weights(strategy_keys, vol_ests, params)
        # B's vol = vol_floor = 0.05 → raw = 20
        # A's raw = 1 / 0.10 = 10
        # total raw = 30, weight A = 10/30 ≈ 0.333, weight B = 20/30 ≈ 0.667
        assert pytest.approx(weights["A"], rel=1e-9) == 10.0 / 30.0
        assert pytest.approx(weights["B"], rel=1e-9) == 20.0 / 30.0

    def test_zero_total_raw_fallback_equal(self, sample_params):
        """If all raw weights are zero (vol infinite), fallback to equal weights."""
        strategy_keys = ["A", "B", "C"]
        # Use huge volatility so raw ≈ 0
        vol_ests = {k: 1e9 for k in strategy_keys}
        params = GovernanceParams(
            risk_model="vol_target",
            vol_floor=0.0,
            w_min=0.0,
            w_max=1.0,
        )
        weights = allocate_weights(strategy_keys, vol_ests, params)
        for w in weights.values():
            assert pytest.approx(w, rel=1e-9) == 1.0 / len(strategy_keys)