
"""靜態檢查：FishBroWFS_V2.gui.nicegui 不得 import control.research_runner / wfs.runner"""

import ast
from pathlib import Path


def check_imports_in_file(file_path: Path, forbidden_imports: list) -> list:
    """檢查檔案中的導入語句"""
    violations = []
    
    try:
        content = file_path.read_text()
        tree = ast.parse(content)
        
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    for forbidden in forbidden_imports:
                        if alias.name == forbidden or alias.name.startswith(forbidden + "."):
                            violations.append(f"{file_path}:{node.lineno}: import {alias.name}")
            
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    for forbidden in forbidden_imports:
                        if node.module == forbidden or node.module.startswith(forbidden + "."):
                            violations.append(f"{file_path}:{node.lineno}: from {node.module} import ...")
    
    except (SyntaxError, UnicodeDecodeError):
        # 忽略無法解析的檔案
        pass
    
    return violations


def test_nicegui_no_runner_imports():
    """測試 NiceGUI 模組沒有導入 runner"""
    
    nicegui_dir = Path(__file__).parent.parent.parent / "src" / "FishBroWFS_V2" / "gui" / "nicegui"
    
    # 禁止的導入
    forbidden_imports = [
        "FishBroWFS_V2.control.research_runner",
        "FishBroWFS_V2.wfs.runner",
        "FishBroWFS_V2.control.research_cli",
        "FishBroWFS_V2.control.worker",
        "FishBroWFS_V2.core.features",  # 可能觸發 build
        "FishBroWFS_V2.data.layout",    # 可能觸發 IO
    ]
    
    violations = []
    
    # 檢查所有 Python 檔案
    for py_file in nicegui_dir.rglob("*.py"):
        violations.extend(check_imports_in_file(py_file, forbidden_imports))
    
    # 如果有違規，輸出詳細資訊
    if violations:
        print("發現禁止的導入:")
        for violation in violations:
            print(f"  - {violation}")
    
    assert len(violations) == 0, f"發現 {len(violations)} 個禁止的導入"


def test_nicegui_api_is_thin():
    """測試 API 模組是薄接口"""
    
    api_file = Path(__file__).parent.parent.parent / "src" / "FishBroWFS_V2" / "gui" / "nicegui" / "api.py"
    
    content = api_file.read_text()
    
    # 檢查是否只有薄接口函數
    # API 應該只包含資料類別和簡單的 HTTP 呼叫
    forbidden_patterns = [
        "def run_wfs",
        "def compute",
        "def calculate",
        "import numpy",
        "import pandas",
        "from FishBroWFS_V2.core",
        "from FishBroWFS_V2.data",
    ]
    
    violations = []
    for pattern in forbidden_patterns:
        if pattern in content:
            violations.append(f"發現禁止的模式: {pattern}")
    
    # 檢查是否有實際的計算邏輯
    lines = content.split('\n')
    for i, line in enumerate(lines):
        if "def " in line and "compute" in line.lower():
            violations.append(f"行 {i+1}: 可能包含計算邏輯: {line.strip()}")
    
    if violations:
        print("API 模組可能不是薄接口:")
        for violation in violations:
            print(f"  - {violation}")
    
    assert len(violations) == 0, f"API 模組可能包含計算邏輯"


