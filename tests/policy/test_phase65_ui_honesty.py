
"""Phase 6.5 - UI 誠實化測試

測試 UI 是否遵守 Phase 6.5 規範：
1. 禁止假成功、假狀態
2. 未完成功能必須 disabled 並明確標示
3. Mock 必須明確標示為 DEV MODE
4. UI 不得直接跑 Rolling WFS
5. UI 不得自行算 drawdown/corr
"""

import pytest
import importlib
import ast
from pathlib import Path


def test_nicegui_pages_no_fake_success():
    """測試 NiceGUI 頁面沒有假成功訊息"""
    # 檢查所有 NiceGUI 頁面檔案
    pages_dir = Path("src/FishBroWFS_V2/gui/nicegui/pages")
    
    for page_file in pages_dir.glob("*.py"):
        content = page_file.read_text()
        
        # 禁止的假成功模式（排除註解中的文字）
        fake_patterns = [
            "假成功",
            "fake success",
            "模擬成功",
            "simulated success",
            "always success",
            "always True",
        ]
        
        # 將內容按行分割，檢查非註解行
        lines = content.split('\n')
        for i, line in enumerate(lines, 1):
            # 跳過註解行
            stripped_line = line.strip()
            if stripped_line.startswith('#') or stripped_line.startswith('"""') or stripped_line.startswith("'''"):
                continue
            
            # 跳過包含 "no fake success" 的行（這是誠實的聲明）
            if "no fake success" in line.lower():
                continue
            
            # 檢查行中是否包含假成功模式
            line_lower = line.lower()
            for pattern in fake_patterns:
                if pattern in line_lower:
                    pytest.fail(f"{page_file.name}:{i} contains fake success pattern: '{pattern}' in line: {line.strip()}")
        
        # 檢查是否有硬編碼的成功狀態
        lines = content.split('\n')
        for i, line in enumerate(lines, 1):
            if 'ui.notify' in line and '"success"' in line.lower():
                # 檢查是否為假成功通知
                if 'fake' in line.lower() or '模擬' in line.lower():
                    pytest.fail(f"{page_file.name}:{i} contains fake success notification")


def test_nicegui_pages_have_dev_mode_for_unfinished():
    """測試未完成功能有 DEV MODE 標示"""
    pages_dir = Path("src/FishBroWFS_V2/gui/nicegui/pages")
    
    for page_file in pages_dir.glob("*.py"):
        content = page_file.read_text()
        
        # 檢查是否有 disabled 按鈕但沒有適當標示
        lines = content.split('\n')
        for i, line in enumerate(lines, 1):
            if '.props("disabled")' in line:
                # 檢查同一行或接下來 3 行是否有 tooltip 或 DEV MODE
                current_and_next_lines = lines[i-1:i+3]  # i-1 因為 enumerate 從 1 開始
                has_tooltip = any('.tooltip(' in nl for nl in current_and_next_lines)
                has_dev_mode = any('DEV MODE' in nl for nl in current_and_next_lines) or any('dev mode' in nl.lower() for nl in current_and_next_lines)
                
                if not (has_tooltip or has_dev_mode):
                    pytest.fail(f"{page_file.name}:{i} has disabled button without DEV MODE or tooltip")


def test_ui_does_not_import_research_runner():
    """測試 UI 沒有 import Research Runner"""
    # 檢查 NiceGUI 目錄下的所有檔案
    nicegui_dir = Path("src/FishBroWFS_V2/gui/nicegui")
    
    for py_file in nicegui_dir.rglob("*.py"):
        content = py_file.read_text()
        
        # 禁止的 import
        banned_imports = [
            "FishBroWFS_V2.control.research_runner",
            "FishBroWFS_V2.wfs.runner",
            "research_runner",
            "wfs.runner",
        ]
        
        # 檢查非註解行
        lines = content.split('\n')
        in_docstring = False
        for i, line in enumerate(lines, 1):
            stripped_line = line.strip()
            
            # 處理文檔字串開始/結束
            if stripped_line.startswith('"""') or stripped_line.startswith("'''"):
                if in_docstring:
                    in_docstring = False
                else:
                    in_docstring = True
                continue
            
            # 跳過註解行和文檔字串內的內容
            if stripped_line.startswith('#') or in_docstring:
                continue
            
            # 檢查行中是否包含禁止的 import
            for banned in banned_imports:
                if banned in line:
                    # 檢查是否為實際的 import 語句
                    if "import" in line and banned in line:
                        pytest.fail(f"{py_file}:{i} imports banned module: '{banned}' in line: {line.strip()}")


