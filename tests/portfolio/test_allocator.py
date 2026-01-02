"""
Unit tests for RiskParityAllocator (Article IV.3 Risk Budgeting).
"""
import math
import pytest
from portfolio.governance_state import StrategyRecord, StrategyState
from portfolio.allocator import RiskParityAllocator


def create_strategy(strategy_id: str, volatility: float | None) -> StrategyRecord:
    """Helper to create a StrategyRecord with given volatility metric."""
    metrics = {}
    if volatility is not None:
        metrics["volatility"] = volatility
    return StrategyRecord(
        strategy_id=strategy_id,
        version_hash="dummy_hash",
        state=StrategyState.CANDIDATE,
        config={},
        metrics=metrics,
    )


class TestRiskParityAllocator:
    """Test suite for RiskParityAllocator.allocate."""

    def test_empty_list(self):
        """allocate([]) should return empty dict."""
        result = RiskParityAllocator.allocate([])
        assert result == {}

    def test_equal_risk(self):
        """Two strategies with same volatility should get equal allocations."""
        s1 = create_strategy("S1", 0.10)
        s2 = create_strategy("S2", 0.10)
        result = RiskParityAllocator.allocate([s1, s2], total_capital=1.0)
        assert len(result) == 2
        assert math.isclose(result["S1"], 0.5, rel_tol=1e-9)
        assert math.isclose(result["S2"], 0.5, rel_tol=1e-9)
        assert math.isclose(result["S1"] + result["S2"], 1.0, rel_tol=1e-9)

    def test_high_vs_low_volatility(self):
        """
        A with vol=0.10, B with vol=0.20 => A should receive exactly 2× B.
        Weights: A = 2/3 ≈ 0.666..., B = 1/3 ≈ 0.333...
        """
        s_a = create_strategy("A", 0.10)
        s_b = create_strategy("B", 0.20)
        result = RiskParityAllocator.allocate([s_a, s_b], total_capital=1.0)
        assert len(result) == 2
        # A weight = (1/0.10) / (1/0.10 + 1/0.20) = 10 / (10 + 5) = 10/15 = 2/3
        expected_a = 2.0 / 3.0
        expected_b = 1.0 / 3.0
        assert math.isclose(result["A"], expected_a, rel_tol=1e-9)
        assert math.isclose(result["B"], expected_b, rel_tol=1e-9)
        # Verify exact 2× relationship
        assert math.isclose(result["A"], 2.0 * result["B"], rel_tol=1e-9)

    def test_flatline_floor(self):
        """
        Very low volatility (0.001) should be floored to MIN_VOL_FLOOR (0.02).
        Thus inverse vol = 1/0.02 = 50, not 1/0.001 = 1000.
        """
        s_low = create_strategy("low", 0.001)
        s_normal = create_strategy("normal", 0.10)
        result = RiskParityAllocator.allocate([s_low, s_normal], total_capital=1.0)
        # Expected: low inv = 1/0.02 = 50, normal inv = 1/0.10 = 10
        # total inv = 60, weight low = 50/60 ≈ 0.83333, weight normal = 10/60 ≈ 0.16667
        expected_low = 50.0 / 60.0
        expected_normal = 10.0 / 60.0
        assert math.isclose(result["low"], expected_low, rel_tol=1e-9)
        assert math.isclose(result["normal"], expected_normal, rel_tol=1e-9)

    def test_missing_metric(self):
        """Strategy with missing volatility gets 0.0, other valid strategy gets all capital."""
        s_valid = create_strategy("valid", 0.15)
        s_missing = create_strategy("missing", None)  # metrics dict empty
        result = RiskParityAllocator.allocate([s_valid, s_missing], total_capital=1.0)
        assert result["missing"] == 0.0
        assert math.isclose(result["valid"], 1.0, rel_tol=1e-9)

    def test_nan_volatility(self):
        """NaN volatility is treated as invalid -> allocation 0.0."""
        import numpy as np
        s_nan = create_strategy("nan", float("nan"))
        s_ok = create_strategy("ok", 0.12)
        result = RiskParityAllocator.allocate([s_nan, s_ok], total_capital=1.0)
        assert result["nan"] == 0.0
        assert math.isclose(result["ok"], 1.0, rel_tol=1e-9)

    def test_zero_or_negative_volatility(self):
        """Zero or negative volatility is invalid -> allocation 0.0."""
        s_zero = create_strategy("zero", 0.0)
        s_negative = create_strategy("negative", -0.05)
        s_ok = create_strategy("ok", 0.08)
        result = RiskParityAllocator.allocate([s_zero, s_negative, s_ok], total_capital=1.0)
        assert result["zero"] == 0.0
        assert result["negative"] == 0.0
        assert math.isclose(result["ok"], 1.0, rel_tol=1e-9)

    def test_all_invalid(self):
        """If all strategies are invalid, all allocations are 0.0."""
        s1 = create_strategy("s1", None)
        s2 = create_strategy("s2", float("nan"))
        s3 = create_strategy("s3", -0.1)
        result = RiskParityAllocator.allocate([s1, s2, s3], total_capital=1.0)
        assert result == {"s1": 0.0, "s2": 0.0, "s3": 0.0}

    def test_total_capital_scaling(self):
        """total_capital parameter scales allocations appropriately."""
        s1 = create_strategy("s1", 0.10)
        s2 = create_strategy("s2", 0.20)
        result = RiskParityAllocator.allocate([s1, s2], total_capital=100.0)
        # Weights are 2/3 and 1/3 as before
        assert math.isclose(result["s1"], 100.0 * 2.0 / 3.0, rel_tol=1e-9)
        assert math.isclose(result["s2"], 100.0 * 1.0 / 3.0, rel_tol=1e-9)

    def test_ordering_preserved(self):
        """Allocation dict includes all input strategy_ids, even invalid ones."""
        strategies = [
            create_strategy("first", None),
            create_strategy("second", 0.10),
            create_strategy("third", 0.20),
            create_strategy("fourth", float("nan")),
        ]
        result = RiskParityAllocator.allocate(strategies, total_capital=1.0)
        assert set(result.keys()) == {"first", "second", "third", "fourth"}
        assert result["first"] == 0.0
        assert result["fourth"] == 0.0
        # second and third should share the capital
        total_valid = result["second"] + result["third"]
        assert math.isclose(total_valid, 1.0, rel_tol=1e-9)