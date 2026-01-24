"""
Backtest Kernel (Layer 2).

Pure Function: f(Data, Strategy) -> Result.
"""

from __future__ import annotations

import pandas as pd
import importlib
import logging
from typing import List, Tuple, Optional

from contracts.data_models import DataSnapshot
from contracts.strategy import StrategySpec
from contracts.research import ResearchResult, PerformanceMetrics, Trade

logger = logging.getLogger(__name__)

class BacktestKernel:
    """
    Stateless execution engine for strategies.
    """
    
    @staticmethod
    def run(df_data: pd.DataFrame, strategy_spec: StrategySpec, snapshot_id: str) -> ResearchResult:
        """
        Execute a strategy against a dataframe.
        
        Args:
            df_data: DataFrame containing Price + Features (aligned index).
            strategy_spec: The strategy hypothesis.
            snapshot_id: ID of the raw data used.
            
        Returns:
            ResearchResult
        """
        # 1. Load Strategy Logic
        strategy_class = BacktestKernel._resolve_strategy(strategy_spec.class_path)
        strategy_instance = strategy_class(strategy_spec.params)
        
        # 2. Compute signals then simulate (vectorized kernel).
        signals = BacktestKernel._compute_signals(df_data, strategy_instance)
        algo_returns = BacktestKernel._compute_algo_returns(df_data, signals)
        
        # 4. Aggregate Metrics
        total_types = (1 + algo_returns).prod() - 1
        sharpe = 0.0
        if algo_returns.std() > 0:
            sharpe = (algo_returns.mean() / algo_returns.std()) * (252**0.5) # Annualized
            
        # Drawdown
        cum_returns = (1 + algo_returns).cumprod()
        peak = cum_returns.cummax()
        dd = (cum_returns - peak) / peak
        max_dd = dd.min()
        
        # Dummy trades list (vectorized approx)
        trades_count = int(signals.diff().abs().sum() / 2) # Rough approx of turns
        
        metrics = PerformanceMetrics(
            total_return=float(total_types),
            sharpe_ratio=float(sharpe),
            max_drawdown=float(max_dd),
            win_rate=0.5, # Placeholder
            total_trades=trades_count
        )
        
        # 5. Construct Result
        import hashlib
        run_id = hashlib.sha256(f"{snapshot_id}:{strategy_spec.compute_hash()}".encode()).hexdigest()
        
        return ResearchResult(
            run_id=run_id,
            strategy_hash=strategy_spec.compute_hash(),
            data_snapshot_id=snapshot_id,
            metrics=metrics,
            trades=[] # Populating detailed trade list requires event-loop logic, skipped for MVP
        )

    @staticmethod
    def run_with_equity(
        df_data: pd.DataFrame,
        strategy_spec: StrategySpec,
        snapshot_id: str,
        *,
        initial_equity: float = 10_000.0,
    ) -> Tuple[ResearchResult, pd.Series]:
        """
        Like `run`, but also returns the full-resolution equity curve as a Series.
        This is used by WFS stitching / UI without duplicating signal/return logic.
        """
        strategy_class = BacktestKernel._resolve_strategy(strategy_spec.class_path)
        strategy_instance = strategy_class(strategy_spec.params)

        signals = BacktestKernel._compute_signals(df_data, strategy_instance)
        algo_returns = BacktestKernel._compute_algo_returns(df_data, signals)
        equity = initial_equity * (1.0 + algo_returns).cumprod()

        result = BacktestKernel.run(df_data, strategy_spec, snapshot_id)
        return result, equity

    @staticmethod
    def _compute_signals(df_data: pd.DataFrame, strategy_instance) -> pd.Series:
        # For this prototype, strategy class must implement `compute_signals(df)->Series`.
        try:
            signals = strategy_instance.compute_signals(df_data)
        except Exception as e:
            raise RuntimeError(f"Strategy Execution Failed: {e}") from e

        if len(signals) != len(df_data):
            signals = signals.reindex(df_data.index).fillna(0)
        return signals

    @staticmethod
    def _compute_algo_returns(df_data: pd.DataFrame, signals: pd.Series) -> pd.Series:
        # Shift signals by 1 to avoid lookahead bias (Signal at T acts on T+1 Return)
        returns = df_data["close"].pct_change().fillna(0)
        return signals.shift(1).fillna(0) * returns

    @staticmethod
    def _resolve_strategy(class_path: str):
        module_name, class_name = class_path.rsplit(".", 1)
        module = importlib.import_module(module_name)
        return getattr(module, class_name)
