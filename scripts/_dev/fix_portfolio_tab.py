#!/usr/bin/env python3
"""
Fix portfolio_admission_tab.py by replacing setProperty with regular attribute assignment.
"""

import re

def fix_file():
    filepath = "src/gui/desktop/tabs/portfolio_admission_tab.py"
    
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Pattern to match self.setProperty('attr', value)
    pattern = r'self\.setProperty\(\s*[\'"]([^\'"]+)[\'"]\s*,\s*([^)]+)\s*\)'
    
    def replace_match(match):
        attr = match.group(1)
        value = match.group(2)
        return f'self.{attr} = {value}'
    
    new_content = re.sub(pattern, replace_match, content)
    
    # Also fix lines with missing indentation for self.attr = value
    lines = new_content.split('\n')
    for i, line in enumerate(lines):
        if line.strip().startswith('self.') and '=' in line:
            # Check if line should be indented (inside setup_ui method)
            if i > 0 and 'def setup_ui' in lines[i-1]:
                # This line should be indented by 8 spaces
                if not line.startswith('        '):
                    lines[i] = '        ' + line.lstrip()
    
    new_content = '\n'.join(lines)
    
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(new_content)
    
    print(f"Fixed {filepath}")
    print("Changed setProperty calls to regular attribute assignment")

if __name__ == "__main__":
    fix_file()