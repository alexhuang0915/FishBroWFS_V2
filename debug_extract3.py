#!/usr/bin/env python3
import tempfile, os, subprocess, sys
from pathlib import Path

def extract_section(content: str, section_header: str) -> str:
    lines = content.splitlines(keepends=True)
    in_code_block = False
    code_block_delimiter = None
    section_start = -1
    result_lines = []
    
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith('```'):
            if not in_code_block:
                in_code_block = True
                code_block_delimiter = stripped
            else:
                if stripped == code_block_delimiter:
                    in_code_block = False
                    code_block_delimiter = None
        if section_start == -1:
            if line.strip() == section_header:
                section_start = i
                result_lines.append(line)
        else:
            if not in_code_block and line.strip().startswith('## ') and line.strip() != section_header:
                break
            result_lines.append(line)
    
    if section_start == -1:
        return ""
    return ''.join(result_lines)

def extract_code_block(section_content: str) -> str:
    lines = section_content.splitlines(keepends=True)
    stack = []  # stores the number of backticks (3) for each nesting level
    start_line = -1
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith('```'):
            # Count leading backticks
            backticks = len(stripped) - len(stripped.lstrip('`'))
            if not stack:
                # Opening code block
                stack.append(backticks)
                start_line = i
            else:
                # Could be closing or nested opening
                if backticks == stack[-1]:
                    # Matching closing (same number of backticks)
                    stack.pop()
                    if not stack:
                        # Found the matching closing for the outermost block
                        # Collect content between start_line+1 and i-1
                        content_lines = lines[start_line + 1:i]
                        return ''.join(content_lines).rstrip('\n')
                else:
                    # Nested code block with different number of backticks (should not happen with triple backticks)
                    stack.append(backticks)
    # If we never found a closing, return empty
    return ""

with tempfile.TemporaryDirectory() as tmpdir:
    out = Path(tmpdir) / 'outputs' / 'snapshots'
    out.mkdir(parents=True)
    env = os.environ.copy()
    env['FISHBRO_SNAPSHOT_OUTPUT_DIR'] = str(out)
    script = Path.cwd() / 'scripts' / 'no_fog' / 'generate_full_snapshot_v2.py'
    result = subprocess.run([sys.executable, str(script), '--force'], env=env, capture_output=True, text=True, cwd=Path.cwd())
    snapshot = out / 'SYSTEM_FULL_SNAPSHOT.md'
    content = snapshot.read_text()
    section = extract_section(content, '## AUDIT_ENTRYPOINTS')
    print('Section length:', len(section))
    code = extract_code_block(section)
    print('Extracted code length:', len(code))
    if code:
        print('First 200 chars of code:', code[:200])
        # Check required sections
        required = ['## Git HEAD', '## Makefile Targets Extract', '## Detected Python Entrypoints', '## Notes / Risk Flags']
        for req in required:
            if req in code:
                print(f'✓ Found {req}')
            else:
                print(f'✗ Missing {req}')
    else:
        print('No code extracted')
        # Debug stack
        lines = section.splitlines(keepends=True)
        for i, line in enumerate(lines):
            if line.strip().startswith('```'):
                print(f'{i}: {line.rstrip()}')
