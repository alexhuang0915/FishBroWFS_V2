"""Server-side path selector - 禁止 file upload，只允許伺服器端路徑"""

import os
import glob
from pathlib import Path
from typing import List, Optional


# 允許的根目錄（根據 HUMAN TASKS 要求）
ALLOWED_ROOTS = [
    Path("/home/fishbro/FishBroData/raw"),
    Path("/home/fishbro/FishBroData/normalized"),  # 如果未來有
    Path(__file__).parent.parent.parent.parent / "data",  # 專案內的 data 目錄
]


def list_txt_candidates(base_dir: Path, pattern: str = "*.txt", limit: int = 200) -> List[str]:
    """
    列出指定目錄下的 txt 檔案候選
    
    Args:
        base_dir: 基礎目錄
        pattern: 檔案模式（預設 *.txt）
        limit: 返回的檔案數量限制
    
    Returns:
        List[str]: 檔案路徑清單（相對路徑或絕對路徑）
    
    Raises:
        ValueError: 如果 base_dir 不在 allowed roots 內
    """
    # 驗證 base_dir 是否在 allowed roots 內
    if not _is_allowed_path(base_dir):
        raise ValueError(f"base_dir 不在允許的根目錄內: {base_dir}")
    
    if not base_dir.exists():
        return []
    
    # 使用 glob 尋找檔案
    search_pattern = str(base_dir / "**" / pattern)
    files = []
    
    try:
        for file_path in glob.glob(search_pattern, recursive=True):
            if os.path.isfile(file_path):
                # 返回相對路徑（相對於 base_dir）
                rel_path = os.path.relpath(file_path, base_dir)
                files.append(rel_path)
                
                if len(files) >= limit:
                    break
    except (OSError, PermissionError):
        pass
    
    # 排序（按修改時間或名稱）
    files.sort()
    return files


def validate_server_path(p: str, allowed_roots: Optional[List[Path]] = None) -> str:
    """
    驗證伺服器端路徑是否在允許的根目錄內
    
    Args:
        p: 要驗證的路徑
        allowed_roots: 允許的根目錄清單（預設使用 ALLOWED_ROOTS）
    
    Returns:
        str: 驗證後的路徑（絕對路徑）
    
    Raises:
        ValueError: 如果路徑不在 allowed roots 內
        FileNotFoundError: 如果路徑不存在
    """
    if allowed_roots is None:
        allowed_roots = ALLOWED_ROOTS
    
    # 轉換為 Path 物件
    path = Path(p)
    
    # 如果是相對路徑，嘗試解析為絕對路徑
    if not path.is_absolute():
        # 嘗試在每個 allowed root 下尋找
        for root in allowed_roots:
            candidate = root / path
            if candidate.exists():
                path = candidate
                break
        else:
            # 如果找不到，使用第一個 allowed root 作為基礎
            path = allowed_roots[0] / path
    
    # 確保路徑是絕對路徑
    path = path.resolve()
    
    # 檢查是否在 allowed roots 內
    if not _is_allowed_path(path, allowed_roots):
        raise ValueError(f"路徑不在允許的根目錄內: {path}")
    
    # 檢查路徑是否存在
    if not path.exists():
        raise FileNotFoundError(f"路徑不存在: {path}")
    
    return str(path)


def _is_allowed_path(path: Path, allowed_roots: Optional[List[Path]] = None) -> bool:
    """
    檢查路徑是否在 allowed roots 內
    
    Args:
        path: 要檢查的路徑
        allowed_roots: 允許的根目錄清單
    
    Returns:
        bool: 是否允許
    """
    if allowed_roots is None:
        allowed_roots = ALLOWED_ROOTS
    
    path = path.resolve()
    
    for root in allowed_roots:
        root = root.resolve()
        try:
            # 檢查 path 是否是 root 的子目錄
            if path.is_relative_to(root):
                return True
        except (AttributeError, ValueError):
            # Python 3.8 兼容性：使用 str 比較
            if str(path).startswith(str(root) + os.sep):
                return True
    
    return False


def get_allowed_roots_info() -> List[dict]:
    """
    獲取 allowed roots 的資訊
    
    Returns:
        List[dict]: 每個 root 的資訊
    """
    info = []
    for root in ALLOWED_ROOTS:
        exists = root.exists()
        info.append({
            "path": str(root),
            "exists": exists,
            "readable": os.access(root, os.R_OK) if exists else False,
            "files_count": _count_files(root) if exists else 0,
        })
    return info


def _count_files(directory: Path) -> int:
    """計算目錄下的檔案數量"""
    if not directory.exists() or not directory.is_dir():
        return 0
    
    try:
        return sum(1 for _ in directory.rglob("*") if _.is_file())
    except (OSError, PermissionError):
        return 0


def browse_directory(directory: Path, pattern: str = "*") -> List[dict]:
    """
    瀏覽目錄內容
    
    Args:
        directory: 要瀏覽的目錄
        pattern: 檔案模式
    
    Returns:
        List[dict]: 目錄內容
    """
    if not _is_allowed_path(directory):
        raise ValueError(f"目錄不在允許的根目錄內: {directory}")
    
    if not directory.exists() or not directory.is_dir():
        return []
    
    contents = []
    try:
        for item in directory.iterdir():
            try:
                stat = item.stat()
                contents.append({
                    "name": item.name,
                    "path": str(item),
                    "is_dir": item.is_dir(),
                    "is_file": item.is_file(),
                    "size": stat.st_size if item.is_file() else 0,
                    "mtime": stat.st_mtime,
                    "readable": os.access(item, os.R_OK),
                })
            except (OSError, PermissionError):
                continue
        
        # 排序：目錄在前，檔案在後
        contents.sort(key=lambda x: (not x["is_dir"], x["name"].lower()))
    except (OSError, PermissionError):
        pass
    
    return contents