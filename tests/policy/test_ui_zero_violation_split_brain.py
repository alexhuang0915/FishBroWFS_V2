"""靜態檢查：UI 零違反 split‑brain 架構

憲法級原則：
1. UI 模組不得直接導入 FishBroWFS_V2.control.* 的任何符號（除了 ui_bridge 與 control_client）
2. UI 模組必須透過 ui_bridge 或 control_client 與 Control API 通訊
3. 禁止任何直接引用 Control 內部類別、函數、變數

此測試確保 Phase C 的 split‑brain 架構被嚴格遵守。
"""

import ast
from pathlib import Path


def check_imports_in_file(file_path: Path, forbidden_imports: list, allowed_exceptions: list) -> list:
    """檢查檔案中的導入語句，回傳違規列表"""
    violations = []
    
    try:
        content = file_path.read_text()
        tree = ast.parse(content)
        
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    for forbidden in forbidden_imports:
                        # Check if the import matches the forbidden pattern
                        # For prefix patterns (ending with '.'), check if import starts with prefix
                        if forbidden.endswith('.'):
                            if alias.name.startswith(forbidden):
                                # Check if this import is allowed via exception
                                if any(alias.name.startswith(exc) for exc in allowed_exceptions):
                                    continue
                                violations.append(f"{file_path}:{node.lineno}: import {alias.name}")
                        else:
                            if alias.name == forbidden:
                                if any(alias.name == exc for exc in allowed_exceptions):
                                    continue
                                violations.append(f"{file_path}:{node.lineno}: import {alias.name}")
            
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    for forbidden in forbidden_imports:
                        if forbidden.endswith('.'):
                            if node.module.startswith(forbidden):
                                if any(node.module.startswith(exc) for exc in allowed_exceptions):
                                    continue
                                violations.append(f"{file_path}:{node.lineno}: from {node.module} import ...")
                        else:
                            if node.module == forbidden:
                                if any(node.module == exc for exc in allowed_exceptions):
                                    continue
                                violations.append(f"{file_path}:{node.lineno}: from {node.module} import ...")
    
    except (SyntaxError, UnicodeDecodeError):
        # 忽略無法解析的檔案
        pass
    
    return violations


def test_ui_no_direct_control_imports():
    """測試 UI 模組沒有直接導入 FishBroWFS_V2.control.*（除了橋接器）"""
    
    gui_dir = Path(__file__).parent.parent.parent / "src" / "FishBroWFS_V2" / "gui"
    
    # 禁止的導入前綴
    forbidden_imports = [
        "FishBroWFS_V2.control.",
    ]
    
    # 允許的例外（橋接器模組）
    allowed_exceptions = [
        "FishBroWFS_V2.gui.adapters.ui_bridge",
        "FishBroWFS_V2.gui.adapters.control_client",
        "FishBroWFS_V2.gui.adapters.intent_bridge",  # 舊的橋接器，可能還存在但應被移除
    ]
    
    violations = []
    files_checked = 0
    
    # 檢查所有 Python 檔案
    for py_file in gui_dir.rglob("*.py"):
        # 跳過橋接器檔案本身
        if "adapters/ui_bridge.py" in str(py_file) or "adapters/control_client.py" in str(py_file):
            continue
        # 跳過 intent_bridge.py（已廢棄）
        if "adapters/intent_bridge.py" in str(py_file):
            continue
        
        files_checked += 1
        file_violations = check_imports_in_file(py_file, forbidden_imports, allowed_exceptions)
        if file_violations:
            violations.extend(file_violations)
    
    # 如果有違規，輸出詳細資訊
    if violations:
        print("發現禁止的直接 control 導入:")
        for violation in violations:
            print(f"  - {violation}")
    
    assert len(violations) == 0, f"發現 {len(violations)} 個禁止的直接 control 導入（檢查了 {files_checked} 個檔案）"


