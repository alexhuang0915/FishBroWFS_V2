
"""
Fingerprint index 儲存與讀取

提供 atomic write 與 deterministic JSON 序列化。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from contracts.fingerprint import FingerprintIndex
from contracts.dimensions import canonical_json


def fingerprint_index_path(
    season: str,
    dataset_id: str,
    outputs_root: Optional[Path] = None
) -> Path:
    """
    取得指紋索引檔案路徑
    
    建議位置：outputs/fingerprints/{season}/{dataset_id}/fingerprint_index.json
    
    Args:
        season: 季節標記，例如 "2026Q1"
        dataset_id: 資料集 ID
        outputs_root: 輸出根目錄，預設為專案根目錄下的 outputs/
    
    Returns:
        檔案路徑
    """
    if outputs_root is None:
        # 從專案根目錄開始
        project_root = Path(__file__).parent.parent.parent
        outputs_root = project_root / "outputs"
    
    # 建立路徑
    path = outputs_root / "fingerprints" / season / dataset_id / "fingerprint_index.json"
    return path


def write_fingerprint_index(
    index: FingerprintIndex,
    path: Path,
    *,
    ensure_parents: bool = True
) -> None:
    """
    寫入指紋索引（原子寫入）
    
    使用 tmp + replace 模式確保 atomic write。
    
    Args:
        index: 要寫入的 FingerprintIndex
        path: 目標檔案路徑
        ensure_parents: 是否建立父目錄
    
    Raises:
        IOError: 寫入失敗
    """
    if ensure_parents:
        path.parent.mkdir(parents=True, exist_ok=True)
    
    # 轉換為字典
    data = index.model_dump()
    
    # 使用 canonical_json 確保 deterministic 輸出
    json_str = canonical_json(data)
    
    # 原子寫入：先寫到暫存檔案，再移動
    temp_path = path.with_suffix(".json.tmp")
    
    try:
        # 寫入暫存檔案
        temp_path.write_text(json_str, encoding="utf-8")
        
        # 移動到目標位置（原子操作）
        temp_path.replace(path)
        
    except Exception as e:
        # 清理暫存檔案
        if temp_path.exists():
            try:
                temp_path.unlink()
            except:
                pass
        
        raise IOError(f"寫入指紋索引失敗 {path}: {e}")
    
    # 驗證寫入的檔案可以正確讀回
    try:
        loaded = load_fingerprint_index(path)
        if loaded.index_sha256 != index.index_sha256:
            raise IOError(f"寫入後驗證失敗: hash 不匹配")
    except Exception as e:
        # 如果驗證失敗，刪除檔案
        if path.exists():
            try:
                path.unlink()
            except:
                pass
        raise IOError(f"指紋索引驗證失敗 {path}: {e}")


def load_fingerprint_index(path: Path) -> FingerprintIndex:
    """
    載入指紋索引
    
    Args:
        path: 檔案路徑
    
    Returns:
        FingerprintIndex
    
    Raises:
        FileNotFoundError: 檔案不存在
        ValueError: JSON 解析失敗或 schema 驗證失敗
    """
    if not path.exists():
        raise FileNotFoundError(f"指紋索引檔案不存在: {path}")
    
    try:
        content = path.read_text(encoding="utf-8")
    except (IOError, OSError) as e:
        raise ValueError(f"無法讀取指紋索引檔案 {path}: {e}")
    
    try:
        data = json.loads(content)
    except json.JSONDecodeError as e:
        raise ValueError(f"指紋索引 JSON 解析失敗 {path}: {e}")
    
    try:
        return FingerprintIndex(**data)
    except Exception as e:
        raise ValueError(f"指紋索引 schema 驗證失敗 {path}: {e}")


def load_fingerprint_index_if_exists(path: Path) -> Optional[FingerprintIndex]:
    """
    載入指紋索引（如果存在）
    
    Args:
        path: 檔案路徑
    
    Returns:
        FingerprintIndex 或 None（如果檔案不存在）
    
    Raises:
        ValueError: JSON 解析失敗或 schema 驗證失敗
    """
    if not path.exists():
        return None
    
    return load_fingerprint_index(path)


def delete_fingerprint_index(path: Path) -> None:
    """
    刪除指紋索引檔案
    
    Args:
        path: 檔案路徑
    """
    if path.exists():
        path.unlink()


def list_fingerprint_indices(
    season: str,
    outputs_root: Optional[Path] = None
) -> list[tuple[str, Path]]:
    """
    列出指定季節的所有指紋索引
    
    Args:
        season: 季節標記
        outputs_root: 輸出根目錄
    
    Returns:
        (dataset_id, path) 的列表
    """
    if outputs_root is None:
        project_root = Path(__file__).parent.parent.parent
        outputs_root = project_root / "outputs"
    
    season_dir = outputs_root / "fingerprints" / season
    
    if not season_dir.exists():
        return []
    
    indices = []
    
    for dataset_dir in season_dir.iterdir():
        if dataset_dir.is_dir():
            index_path = dataset_dir / "fingerprint_index.json"
            if index_path.exists():
                indices.append((dataset_dir.name, index_path))
    
    # 按 dataset_id 排序
    indices.sort(key=lambda x: x[0])
    
    return indices


def ensure_fingerprint_directory(
    season: str,
    dataset_id: str,
    outputs_root: Optional[Path] = None
) -> Path:
    """
    確保指紋索引目錄存在
    
    Args:
        season: 季節標記
        dataset_id: 資料集 ID
        outputs_root: 輸出根目錄
    
    Returns:
        目錄路徑
    """
    path = fingerprint_index_path(season, dataset_id, outputs_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path.parent


