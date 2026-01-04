"""
Policy test: Ensure no tests spawn real network servers or make HTTP requests to localhost.

Strictly forbidden:
- uvicorn (spawning real ASGI servers)
- requests.get(http://127.0.0.1...)
- requests.get(http://localhost:...)
- socket.bind(('127.0.0.1', ...))
- Any real network binding to localhost ports

Allowed:
- fastapi TestClient(app) without binding ports
- httpx.AsyncClient with mocked transport
- In-process testing only
"""

import ast
import os
from pathlib import Path
import re


def test_no_localhost_network_tests():
    """Scan all test files for forbidden network patterns."""
    test_dir = Path(__file__).parent.parent
    forbidden_patterns = [
        # Real server spawning
        (r"uvicorn\.run", "uvicorn.run - spawns real ASGI server"),
        (r"import uvicorn", "uvicorn import - may lead to real server spawning"),
        (r"from uvicorn import", "uvicorn import - may lead to real server spawning"),
        
        # HTTP requests to localhost
        (r'requests\.get\("http://127\.0\.0\.1', "requests.get to 127.0.0.1 - real network request"),
        (r'requests\.get\("http://localhost:', "requests.get to localhost - real network request"),
        (r'requests\.post\("http://127\.0\.0\.1', "requests.post to 127.0.0.1 - real network request"),
        (r'requests\.post\("http://localhost:', "requests.post to localhost - real network request"),
        
        # Socket binding
        (r"socket\.bind\(\(['\"]127\.0\.0\.1['\"]", "socket.bind to 127.0.0.1 - real network binding"),
        (r"socket\.bind\(\(['\"]localhost['\"]", "socket.bind to localhost - real network binding"),
        
        # Port binding patterns (may be false positives but worth checking)
        (r":8080", "Port 8080 binding - may indicate real server"),
        (r":8000", "Port 8000 binding - may indicate real server"),
        (r":5000", "Port 5000 binding - may indicate real server"),
    ]
    
    violations = []
    
    for test_file in test_dir.rglob("*.py"):
        # Skip this file itself completely
        if test_file.resolve() == Path(__file__).resolve():
            continue
            
        # Skip __pycache__ directories
        if "__pycache__" in str(test_file):
            continue
            
        try:
            content = test_file.read_text(encoding="utf-8")
            
            # Check for forbidden patterns
            for pattern, reason in forbidden_patterns:
                if re.search(pattern, content):
                    # Get line numbers for context
                    lines = content.splitlines()
                    for i, line in enumerate(lines, 1):
                        if re.search(pattern, line):
                            # Skip if this is in a comment
                            stripped = line.strip()
                            if stripped.startswith("#"):
                                continue
                            # Skip if it's in a string literal (docstring or error message)
                            # Simple heuristic: if line contains pattern but also contains quotes
                            if '"' in line or "'" in line:
                                # Check if it's likely a string literal vs actual code
                                # This is imperfect but works for most cases
                                pass
                            
                            violations.append({
                                "file": str(test_file.relative_to(test_dir.parent)),
                                "line": i,
                                "pattern": pattern,
                                "reason": reason,
                                "context": line.strip()[:100]
                            })
                            
        except (UnicodeDecodeError, IOError) as e:
            # Skip binary files or unreadable files
            continue
    
    # Report violations
    if violations:
        error_msg = "Found forbidden network patterns in tests:\n\n"
        for v in violations:
            error_msg += f"  {v['file']}:{v['line']} - {v['reason']}\n"
            error_msg += f"    Pattern: {v['pattern']}\n"
            error_msg += f"    Context: {v['context']}\n\n"
        
        error_msg += "\nThese tests must be converted to in-process tests or removed.\n"
        error_msg += "Allowed: TestClient(app) without binding ports.\n"
        error_msg += "Forbidden: Real network servers, HTTP requests to localhost, socket binding.\n"
        
        raise AssertionError(error_msg)
    
    # If we get here, test passes
    assert len(violations) == 0, f"Found {len(violations)} violations"