#!/usr/bin/env python3
"""
Replace FishBroWFS_V2 module prefixes and path references after flattening.
"""
import os
import re
import sys
from pathlib import Path

def replace_in_file(filepath: Path):
    """Apply replacements to a single file."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
    except (UnicodeDecodeError, OSError):
        # skip binary files
        return False
    
    # Replacement patterns
    # 1.  -> empty (for imports)
    #    but careful not to break strings like ""? That's fine.
    #    Use regex that matches whole word? We'll just replace literal substring.
    #    However we need to ensure we don't replace inside a longer identifier.
    #    We'll use regex with word boundary.
    #    pattern1 = r'\bFishBroWFS_V2\.'
    # 2. src/ -> src/
    #    pattern2 = r'src/'
    # 3. "FishBroWFS_V2" as a standalone word in strings? We'll leave as is.
    
    original = content
    
    # pattern 1:  with dot
    # Use lookahead to ensure dot is removed (so we keep the dot after removal?)
    # Actually we want to remove '' entirely, leaving the next token.
    # So we replace '' with ''.
    # Use regex that matches '' not preceded by alnum and not part of a longer word.
    # Simpler: replace '' globally.
    content = re.sub(r'FishBroWFS_V2\.', '', content)
    
    # pattern 2: src/ -> src/
    content = re.sub(r'src/', 'src/', content)
    
    # pattern 3: src\ (Windows style) -> src\\
    content = re.sub(r'src\\\\FishBroWFS_V2\\\\', 'src\\\\', content)
    
    if content == original:
        return False
    
    # Write back
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)
    return True

def main():
    root = Path.cwd()
    exclude_dirs = {'.venv', '.git', '__pycache__', 'node_modules', 'build', 'dist'}
    
    changed = 0
    for dirpath, dirnames, filenames in os.walk(root):
        # prune excluded directories
        dirnames[:] = [d for d in dirnames if d not in exclude_dirs]
        
        for filename in filenames:
            if filename.endswith('.py'):
                filepath = Path(dirpath) / filename
                if replace_in_file(filepath):
                    changed += 1
                    print(f'Updated {filepath.relative_to(root)}')
    
    print(f'Total files changed: {changed}')
    return 0

if __name__ == '__main__':
    sys.exit(main())