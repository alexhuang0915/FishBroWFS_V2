
"""
測試 slippage stress gate 模組
"""
import pytest
import numpy as np
from FishBroWFS_V2.control.research_slippage_stress import (
    StressResult,
    CommissionConfig,
    compute_stress_matrix,
    survive_s2,
    compute_stress_test_passed,
    generate_stress_report,
)
from FishBroWFS_V2.core.slippage_policy import SlippagePolicy


class TestStressResult:
    """測試 StressResult 資料類別"""

    def test_stress_result(self):
        """基本建立"""
        result = StressResult(
            level="S2",
            slip_ticks=2,
            net_after_cost=1000.0,
            gross_profit=1500.0,
            gross_loss=-500.0,
            profit_factor=3.0,
            mdd_after_cost=200.0,
            trades=50,
        )
        assert result.level == "S2"
        assert result.slip_ticks == 2
        assert result.net_after_cost == 1000.0
        assert result.gross_profit == 1500.0
        assert result.gross_loss == -500.0
        assert result.profit_factor == 3.0
        assert result.mdd_after_cost == 200.0
        assert result.trades == 50


class TestCommissionConfig:
    """測試 CommissionConfig"""

    def test_default(self):
        """測試預設值"""
        config = CommissionConfig(per_side_usd={"MNQ": 0.5})
        assert config.per_side_usd == {"MNQ": 0.5}
        assert config.default_per_side_usd == 0.0

    def test_get_commission(self):
        """測試取得手續費"""
        config = CommissionConfig(
            per_side_usd={"MNQ": 0.5, "MES": 0.25},
            default_per_side_usd=1.0,
        )
        assert config.per_side_usd.get("MNQ") == 0.5
        assert config.per_side_usd.get("MES") == 0.25
        assert config.per_side_usd.get("MXF") is None
        assert config.default_per_side_usd == 1.0


