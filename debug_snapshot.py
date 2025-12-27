#!/usr/bin/env python3
import tempfile, os, subprocess, sys
from pathlib import Path
import re

with tempfile.TemporaryDirectory() as tmpdir:
    out = Path(tmpdir) / 'outputs' / 'snapshots'
    out.mkdir(parents=True)
    env = os.environ.copy()
    env['FISHBRO_SNAPSHOT_OUTPUT_DIR'] = str(out)
    script = Path.cwd() / 'scripts' / 'no_fog' / 'generate_full_snapshot_v2.py'
    result = subprocess.run([sys.executable, str(script), '--force'], env=env, capture_output=True, text=True, cwd=Path.cwd())
    if result.returncode != 0:
        print('stderr:', result.stderr[:500])
        sys.exit(1)
    snapshot = out / 'SYSTEM_FULL_SNAPSHOT.md'
    if snapshot.exists():
        content = snapshot.read_text()
        # Find AUDIT_ENTRYPOINTS section
        match = re.search(r'## AUDIT_ENTRYPOINTS.*?(?=## |\Z)', content, re.DOTALL)
        if match:
            section = match.group(0)
            print('Section found, length:', len(section))
            print('First 500 chars:')
            print(section[:500])
            # Look for code block
            code = re.search(r'```md\s*(.*?)\s*```', section, re.DOTALL)
            if code:
                print('Code block found, length:', len(code.group(1)))
                print('First 200 chars of code:')
                print(code.group(1)[:200])
            else:
                print('No code block found')
                print('Section lines:')
                for i, line in enumerate(section.splitlines()[:20]):
                    print(f'{i}: {line}')
        else:
            print('Section not found')
    else:
        print('Snapshot not created')