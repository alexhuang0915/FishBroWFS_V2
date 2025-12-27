#!/usr/bin/env python3
"""
Remove lines containing FishBroWFS_V2 that are comments or strings.
"""
import os
import re
import sys

def clean_file(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    new_lines = []
    for line in lines:
        if 'FishBroWFS_V2' in line:
            # Check if line is a comment (starts with #) or a docstring (triple quotes) or a string?
            # We'll just remove if line.strip().startswith('#')
            stripped = line.lstrip()
            if stripped.startswith('#'):
                # skip this comment line
                continue
            # Also skip if line is part of a multiline comment? Not handling.
            # For safety, we keep the line.
        new_lines.append(line)
    if len(new_lines) != len(lines):
        print(f'Removed {len(lines) - len(new_lines)} lines from {filepath}')
        with open(filepath, 'w', encoding='utf-8') as f:
            f.writelines(new_lines)

def main():
    root = os.path.dirname(os.path.abspath(__file__))
    for dirpath, dirnames, filenames in os.walk(root):
        if '.git' in dirpath:
            continue
        for fname in filenames:
            if fname.endswith('.py'):
                filepath = os.path.join(dirpath, fname)
                clean_file(filepath)

if __name__ == '__main__':
    main()