class TestComputeStressMatrix:
    """測試 compute_stress_matrix"""

    def test_basic(self):
        """基本測試：使用模擬的 fills"""
        bars = {
            "open": np.array([100.0, 101.0]),
            "high": np.array([102.0, 103.0]),
            "low": np.array([99.0, 100.0]),
            "close": np.array([101.0, 102.0]),
        }
        # 模擬一筆交易：買入 100，賣出 102，數量 1
        fills = [
            {
                "entry_price": 100.0,
                "exit_price": 102.0,
                "entry_side": "buy",
                "exit_side": "sell",
                "quantity": 1.0,
            }
        ]
        commission_config = CommissionConfig(per_side_usd={"MNQ": 0.5})
        slippage_policy = SlippagePolicy()
        tick_size_map = {"MNQ": 0.25}
        symbol = "MNQ"

        results = compute_stress_matrix(
            bars, fills, commission_config, slippage_policy, tick_size_map, symbol
        )

        # 檢查四個等級都存在
        assert set(results.keys()) == {"S0", "S1", "S2", "S3"}

        # 計算預期值
        # S0: slip_ticks=0, 無滑價
        # 毛利 = (102 - 100) * 1 = 2.0
        # 手續費每邊 0.5，兩邊共 1.0
        # 淨利 = 2.0 - 1.0 = 1.0
        result_s0 = results["S0"]
        assert result_s0.slip_ticks == 0
        assert result_s0.net_after_cost == pytest.approx(1.0)
        assert result_s0.gross_profit == pytest.approx(2.0)  # 毛利
        assert result_s0.gross_loss == pytest.approx(0.0)
        assert result_s0.profit_factor == float("inf")  # gross_loss == 0
        assert result_s0.trades == 1

        # S1: slip_ticks=1
        # 買入價格調整：100 + 1*0.25 = 100.25
        # 賣出價格調整：102 - 1*0.25 = 101.75
        # 毛利 = (101.75 - 100.25) = 1.5
        # 淨利 = 1.5 - 1.0 = 0.5
        result_s1 = results["S1"]
        assert result_s1.slip_ticks == 1
        assert result_s1.net_after_cost == pytest.approx(0.5)

        # S2: slip_ticks=2
        # 買入價格調整：100 + 2*0.25 = 100.5
        # 賣出價格調整：102 - 2*0.25 = 101.5
        # 毛利 = (101.5 - 100.5) = 1.0
        # 淨利 = 1.0 - 1.0 = 0.0
        result_s2 = results["S2"]
        assert result_s2.slip_ticks == 2
        assert result_s2.net_after_cost == pytest.approx(0.0)

        # S3: slip_ticks=3
        # 買入價格調整：100 + 3*0.25 = 100.75
        # 賣出價格調整：102 - 3*0.25 = 101.25
        # 毛利 = (101.25 - 100.75) = 0.5
        # 淨利 = 0.5 - 1.0 = -0.5
        result_s3 = results["S3"]
        assert result_s3.slip_ticks == 3
        assert result_s3.net_after_cost == pytest.approx(-0.5)

    def test_missing_tick_size(self):
        """測試缺少 tick_size"""
        bars = {"open": np.array([100.0])}
        fills = []
        commission_config = CommissionConfig(per_side_usd={})
        slippage_policy = SlippagePolicy()
        tick_size_map = {}  # 缺少 MNQ
        symbol = "MNQ"

        with pytest.raises(ValueError, match="商品 MNQ 的 tick_size 無效或缺失"):
            compute_stress_matrix(
                bars, fills, commission_config, slippage_policy, tick_size_map, symbol
            )

    def test_invalid_tick_size(self):
        """測試無效 tick_size"""
        bars = {"open": np.array([100.0])}
        fills = []
        commission_config = CommissionConfig(per_side_usd={})
        slippage_policy = SlippagePolicy()
        tick_size_map = {"MNQ": 0.0}  # tick_size <= 0
        symbol = "MNQ"

        with pytest.raises(ValueError, match="商品 MNQ 的 tick_size 無效或缺失"):
            compute_stress_matrix(
                bars, fills, commission_config, slippage_policy, tick_size_map, symbol
            )

    def test_empty_fills(self):
        """測試無成交"""
        bars = {"open": np.array([100.0])}
        fills = []
        commission_config = CommissionConfig(per_side_usd={"MNQ": 0.5})
        slippage_policy = SlippagePolicy()
        tick_size_map = {"MNQ": 0.25}
        symbol = "MNQ"

        results = compute_stress_matrix(
            bars, fills, commission_config, slippage_policy, tick_size_map, symbol
        )

        # 所有等級的淨利應為 0，交易次數 0
        for level in ["S0", "S1", "S2", "S3"]:
            result = results[level]
            assert result.net_after_cost == 0.0
            assert result.gross_profit == 0.0
            assert result.gross_loss == 0.0
            assert result.profit_factor == 1.0  # gross_loss == 0, gross_profit == 0
            assert result.trades == 0

    def test_multiple_fills(self):
        """測試多筆成交"""
        bars = {"open": np.array([100.0])}
        fills = [
            {
                "entry_price": 100.0,
                "exit_price": 102.0,
                "entry_side": "buy",
                "exit_side": "sell",
                "quantity": 1.0,
            },
            {
                "entry_price": 102.0,
                "exit_price": 101.0,
                "entry_side": "sellshort",
                "exit_side": "buytocover",
                "quantity": 2.0,
            },
        ]
        commission_config = CommissionConfig(per_side_usd={"MNQ": 0.0})  # 無手續費
        slippage_policy = SlippagePolicy()
        tick_size_map = {"MNQ": 0.25}
        symbol = "MNQ"

        results = compute_stress_matrix(
            bars, fills, commission_config, slippage_policy, tick_size_map, symbol
        )

        # 檢查 S0 淨利
        # 第一筆：毛利 2.0
        # 第二筆：空頭，賣出 102，買回 101，毛利 (102-101)*2 = 2.0
        # 總毛利 4.0，無手續費
        result_s0 = results["S0"]
        assert result_s0.net_after_cost == pytest.approx(4.0)
        assert result_s0.trades == 2


class TestSurviveS2:
    """測試 survive_s2 函數"""

    def test_pass_all_criteria(self):
        """通過所有條件"""
        result = StressResult(
            level="S2",
            slip_ticks=2,
            net_after_cost=1000.0,
            gross_profit=1500.0,
            gross_loss=-500.0,
            profit_factor=3.0,
            mdd_after_cost=200.0,
            trades=50,
        )
        assert survive_s2(result, min_trades=30, min_pf=1.10) is True

    def test_fail_min_trades(self):
        """交易次數不足"""
        result = StressResult(
            level="S2",
            slip_ticks=2,
            net_after_cost=1000.0,
            gross_profit=1500.0,
            gross_loss=-500.0,
            profit_factor=3.0,
            mdd_after_cost=200.0,
            trades=20,
        )
        assert survive_s2(result, min_trades=30) is False

    def test_fail_min_pf(self):
        """盈利因子不足"""
        result = StressResult(
            level="S2",
            slip_ticks=2,
            net_after_cost=1000.0,
            gross_profit=1100.0,
            gross_loss=-1000.0,
            profit_factor=1.05,  # 低於 1.10
            mdd_after_cost=200.0,
            trades=50,
        )
        assert survive_s2(result, min_pf=1.10) is False

    def test_fail_max_mdd_abs(self):
        """最大回撤超過限制"""
        result = StressResult(
            level="S2",
            slip_ticks=2,
            net_after_cost=1000.0,
            gross_profit=1500.0,
            gross_loss=-500.0,
            profit_factor=3.0,
            mdd_after_cost=500.0,
            trades=50,
        )
        # 設定 max_mdd_abs = 400
        assert survive_s2(result, max_mdd_abs=400.0) is False
        # 設定 max_mdd_abs = 600 則通過
        assert survive_s2(result, max_mdd_abs=600.0) is True

    def test_infinite_profit_factor(self):
        """無虧損（盈利因子無限大）"""
        result = StressResult(
            level="S2",
            slip_ticks=2,
            net_after_cost=1000.0,
            gross_profit=1000.0,
            gross_loss=0.0,
            profit_factor=float("inf"),
            mdd_after_cost=0.0,
            trades=50,
        )
        assert survive_s2(result, min_pf=1.10) is True

    def test_zero_gross_profit(self):
        """無盈利（盈利因子 1.0）"""
        result = StressResult(
            level="S2",
            slip_ticks=2,
            net_after_cost=0.0,
            gross_profit=0.0,
            gross_loss=0.0,
            profit_factor=1.0,
            mdd_after_cost=0.0,
            trades=50,
        )
        # profit_factor = 1.0 < 1.10
        assert survive_s2(result, min_pf=1.10) is False