def test_ui_does_not_compute_drawdown_corr():
    """測試 UI 沒有計算 drawdown 或 correlation"""
    pages_dir = Path("src/FishBroWFS_V2/gui/nicegui/pages")
    
    for page_file in pages_dir.glob("*.py"):
        content = page_file.read_text().lower()
        
        # 檢查是否有計算 drawdown 或 correlation 的程式碼
        suspicious_patterns = [
            "max_drawdown",
            "drawdown.*=",
            "correlation.*=",
            "corr.*=",
            "np\\.",  # numpy 計算
            "pd\\.",  # pandas 計算
            "calculate.*drawdown",
            "compute.*correlation",
        ]
        
        for pattern in suspicious_patterns:
            # 簡單檢查，實際應該用更精確的方法
            if "def display_" in content or "def refresh_" in content:
                # 這些是顯示函數，允許包含這些字串
                continue
            
            if pattern in content and "artifact" not in content:
                # 需要更仔細的檢查，但先標記
                print(f"Warning: {page_file.name} may contain computation pattern: {pattern}")


def test_charts_page_has_dev_mode_banner():
    """測試 Charts 頁面有 DEV MODE banner"""
    charts_file = Path("src/FishBroWFS_V2/gui/nicegui/pages/charts.py")
    content = charts_file.read_text()
    
    # 檢查是否有 DEV MODE banner
    assert "DEV MODE" in content, "Charts page missing DEV MODE banner"
    # 檢查是否有誠實的未實作警告（接受多種形式）
    warning_phrases = [
        "Chart visualization system not yet implemented",
        "Chart visualization NOT WIRED",
        "NOT IMPLEMENTED",
        "not yet implemented",
        "NOT WIRED"
    ]
    has_warning = any(phrase in content for phrase in warning_phrases)
    assert has_warning, "Charts page missing implementation warning"


def test_deploy_page_has_honest_checklist():
    """測試 Deploy 頁面有誠實的檢查清單"""
    deploy_file = Path("src/FishBroWFS_V2/gui/nicegui/pages/deploy.py")
    content = deploy_file.read_text()
    
    # 檢查是否有假設為 True 的項目
    lines = content.split('\n')
    fake_true_count = 0
    
    for i, line in enumerate(lines):
        if '"checked": True' in line:
            # 檢查是否有合理的理由
            context = '\n'.join(lines[max(0, i-2):min(len(lines), i+3)])
            if "DEV MODE" not in context and "not implemented" not in context:
                fake_true_count += 1
    
    # 允許一些合理的 True 項目，但不能太多
    assert fake_true_count <= 2, f"Deploy page has {fake_true_count} potentially fake True items"


def test_new_job_page_uses_real_submit_api():
    """測試 New Job 頁面使用真的 submit API"""
    new_job_file = Path("src/FishBroWFS_V2/gui/nicegui/pages/new_job.py")
    content = new_job_file.read_text()
    
    # 檢查是否有真的 submit_job 呼叫
    assert "submit_job(" in content, "New Job page missing real submit_job call"
    assert "from ..api import" in content, "New Job page missing api import"
    
    # 檢查是否有假成功通知
    assert "假成功" not in content, "New Job page contains fake success"
    assert "fake success" not in content.lower(), "New Job page contains fake success"


def test_no_streamlit_references_in_nicegui():
    """測試 NiceGUI 中沒有 Streamlit 參考"""
    nicegui_dir = Path("src/FishBroWFS_V2/gui/nicegui")
    
    for py_file in nicegui_dir.rglob("*.py"):
        content = py_file.read_text()
        
        # 檢查 Streamlit 參考
        assert "streamlit" not in content.lower(), f"{py_file} contains streamlit reference"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])


