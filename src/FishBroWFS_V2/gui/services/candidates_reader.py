"""
Candidates Reader - 讀取 outputs/seasons/{season}/research/ 下的 canonical_results.json 和 research_index.json
Phase 4: 使用 season_context 作為單一真相來源
"""

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import List, Dict, Any, Optional

from FishBroWFS_V2.core.season_context import (
    current_season,
    canonical_results_path,
    research_index_path,
)

logger = logging.getLogger(__name__)

# 官方路徑契約 - 使用 season_context
def get_canonical_results_path(season: Optional[str] = None) -> Path:
    """返回 canonical_results.json 的路徑"""
    return canonical_results_path(season)

def get_research_index_path(season: Optional[str] = None) -> Path:
    """返回 research_index.json 的路徑"""
    return research_index_path(season)

@dataclass
class CanonicalResult:
    """Canonical Results 的單一項目"""
    run_id: str
    strategy_id: str
    symbol: str
    bars: int
    net_profit: float
    max_drawdown: float
    score_final: float
    score_net_mdd: float
    trades: int
    start_date: str
    end_date: str
    sharpe: Optional[float] = None
    profit_factor: Optional[float] = None
    portfolio_id: Optional[str] = None
    portfolio_version: Optional[str] = None
    strategy_version: Optional[str] = None
    timeframe_min: Optional[int] = None

@dataclass
class ResearchIndexEntry:
    """Research Index 的單一項目"""
    run_id: str
    season: str
    stage: str
    mode: str
    strategy_id: str
    dataset_id: str
    created_at: str
    status: str
    manifest_path: Optional[str] = None

