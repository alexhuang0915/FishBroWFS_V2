#!/usr/bin/env python3
"""
Replace  prefix in all Python files.
"""
import os
import re
import sys

def replace_in_file(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    # replace  with empty string
    new_content = re.sub(r'FishBroWFS_V2\.', '', content)
    # replace 'import' with 'import' (keep the rest)
    # Actually we want to keep 'import X' -> 'import X'? That's tricky.
    # Let's handle specific pattern: 'import' -> 'import'
    new_content = re.sub(r'import', 'import', new_content)
    # but we need to keep possible trailing comments. Simpler: we'll ignore for now.
    if new_content != content:
        print(f'Updated {filepath}')
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(new_content)

def main():
    root = os.path.dirname(os.path.abspath(__file__))
    for dirpath, dirnames, filenames in os.walk(root):
        # skip .git directories
        if '.git' in dirpath:
            continue
        for fname in filenames:
            if fname.endswith('.py'):
                filepath = os.path.join(dirpath, fname)
                replace_in_file(filepath)

if __name__ == '__main__':
    main()