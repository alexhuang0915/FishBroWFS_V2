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
    stack = []
    start_line = -1
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith('```'):
            if not stack:
                stack.append(stripped)
                start_line = i
            else:
                if stripped == stack[-1]:
                    stack.pop()
                    if not stack:
                        content_lines = lines[start_line + 1:i]
                        return ''.join(content_lines).rstrip('\n')
                else:
                    stack.append(stripped)
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
    print('First 500 chars:')
    print(section[:500])
    print('---')
    code = extract_code_block(section)
    print('Extracted code length:', len(code))
    if code:
        print('First 200 chars of code:', code[:200])
    else:
        print('No code extracted')
        # Debug stack
        lines = section.splitlines(keepends=True)
        for i, line in enumerate(lines):
            print(f'{i}: {line.rstrip()}')
            if line.strip().startswith('```'):
                print('   ^ backticks')