def load_canonical_results(season: Optional[str] = None) -> List[CanonicalResult]:
    """
    載入 canonical_results.json
    
    Args:
        season: Season identifier (e.g., "2026Q1")
    
    Returns:
        List[CanonicalResult]: 解析後的 canonical results 列表
        
    Raises:
        FileNotFoundError: 如果檔案不存在
        json.JSONDecodeError: 如果 JSON 格式錯誤
    """
    canonical_path = get_canonical_results_path(season)
    
    if not canonical_path.exists():
        logger.warning(f"Canonical results file not found: {canonical_path}")
        return []
    
    try:
        with open(canonical_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        if not isinstance(data, list):
            logger.error(f"Canonical results should be a list, got {type(data)}")
            return []
        
        results = []
        for item in data:
            try:
                result = CanonicalResult(
                    run_id=item.get("run_id", ""),
                    strategy_id=item.get("strategy_id", ""),
                    symbol=item.get("symbol", "UNKNOWN"),
                    bars=item.get("bars", 0),
                    net_profit=item.get("net_profit", 0.0),
                    max_drawdown=item.get("max_drawdown", 0.0),
                    score_final=item.get("score_final", 0.0),
                    score_net_mdd=item.get("score_net_mdd", 0.0),
                    trades=item.get("trades", 0),
                    start_date=item.get("start_date", ""),
                    end_date=item.get("end_date", ""),
                    sharpe=item.get("sharpe"),
                    profit_factor=item.get("profit_factor"),
                    portfolio_id=item.get("portfolio_id"),
                    portfolio_version=item.get("portfolio_version"),
                    strategy_version=item.get("strategy_version"),
                    timeframe_min=item.get("timeframe_min"),
                )
                results.append(result)
            except Exception as e:
                logger.warning(f"Failed to parse canonical result item: {item}, error: {e}")
                continue
        
        logger.info(f"Loaded {len(results)} canonical results from {canonical_path}")
        return results
        
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse canonical_results.json: {e}")
        return []
    except Exception as e:
        logger.error(f"Unexpected error loading canonical results: {e}")
        return []

def load_research_index(season: Optional[str] = None) -> List[ResearchIndexEntry]:
    """
    載入 research_index.json
    
    Args:
        season: Season identifier (e.g., "2026Q1")
    
    Returns:
        List[ResearchIndexEntry]: 解析後的 research index 列表
        
    Raises:
        FileNotFoundError: 如果檔案不存在
        json.JSONDecodeError: 如果 JSON 格式錯誤
    """
    research_path = get_research_index_path(season)
    
    if not research_path.exists():
        logger.warning(f"Research index file not found: {research_path}")
        return []
    
    try:
        with open(research_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        if not isinstance(data, list):
            logger.error(f"Research index should be a list, got {type(data)}")
            return []
        
        entries = []
        for item in data:
            try:
                entry = ResearchIndexEntry(
                    run_id=item.get("run_id", ""),
                    season=item.get("season", ""),
                    stage=item.get("stage", ""),
                    mode=item.get("mode", ""),
                    strategy_id=item.get("strategy_id", ""),
                    dataset_id=item.get("dataset_id", ""),
                    created_at=item.get("created_at", ""),
                    status=item.get("status", ""),
                    manifest_path=item.get("manifest_path"),
                )
                entries.append(entry)
            except Exception as e:
                logger.warning(f"Failed to parse research index item: {item}, error: {e}")
                continue
        
        logger.info(f"Loaded {len(entries)} research index entries from {research_path}")
        return entries
        
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse research_index.json: {e}")
        return []
    except Exception as e:
        logger.error(f"Unexpected error loading research index: {e}")
        return []

def get_canonical_results_by_strategy(strategy_id: str, season: Optional[str] = None) -> List[CanonicalResult]:
    """
    根據 strategy_id 篩選 canonical results
    
    Args:
        strategy_id: 策略 ID
        season: Season identifier (e.g., "2026Q1")
        
    Returns:
        List[CanonicalResult]: 符合條件的結果列表
    """
    results = load_canonical_results(season)
    return [r for r in results if r.strategy_id == strategy_id]

def get_canonical_results_by_run_id(run_id: str, season: Optional[str] = None) -> Optional[CanonicalResult]:
    """
    根據 run_id 查找 canonical result
    
    Args:
        run_id: Run ID
        season: Season identifier (e.g., "2026Q1")
        
    Returns:
        Optional[CanonicalResult]: 找到的結果，如果沒有則返回 None
    """
    results = load_canonical_results(season)
    for result in results:
        if result.run_id == run_id:
            return result
    return None

def get_research_index_by_run_id(run_id: str, season: Optional[str] = None) -> Optional[ResearchIndexEntry]:
    """
    根據 run_id 查找 research index entry
    
    Args:
        run_id: Run ID
        season: Season identifier (e.g., "2026Q1")
        
    Returns:
        Optional[ResearchIndexEntry]: 找到的項目，如果沒有則返回 None
    """
    entries = load_research_index(season)
    for entry in entries:
        if entry.run_id == run_id:
            return entry
    return None

def get_research_index_by_season(season: str) -> List[ResearchIndexEntry]:
    """
    根據 season 篩選 research index
    
    Args:
        season: Season ID
        
    Returns:
        List[ResearchIndexEntry]: 符合條件的項目列表
    """
    entries = load_research_index(season)
    return [e for e in entries if e.season == season]

def get_combined_candidate_info(run_id: str, season: Optional[str] = None) -> Dict[str, Any]:
    """
    結合 canonical results 和 research index 的資訊
    
    Args:
        run_id: Run ID
        season: Season identifier (e.g., "2026Q1")
        
    Returns:
        Dict[str, Any]: 合併後的候選人資訊
    """
    canonical = get_canonical_results_by_run_id(run_id, season)
    research = get_research_index_by_run_id(run_id, season)
    
    result = {
        "run_id": run_id,
        "canonical": canonical.__dict__ if canonical else None,
        "research": research.__dict__ if research else None,
    }
    
    return result

def refresh_canonical_results(season: Optional[str] = None) -> bool:
    """
    刷新 canonical results（目前只是重新讀取檔案）
    
    Args:
        season: Season identifier (e.g., "2026Q1")
    
    Returns:
        bool: 是否成功刷新
    """
    try:
        # 目前只是重新讀取檔案，未來可以加入重新生成邏輯
        results = load_canonical_results(season)
        logger.info(f"Refreshed canonical results, found {len(results)} entries")
        return True
    except Exception as e:
        logger.error(f"Failed to refresh canonical results: {e}")
        return False

def refresh_research_index(season: Optional[str] = None) -> bool:
    """
    刷新 research index（目前只是重新讀取檔案）
    
    Args:
        season: Season identifier (e.g., "2026Q1")
    
    Returns:
        bool: 是否成功刷新
    """
    try:
        # 目前只是重新讀取檔案，未來可以加入重新生成邏輯
        entries = load_research_index(season)
        logger.info(f"Refreshed research index, found {len(entries)} entries")
        return True
    except Exception as e:
        logger.error(f"Failed to refresh research index: {e}")
        return False