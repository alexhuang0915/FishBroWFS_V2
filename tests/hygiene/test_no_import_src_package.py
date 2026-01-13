"""
Hygiene test to ensure no illegal '' imports exist in the codebase.

Contract:
- Parse every `src/**/*.py` file as plain text (no imports).
- Fail if pattern matches:
  - `^(from|import)\s+src\.`

Implementation requirements:
- Deterministic file iteration order (`sorted(Path(...).rglob(...))`)
- Fail message lists offending files (and ideally line snippets if easy).
- No DeprecationWarnings, no AST needed, pure regex is sufficient.
- Must not rely on OS-specific path behavior.
"""

import re
from pathlib import Path


def test_no_import_src_package():
    """Fail if any Python file in src/ contains 'from ' or 'import src.'"""
    src_dir = Path("src")
    if not src_dir.exists():
        return  # If src/ doesn't exist, nothing to check
    
    # Pattern to match illegal imports
    # Matches 'from ' or 'import src.' at start of line (with optional whitespace)
    pattern = re.compile(r'^\s*(from|import)\s+src\.')
    
    violations = []
    
    # Deterministic iteration order
    for py_file in sorted(src_dir.rglob("*.py")):
        try:
            with open(py_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()
        except (IOError, UnicodeDecodeError):
            # Skip files we can't read
            continue
        
        for line_num, line in enumerate(lines, start=1):
            if pattern.match(line):
                # Capture the violating line (strip trailing newline)
                violations.append({
                    'file': py_file.relative_to(src_dir.parent),
                    'line': line_num,
                    'content': line.rstrip('\n')
                })
    
    if violations:
        # Build failure message
        msg_lines = [
            f"Found {len(violations)} illegal '' import(s):",
            "",
        ]
        
        for v in violations:
            msg_lines.append(
                f"  {v['file']}:{v['line']}: {v['content']}"
            )
        
        msg_lines.extend([
            "",
            "These imports violate the PYTHONPATH=src contract.",
            "Fix by removing the '' prefix:",
            "  - Change 'from X import Y' to 'from X import Y'",
            "  - Change 'import src.X' to 'import X'",
            "",
            "Run `rg -n \"^(from|import)\\\\s+src\\\\.\" src` to see all violations.",
        ])
        
        raise AssertionError("\n".join(msg_lines))