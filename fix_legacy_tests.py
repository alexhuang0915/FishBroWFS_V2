#!/usr/bin/env python3
"""修復 legacy tests 的 collection-time skip 問題"""

import os
import re
from pathlib import Path

def fix_test_file(filepath: Path) -> bool:
    """修復單個測試檔案"""
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 檢查是否有 module-level skip
    if 'pytest.skip("integration test requires FISHBRO_RUN_INTEGRATION=1", allow_module_level=True)' in content:
        print(f"修復 {filepath}")
        
        # 移除 module-level skip
        lines = content.split('\n')
        new_lines = []
        skip_removed = False
        
        for line in lines:
            if 'pytest.skip("integration test requires FISHBRO_RUN_INTEGRATION=1", allow_module_level=True)' in line:
                skip_removed = True
                continue
            new_lines.append(line)
        
        if not skip_removed:
            print(f"  警告: 未找到 module-level skip")
            return False
        
        # 重新組合內容
        content = '\n'.join(new_lines)
        
        # 為每個測試函數添加 skip 檢查
        lines = content.split('\n')
        new_lines = []
        in_function = False
        current_function_lines = []
        
        for i, line in enumerate(lines):
            if line.strip().startswith('def test_'):
                # 處理上一個函數
                if in_function and current_function_lines:
                    # 在函數開頭添加 skip 檢查
                    func_content = '\n'.join(current_function_lines)
                    # 檢查是否已經有 skip 檢查
                    if 'if os.getenv("FISHBRO_RUN_INTEGRATION") != "1":' not in func_content:
                        # 找到函數體開始的位置
                        for j, func_line in enumerate(current_function_lines):
                            if func_line.strip().startswith('"""') or func_line.strip().startswith("'''"):
                                # 跳過 docstring
                                continue
                            if func_line.strip() and not func_line.strip().startswith('#'):
                                # 插入 skip 檢查
                                indent = len(func_line) - len(func_line.lstrip())
                                skip_lines = [
                                    ' ' * indent + 'if os.getenv("FISHBRO_RUN_INTEGRATION") != "1":',
                                    ' ' * indent + '    pytest.skip("integration test requires FISHBRO_RUN_INTEGRATION=1")',
                                    ' ' * indent + ''
                                ]
                                current_function_lines = (current_function_lines[:j] + 
                                                         skip_lines + 
                                                         current_function_lines[j:])
                                break
                
                # 開始新函數
                in_function = True
                current_function_lines = [line]
                new_lines.extend(current_function_lines)
                current_function_lines = []
            elif in_function:
                current_function_lines.append(line)
            else:
                new_lines.append(line)
        
        # 處理最後一個函數
        if in_function and current_function_lines:
            func_content = '\n'.join(current_function_lines)
            if 'if os.getenv("FISHBRO_RUN_INTEGRATION") != "1":' not in func_content:
                # 找到函數體開始的位置
                for j, func_line in enumerate(current_function_lines):
                    if func_line.strip().startswith('"""') or func_line.strip().startswith("'''"):
                        continue
                    if func_line.strip() and not func_line.strip().startswith('#'):
                        indent = len(func_line) - len(func_line.lstrip())
                        skip_lines = [
                            ' ' * indent + 'if os.getenv("FISHBRO_RUN_INTEGRATION") != "1":',
                            ' ' * indent + '    pytest.skip("integration test requires FISHBRO_RUN_INTEGRATION=1")',
                            ' ' * indent + ''
                        ]
                        current_function_lines = (current_function_lines[:j] + 
                                                 skip_lines + 
                                                 current_function_lines[j:])
                        break
            new_lines.extend(current_function_lines)
        
        content = '\n'.join(new_lines)
        
        # 寫回檔案
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        
        return True
    
    return False

def main():
    """主函數"""
    legacy_dir = Path(__file__).parent / "tests" / "legacy"
    
    if not legacy_dir.exists():
        print(f"錯誤: 目錄不存在 {legacy_dir}")
        return
    
    test_files = list(legacy_dir.glob("test_*.py"))
    print(f"找到 {len(test_files)} 個測試檔案")
    
    fixed_count = 0
    for test_file in test_files:
        if fix_test_file(test_file):
            fixed_count += 1
    
    print(f"修復了 {fixed_count} 個檔案")

if __name__ == "__main__":
    main()