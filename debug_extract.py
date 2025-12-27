#!/usr/bin/env python3
import re
import tempfile
import os
import subprocess
import sys
from pathlib import Path

def extract_code_block(section_content):
    match = re.search(r'```\w*\s*(.*?)\s*```', section_content, re.DOTALL)
    if match:
        return match.group(1)
    return ''

with tempfile.TemporaryDirectory() as tmpdir:
    out = Path(tmpdir) / 'outputs' / 'snapshots'
    out.mkdir(parents=True)
    env = os.environ.copy()
    env['FISHBRO_SNAPSHOT_OUTPUT_DIR'] = str(out)
    script = Path.cwd() / 'scripts' / 'no_fog' / 'generate_full_snapshot_v2.py'
    result = subprocess.run([sys.executable, str(script), '--force'], env=env, capture_output=True, text=True, cwd=Path.cwd())
    snapshot = out / 'SYSTEM_FULL_SNAPSHOT.md'
    content = snapshot.read_text()
    # Find section
    match = re.search(r'## AUDIT_ENTRYPOINTS.*?(?=## |\Z)', content, re.DOTALL)
    if match:
        section = match.group(0)
        print('Section length:', len(section))
        print('First 200 chars:', section[:200])
        code = extract_code_block(section)
        print('Extracted code length:', len(code))
        if code:
            print('First 200 chars of code:', code[:200])
        else:
            print('No code extracted')
        # Also try to find all triple backticks
        ticks = [m.start() for m in re.finditer(r'```', section)]
        print('Triple backticks positions:', ticks)
        # Print lines around each tick
        lines = section.splitlines()
        for pos in ticks:
            # approximate line number by counting characters
            pass
        # Let's just print the section with line numbers
        for i, line in enumerate(lines[:30]):
            print(f'{i}: {line}')
    else:
        print('Section not found')