#!/usr/bin/env python3
"""
Fix indentation for self.setProperty lines in strategy_report_widget.py.
"""
import sys
import re

def main():
    file_path = "src/gui/desktop/widgets/report_widgets/strategy_report_widget.py"
    with open(file_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    # Pattern: lines that start with self.setProperty (no leading spaces)
    # but we need to keep the indentation of the surrounding block.
    # We'll assume each line should be indented by 8 spaces (two levels) relative to the method start.
    # However, we can't just add 8 spaces because the line may be inside a deeper block.
    # Let's instead look for lines that start with 'self.setProperty' and have zero or one space before?
    # Actually the file uses 8 spaces for indentation inside methods (two tabs?).
    # Let's examine the structure: The method definition is at column 4 (one tab?), but the file uses spaces.
    # Let's compute the indentation of the line before each self.setProperty.
    
    new_lines = []
    i = 0
    while i < len(lines):
        line = lines[i]
        # If line starts with self.setProperty and previous line is not empty and has indentation
        if line.lstrip().startswith('self.setProperty'):
            # Find the indentation of the previous non-empty line that is not a comment
            j = i - 1
            while j >= 0 and (lines[j].strip() == '' or lines[j].strip().startswith('#')):
                j -= 1
            if j >= 0:
                # Determine indentation of that line
                prev_line = lines[j]
                # Count leading spaces
                prev_indent = len(prev_line) - len(prev_line.lstrip())
                # If the previous line is a comment? We'll assume same indent.
                # But we need to see if the previous line is at the same block level.
                # Let's just add 8 spaces? Actually the surrounding lines have 8 spaces.
                # Let's look at the line after self.setProperty (the next line) which is indented by 8 spaces.
                # We'll match that.
                # Find next non-empty line after i that is not self.setProperty
                k = i + 1
                while k < len(lines) and lines[k].strip() == '':
                    k += 1
                if k < len(lines):
                    next_indent = len(lines[k]) - len(lines[k].lstrip())
                    # Use that indent
                    new_line = ' ' * next_indent + line.lstrip()
                else:
                    # fallback
                    new_line = ' ' * (prev_indent + 8) + line.lstrip()
            else:
                # fallback
                new_line = ' ' * 8 + line.lstrip()
            new_lines.append(new_line)
        else:
            new_lines.append(line)
        i += 1
    
    # Write back
    with open(file_path, 'w', encoding='utf-8') as f:
        f.writelines(new_lines)
    print(f"Fixed {file_path}")

if __name__ == '__main__':
    main()