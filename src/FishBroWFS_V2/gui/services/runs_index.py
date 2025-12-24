"""Runs Index 服務 - 禁止全量掃描，只讀最新 N 個 run"""

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Dict, Any
from datetime import datetime


@dataclass(frozen=True)
class RunIndexRow:
    """Run 索引行，包含必要 metadata"""
    run_id: str
    run_dir: str
    mtime: float
    season: str
    status: str
    mode: str
    strategy_id: Optional[str]
    dataset_id: Optional[str]
    stage: Optional[str]
    manifest_path: Optional[str]
    
    @property
    def mtime_iso(self) -> str:
        """返回 ISO 格式的修改時間"""
        return datetime.fromtimestamp(self.mtime).isoformat()
    
    @property
    def is_archived(self) -> bool:
        """檢查是否已歸檔（路徑包含 .archive）"""
        return ".archive" in self.run_dir


class RunsIndex:
    """Runs Index 管理器 - 只掃最新 N 個 run，避免全量掃描"""
    
    def __init__(self, outputs_root: Path, limit: int = 50) -> None:
        self.outputs_root = Path(outputs_root)
        self.limit = limit
        self._cache: List[RunIndexRow] = []
        self._cache_time: float = 0.0
        self._cache_ttl: float = 30.0  # 快取 30 秒
        
    def build(self) -> None:
        """建立索引（掃描 seasons/<season>/runs 目錄）"""
        rows: List[RunIndexRow] = []
        
        # 掃描所有 season 目錄
        seasons_dir = self.outputs_root / "seasons"
        if not seasons_dir.exists():
            self._cache = []
            self._cache_time = time.time()
            return
        
        for season_dir in seasons_dir.iterdir():
            if not season_dir.is_dir():
                continue
                
            season = season_dir.name
            runs_dir = season_dir / "runs"
            
            if not runs_dir.exists():
                continue
                
            # 只掃描 runs 目錄下的直接子目錄
            run_dirs = []
            for run_path in runs_dir.iterdir():
                if run_path.is_dir():
                    try:
                        mtime = run_path.stat().st_mtime
                        run_dirs.append((run_path, mtime, season))
                    except OSError:
                        continue
            
            # 按修改時間排序，取最新的
            run_dirs.sort(key=lambda x: x[1], reverse=True)
            
            for run_path, mtime, season in run_dirs[:self.limit]:
                row = self._parse_run_dir(run_path, mtime, season)
                if row:
                    rows.append(row)
        
        # 按修改時間全局排序
        rows.sort(key=lambda x: x.mtime, reverse=True)
        rows = rows[:self.limit]
        
        self._cache = rows
        self._cache_time = time.time()
    
    def _parse_run_dir(self, run_path: Path, mtime: float, season: str) -> Optional[RunIndexRow]:
        """解析單個 run 目錄，讀取 manifest.json（如果存在）"""
        run_id = run_path.name
        manifest_path = run_path / "manifest.json"
        
        # 預設值
        status = "unknown"
        mode = "unknown"
        strategy_id = None
        dataset_id = None
        stage = None
        
        # 嘗試讀取 manifest.json
        if manifest_path.exists():
            try:
                with open(manifest_path, 'r', encoding='utf-8') as f:
                    manifest = json.load(f)
                
                # 從 manifest 提取資訊
                status = manifest.get("status", "unknown")
                mode = manifest.get("mode", "unknown")
                strategy_id = manifest.get("strategy_id")
                dataset_id = manifest.get("dataset_id")
                stage = manifest.get("stage")
                
                # 如果 stage 不存在，嘗試從 run_id 推斷
                if stage is None and "stage" in run_id:
                    for stage_name in ["stage0", "stage1", "stage2", "stage3"]:
                        if stage_name in run_id:
                            stage = stage_name
                            break
            except (json.JSONDecodeError, OSError):
                # 如果讀取失敗，使用預設值
                pass
        
        # 從 run_id 推斷 stage（如果尚未設定）
        if stage is None:
            if "stage0" in run_id:
                stage = "stage0"
            elif "stage1" in run_id:
                stage = "stage1"
            elif "stage2" in run_id:
                stage = "stage2"
            elif "demo" in run_id:
                stage = "demo"
        
        return RunIndexRow(
            run_id=run_id,
            run_dir=str(run_path),
            mtime=mtime,
            season=season,
            status=status,
            mode=mode,
            strategy_id=strategy_id,
            dataset_id=dataset_id,
            stage=stage,
            manifest_path=str(manifest_path) if manifest_path.exists() else None
        )
    
    def refresh(self) -> None:
        """刷新索引（重建快取）"""
        self.build()
    
    def list(self, season: Optional[str] = None, include_archived: bool = False) -> List[RunIndexRow]:
        """列出 runs（可選按 season 過濾）"""
        # 如果快取過期，重新建立
        if time.time() - self._cache_time > self._cache_ttl:
            self.build()
        
        rows = self._cache
        
        # 按 season 過濾
        if season is not None:
            rows = [r for r in rows if r.season == season]
        
        # 過濾歸檔的 runs
        if not include_archived:
            rows = [r for r in rows if not r.is_archived]
        
        return rows
    
    def get(self, run_id: str) -> Optional[RunIndexRow]:
        """根據 run_id 獲取單個 run"""
        # 如果快取過期，重新建立
        if time.time() - self._cache_time > self._cache_ttl:
            self.build()
        
        for row in self._cache:
            if row.run_id == run_id:
                return row
        
        # 如果不在快取中，嘗試直接查找
        # 掃描所有 season 目錄尋找該 run_id
        seasons_dir = self.outputs_root / "seasons"
        if seasons_dir.exists():
            for season_dir in seasons_dir.iterdir():
                if not season_dir.is_dir():
                    continue
                    
                runs_dir = season_dir / "runs"
                if not runs_dir.exists():
                    continue
                
                run_path = runs_dir / run_id
                if run_path.exists() and run_path.is_dir():
                    try:
                        mtime = run_path.stat().st_mtime
                        return self._parse_run_dir(run_path, mtime, season_dir.name)
                    except OSError:
                        pass
        
        return None


# Singleton instance for app-level caching
_global_index: Optional[RunsIndex] = None

def get_global_index(outputs_root: Optional[Path] = None) -> RunsIndex:
    """獲取全域 RunsIndex 實例（singleton）"""
    global _global_index
    
    if _global_index is None:
        if outputs_root is None:
            # 預設使用專案根目錄下的 outputs
            outputs_root = Path(__file__).parent.parent.parent.parent / "outputs"
        _global_index = RunsIndex(outputs_root)
        _global_index.build()
    
    return _global_index