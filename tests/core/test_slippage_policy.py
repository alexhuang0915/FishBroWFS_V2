
"""
測試 slippage_policy 模組
"""
import pytest
from core.slippage_policy import (
    SlippagePolicy,
    apply_slippage_to_price,
    round_to_tick,
    compute_slippage_cost_per_side,
    compute_round_trip_slippage_cost,
)


class TestSlippagePolicy:
    """測試 SlippagePolicy 類別"""

    def test_default_policy(self):
        """測試預設政策"""
        policy = SlippagePolicy()
        assert policy.definition == "per_fill_per_side"
        assert policy.levels == {"S0": 0, "S1": 1, "S2": 2, "S3": 3}
        assert policy.selection_level == "S2"
        assert policy.stress_level == "S3"
        assert policy.mc_execution_level == "S1"

    def test_custom_levels(self):
        """測試自訂 levels"""
        policy = SlippagePolicy(
            levels={"S0": 0, "S1": 2, "S2": 4, "S3": 6},
            selection_level="S1",
            stress_level="S3",
            mc_execution_level="S2",
        )
        assert policy.get_ticks("S0") == 0
        assert policy.get_ticks("S1") == 2
        assert policy.get_ticks("S2") == 4
        assert policy.get_ticks("S3") == 6
        assert policy.get_selection_ticks() == 2
        assert policy.get_stress_ticks() == 6
        assert policy.get_mc_execution_ticks() == 4

    def test_validation_definition(self):
        """驗證 definition 必須為 per_fill_per_side"""
        with pytest.raises(ValueError, match="definition 必須為 'per_fill_per_side'"):
            SlippagePolicy(definition="invalid")

    def test_validation_missing_levels(self):
        """驗證缺少必要等級"""
        with pytest.raises(ValueError, match="levels 缺少必要等級"):
            SlippagePolicy(levels={"S0": 0, "S1": 1})  # 缺少 S2, S3

    def test_validation_level_not_in_levels(self):
        """驗證 selection_level 不存在於 levels"""
        with pytest.raises(ValueError, match="等級 S5 不存在於 levels 中"):
            SlippagePolicy(selection_level="S5")

    def test_validation_ticks_non_negative(self):
        """驗證 ticks 必須為非負整數"""
        with pytest.raises(ValueError, match="ticks 必須為非負整數"):
            SlippagePolicy(levels={"S0": -1, "S1": 1, "S2": 2, "S3": 3})
        with pytest.raises(ValueError, match="ticks 必須為非負整數"):
            SlippagePolicy(levels={"S0": 0, "S1": 1.5, "S2": 2, "S3": 3})

    def test_get_ticks_key_error(self):
        """測試取得不存在的等級"""
        policy = SlippagePolicy()
        with pytest.raises(KeyError):
            policy.get_ticks("S99")


class TestApplySlippageToPrice:
    """測試 apply_slippage_to_price 函數"""

    def test_buy_side(self):
        """測試買入方向"""
        # tick_size = 0.25, slip_ticks = 2
        adjusted = apply_slippage_to_price(100.0, "buy", 2, 0.25)
        assert adjusted == 100.5  # 100 + 2*0.25

    def test_buytocover_side(self):
        """測試 buytocover 方向（同 buy）"""
        adjusted = apply_slippage_to_price(100.0, "buytocover", 1, 0.25)
        assert adjusted == 100.25

    def test_sell_side(self):
        """測試賣出方向"""
        adjusted = apply_slippage_to_price(100.0, "sell", 3, 0.25)
        assert adjusted == 99.25  # 100 - 3*0.25

    def test_sellshort_side(self):
        """測試 sellshort 方向（同 sell）"""
        adjusted = apply_slippage_to_price(100.0, "sellshort", 1, 0.25)
        assert adjusted == 99.75

    def test_zero_slippage(self):
        """測試零滑價"""
        adjusted = apply_slippage_to_price(100.0, "buy", 0, 0.25)
        assert adjusted == 100.0

    def test_negative_price_protection(self):
        """測試價格保護（避免負值）"""
        adjusted = apply_slippage_to_price(0.5, "sell", 3, 0.25)
        # 0.5 - 0.75 = -0.25 → 調整為 0.0
        assert adjusted == 0.0

    def test_invalid_tick_size(self):
        """測試無效 tick_size"""
        with pytest.raises(ValueError, match="tick_size 必須 > 0"):
            apply_slippage_to_price(100.0, "buy", 1, 0.0)
        with pytest.raises(ValueError, match="tick_size 必須 > 0"):
            apply_slippage_to_price(100.0, "buy", 1, -0.1)

    def test_invalid_slip_ticks(self):
        """測試無效 slip_ticks"""
        with pytest.raises(ValueError, match="slip_ticks 必須 >= 0"):
            apply_slippage_to_price(100.0, "buy", -1, 0.25)

    def test_invalid_side(self):
        """測試無效 side"""
        with pytest.raises(ValueError, match="無效的 side"):
            apply_slippage_to_price(100.0, "invalid", 1, 0.25)


class TestRoundToTick:
    """測試 round_to_tick 函數"""

    def test_rounding(self):
        """測試四捨五入"""
        # tick_size = 0.25
        assert round_to_tick(100.12, 0.25) == 100.0   # 100.12 / 0.25 = 400.48 → round 400 → 100.0
        assert round_to_tick(100.13, 0.25) == 100.25  # 100.13 / 0.25 = 400.52 → round 401 → 100.25
        assert round_to_tick(100.25, 0.25) == 100.25
        assert round_to_tick(100.375, 0.25) == 100.5

    def test_invalid_tick_size(self):
        """測試無效 tick_size"""
        with pytest.raises(ValueError, match="tick_size 必須 > 0"):
            round_to_tick(100.0, 0.0)
        with pytest.raises(ValueError, match="tick_size 必須 > 0"):
            round_to_tick(100.0, -0.1)


class TestComputeSlippageCost:
    """測試滑價成本計算函數"""

    def test_compute_slippage_cost_per_side(self):
        """測試單邊滑價成本"""
        # slip_ticks=2, tick_size=0.25, quantity=1
        cost = compute_slippage_cost_per_side(2, 0.25, 1.0)
        assert cost == 0.5  # 2 * 0.25 * 1

        # quantity=10
        cost = compute_slippage_cost_per_side(2, 0.25, 10.0)
        assert cost == 5.0  # 2 * 0.25 * 10

    def test_compute_round_trip_slippage_cost(self):
        """測試來回滑價成本"""
        # slip_ticks=2, tick_size=0.25, quantity=1
        cost = compute_round_trip_slippage_cost(2, 0.25, 1.0)
        assert cost == 1.0  # 2 * (2 * 0.25 * 1)

        # quantity=10
        cost = compute_round_trip_slippage_cost(2, 0.25, 10.0)
        assert cost == 10.0  # 2 * (2 * 0.25 * 10)

    def test_invalid_parameters(self):
        """測試無效參數"""
        with pytest.raises(ValueError, match="slip_ticks 必須 >= 0"):
            compute_slippage_cost_per_side(-1, 0.25, 1.0)
        with pytest.raises(ValueError, match="tick_size 必須 > 0"):
            compute_slippage_cost_per_side(2, 0.0, 1.0)
        with pytest.raises(ValueError, match="slip_ticks 必須 >= 0"):
            compute_round_trip_slippage_cost(-1, 0.25, 1.0)
        with pytest.raises(ValueError, match="tick_size 必須 > 0"):
            compute_round_trip_slippage_cost(2, 0.0, 1.0)