class TestComputeStressTestPassed:
    """測試 compute_stress_test_passed"""

    def test_passed(self):
        """S3 淨利 > 0"""
        results = {
            "S3": StressResult(
                level="S3",
                slip_ticks=3,
                net_after_cost=100.0,
                gross_profit=200.0,
                gross_loss=-100.0,
                profit_factor=2.0,
                mdd_after_cost=50.0,
                trades=30,
            )
        }
        assert compute_stress_test_passed(results) is True

    def test_failed(self):
        """S3 淨利 <= 0"""
        results = {
            "S3": StressResult(
                level="S3",
                slip_ticks=3,
                net_after_cost=-50.0,
                gross_profit=100.0,
                gross_loss=-150.0,
                profit_factor=0.666,
                mdd_after_cost=200.0,
                trades=30,
            )
        }
        assert compute_stress_test_passed(results) is False

    def test_missing_stress_level(self):
        """缺少 stress_level"""
        results = {
            "S0": StressResult(
                level="S0",
                slip_ticks=0,
                net_after_cost=100.0,
                gross_profit=200.0,
                gross_loss=-100.0,
                profit_factor=2.0,
                mdd_after_cost=50.0,
                trades=30,
            )
        }
        assert compute_stress_test_passed(results, stress_level="S3") is False

    def test_custom_stress_level(self):
        """自訂 stress_level"""
        results = {
            "S2": StressResult(
                level="S2",
                slip_ticks=2,
                net_after_cost=50.0,
                gross_profit=200.0,
                gross_loss=-150.0,
                profit_factor=1.333,
                mdd_after_cost=100.0,
                trades=30,
            )
        }
        assert compute_stress_test_passed(results, stress_level="S2") is True


class TestGenerateStressReport:
    """測試 generate_stress_report"""

    def test_generate_report(self):
        """產生完整報告"""
        results = {
            "S0": StressResult(
                level="S0",
                slip_ticks=0,
                net_after_cost=1000.0,
                gross_profit=1500.0,
                gross_loss=-500.0,
                profit_factor=3.0,
                mdd_after_cost=200.0,
                trades=50,
            ),
            "S1": StressResult(
                level="S1",
                slip_ticks=1,
                net_after_cost=800.0,
                gross_profit=1300.0,
                gross_loss=-500.0,
                profit_factor=2.6,
                mdd_after_cost=250.0,
                trades=50,
            ),
        }
        slippage_policy = SlippagePolicy()
        survive_s2_flag = True
        stress_test_passed_flag = False

        report = generate_stress_report(
            results, slippage_policy, survive_s2_flag, stress_test_passed_flag
        )

        # 檢查結構
        assert "slippage_policy" in report
        assert "stress_matrix" in report
        assert "survive_s2" in report
        assert "stress_test_passed" in report

        # 檢查 policy 內容
        policy = report["slippage_policy"]
        assert policy["definition"] == "per_fill_per_side"
        assert policy["levels"] == {"S0": 0, "S1": 1, "S2": 2, "S3": 3}
        assert policy["selection_level"] == "S2"
        assert policy["stress_level"] == "S3"
        assert policy["mc_execution_level"] == "S1"

        # 檢查矩陣
        matrix = report["stress_matrix"]
        assert set(matrix.keys()) == {"S0", "S1"}
        assert matrix["S0"]["slip_ticks"] == 0
        assert matrix["S0"]["net_after_cost"] == 1000.0
        assert matrix["S0"]["gross_profit"] == 1500