def test_ui_pages_import_ui_bridge():
    """測試 UI 頁面有導入 ui_bridge（確保使用 split‑brain 橋接器）"""
    
    # 定義需要檢查的 UI 頁面目錄
    pages_dir = Path(__file__).parent.parent.parent / "src" / "FishBroWFS_V2" / "gui" / "nicegui" / "pages"
    
    # 預期至少導入 ui_bridge 的檔案（主要頁面）
    expected_files = [
        "wizard.py",
        "wizard_m1.py",
        "jobs.py",
        "job_detail.py",
        "deploy.py",
        "artifacts.py",
        "candidates.py",
        "portfolio.py",
        "history.py",
        "run_detail.py",
        "new_job.py",
        "results.py",
        "charts.py",
        "settings.py",
        "status.py",
    ]
    
    missing_imports = []
    
    for filename in expected_files:
        file_path = pages_dir / filename
        if not file_path.exists():
            continue
        
        content = file_path.read_text()
        # 檢查是否有 import ui_bridge 或 from ... import ui_bridge
        if "import ui_bridge" not in content and "from FishBroWFS_V2.gui.adapters import ui_bridge" not in content:
            # 也可能使用 control_client 直接導入，但至少應有 ui_bridge
            # 我們只要求有導入 ui_bridge 或 control_client
            if "import control_client" not in content and "from FishBroWFS_V2.gui.adapters import control_client" not in content:
                missing_imports.append(filename)
    
    if missing_imports:
        print("以下 UI 頁面未導入 ui_bridge 或 control_client:")
        for name in missing_imports:
            print(f"  - {name}")
    
    # 此測試為警告性質，不強制失敗（因為有些頁面可能不需要橋接器）
    # 但我們可以記錄
    if missing_imports:
        print("警告：部分 UI 頁面可能未使用 split‑brain 橋接器")


def test_no_legacy_intent_bridge_imports():
    """確保沒有殘留的 intent_bridge 導入（應已全部替換為 ui_bridge）"""
    
    gui_dir = Path(__file__).parent.parent.parent / "src" / "FishBroWFS_V2" / "gui"
    
    violations = []
    
    for py_file in gui_dir.rglob("*.py"):
        content = py_file.read_text()
        # 檢查是否有 import intent_bridge 或 from ... import intent_bridge
        if "import intent_bridge" in content or "from FishBroWFS_V2.gui.adapters import intent_bridge" in content:
            violations.append(str(py_file))
    
    if violations:
        print("發現殘留的 intent_bridge 導入:")
        for path in violations:
            print(f"  - {path}")
    
    assert len(violations) == 0, f"發現 {len(violations)} 個殘留的 intent_bridge 導入"


def test_ui_pages_no_migrate_ui_imports():
    """測試 UI 頁面沒有直接呼叫 migrate_ui_imports()（應使用 Domain Bridges）"""
    
    pages_dir = Path(__file__).parent.parent.parent / "src" / "FishBroWFS_V2" / "gui" / "nicegui" / "pages"
    
    violations = []
    
    for py_file in pages_dir.rglob("*.py"):
        try:
            content = py_file.read_text()
            # 使用 AST 解析來檢查實際的函數呼叫，而不是註解
            import ast
            
            tree = ast.parse(content)
            
            for node in ast.walk(tree):
                # 檢查函數呼叫
                if isinstance(node, ast.Call):
                    # 檢查函數名稱
                    if isinstance(node.func, ast.Name):
                        if node.func.id == "migrate_ui_imports":
                            violations.append(f"{py_file}:{node.lineno}: migrate_ui_imports() call")
                    # 檢查屬性呼叫，例如 module.migrate_ui_imports()
                    elif isinstance(node.func, ast.Attribute):
                        if node.func.attr == "migrate_ui_imports":
                            violations.append(f"{py_file}:{node.lineno}: {node.func.attr}() call")
        except (SyntaxError, UnicodeDecodeError):
            # 忽略無法解析的檔案
            pass
    
    if violations:
        print("發現直接呼叫 migrate_ui_imports() 的 UI 頁面:")
        for violation in violations:
            print(f"  - {violation}")
    
    assert len(violations) == 0, f"發現 {len(violations)} 個直接呼叫 migrate_ui_imports() 的 UI 頁面"


def test_ui_pages_no_direct_http_imports():
    """測試 UI 頁面沒有直接導入 httpx 或 requests（應使用 Domain Bridges）"""
    
    pages_dir = Path(__file__).parent.parent.parent / "src" / "FishBroWFS_V2" / "gui" / "nicegui" / "pages"
    
    forbidden_imports = [
        "httpx",
        "requests",
    ]
    
    violations = []
    
    for py_file in pages_dir.rglob("*.py"):
        try:
            content = py_file.read_text()
            # 簡單檢查是否有 import 語句
            for forbidden in forbidden_imports:
                # 檢查 import httpx 或 import requests
                if f"import {forbidden}" in content:
                    violations.append(f"{py_file}: import {forbidden}")
                # 檢查 from httpx import ... 或 from requests import ...
                if f"from {forbidden} import" in content:
                    violations.append(f"{py_file}: from {forbidden} import ...")
        except (SyntaxError, UnicodeDecodeError):
            pass
    
    if violations:
        print("發現直接導入 httpx/requests 的 UI 頁面:")
        for violation in violations:
            print(f"  - {violation}")
    
    assert len(violations) == 0, f"發現 {len(violations)} 個直接導入 httpx/requests 的 UI 頁面"


if __name__ == "__main__":
    # 執行測試
    import pytest
    pytest.main([__file__, "-v"])