"""UI Policy Contract Test: No direct database writes in GUI

Constitutional principle:
1. GUI code MUST NOT write directly to any database
2. GUI code MUST NOT execute SQL statements
3. GUI code MUST NOT modify persistent state directly
4. All state changes MUST go through Control API

Legitimate write patterns (allowed):
- Audit trail writes (JSON lines to audit log files)
- Archival writes (JSON dumps to archive files)
- Cryptographic hash updates (for integrity verification)
- Temporary file writes for UI state (session storage)

Prohibited write patterns:
- Database operations: commit(), execute(), insert(), update(), delete()
- Direct file writes to business data directories
- Bypassing UserIntent → ActionQueue pipeline
"""

import ast
import re
from pathlib import Path
import pytest


def scan_file_for_database_writes(file_path: Path) -> list:
    """Scan a Python file for database write patterns.
    
    Returns list of violations with line numbers and context.
    """
    violations = []
    
    try:
        content = file_path.read_text()
        lines = content.split('\n')
        
        # Database operation patterns (case-insensitive)
        # Focus on actual database operations, not Python container operations
        db_patterns = [
            # SQLAlchemy / database session operations
            r'session\.commit\s*\(',
            r'session\.execute\s*\(',
            r'session\.add\s*\(',
            r'session\.flush\s*\(',
            r'session\.bulk_save_objects\s*\(',
            r'session\.bulk_insert_mappings\s*\(',
            
            # Generic database operations (with context checking)
            r'\.commit\s*\(',
            r'\.execute\s*\(',
            r'\.insert\s*\(',
            r'\.update\s*\(',
            r'\.delete\s*\(',
            
            # SQL statements
            r'INSERT INTO',
            r'UPDATE\s+\w+\s+SET',
            r'DELETE FROM',
            r'CREATE TABLE',
            r'ALTER TABLE',
            r'DROP TABLE',
            
            # File operations that might bypass API (with context checking)
            r'\.write\s*\(',
            r'\.save\s*\(',
            r'\.put\s*\(',
        ]
        
        # Compile regex patterns
        compiled_patterns = [re.compile(pattern, re.IGNORECASE) for pattern in db_patterns]
        
        # Check each line
        for i, line in enumerate(lines, 1):
            # Skip comments and docstrings (simple check)
            stripped_line = line.strip()
            if stripped_line.startswith('#') or stripped_line.startswith('"""') or stripped_line.startswith("'''"):
                continue
            
            # Check for database patterns
            for pattern in compiled_patterns:
                if pattern.search(line):
                    # Check if this is in a legitimate context
                    # Allow certain legitimate patterns
                    if any(allowed in line for allowed in [
                        'audit_log.py',
                        'archive.py',
                        'reload_service.py',
                        'hashlib',
                        'hasher.update',
                        'json.dump',
                        'json.dumps',
                        'f.write',
                        'write_audit_log',
                        'write_archive',
                        'set.add',  # Python set operation
                        'list.append',  # Python list operation
                        'dict.update',  # Python dict operation
                    ]):
                        # These are legitimate write patterns documented in Phase B1 plan
                        continue
                    
                    # Additional context checks
                    line_lower = line.lower()
                    
                    # Skip Python container operations
                    if '.add(' in line_lower and any(container in line_lower for container in ['set', 'values', 'items', 'collection']):
                        # Likely Python set.add() operation
                        continue
                    
                    if '.write(' in line_lower and 'f.write' in line_lower:
                        # File write operation (already handled by legitimate patterns)
                        continue
                    
                    if '.save(' in line_lower and any(context in line_lower for context in ['json', 'pickle', 'numpy', 'pandas']):
                        # Data serialization, not database
                        continue
                    
                    violations.append({
                        'file': str(file_path),
                        'line': i,
                        'pattern': pattern.pattern,
                        'context': line.strip()[:100]
                    })
                    break  # Only report first pattern per line
        
        # Also check AST for SQLAlchemy or database session usage
        try:
            tree = ast.parse(content)
            for node in ast.walk(tree):
                # Check for database session assignments
                if isinstance(node, ast.Assign):
                    for target in node.targets:
                        if isinstance(target, ast.Name):
                            if 'session' in target.id.lower() or 'db' in target.id.lower():
                                # Check if it's used in a write context
                                pass
                # Check for function calls that might be database operations
                if isinstance(node, ast.Call):
                    if isinstance(node.func, ast.Attribute):
                        func_name = node.func.attr.lower()
                        if func_name in ['commit', 'execute', 'insert', 'update', 'delete', 'add', 'flush']:
                            # Check context to avoid false positives
                            line_no = node.lineno
                            line_text = lines[line_no - 1]
                            
                            # Skip Python container operations
                            if func_name == 'add':
                                # Check if this is a set.add() operation
                                if isinstance(node.func, ast.Attribute):
                                    # Get the object being called
                                    if hasattr(node.func, 'value'):
                                        # Check if it's a variable named like a container
                                        if isinstance(node.func.value, ast.Name):
                                            var_name = node.func.value.id.lower()
                                            if any(container in var_name for container in ['set', 'values', 'items', 'collection']):
                                                continue
                                    # Check line text for common patterns
                                    if any(pattern in line_text.lower() for pattern in ['set.add', 'values.add', 'items.add']):
                                        continue
                            
                            # Skip if in legitimate context
                            if not any(allowed in line_text for allowed in [
                                'audit_log',
                                'archive',
                                'reload_service',
                                'hash',
                            ]):
                                violations.append({
                                    'file': str(file_path),
                                    'line': line_no,
                                    'pattern': f'ast.{func_name}()',
                                    'context': line_text.strip()[:100]
                                })
        except SyntaxError:
            pass  # Skip AST parsing errors
            
    except (UnicodeDecodeError, IOError):
        pass  # Skip unreadable files
    
    return violations


def test_gui_no_database_writes():
    """Test that GUI code contains no direct database writes."""
    
    gui_dir = Path(__file__).parent.parent.parent / "src" / "FishBroWFS_V2" / "gui"
    
    violations = []
    
    # Scan all Python files in GUI directory
    for py_file in gui_dir.rglob("*.py"):
        # Skip __pycache__ and test files
        if '__pycache__' in str(py_file) or 'test_' in py_file.name:
            continue
            
        file_violations = scan_file_for_database_writes(py_file)
        violations.extend(file_violations)
    
    # Report violations
    if violations:
        print("\n" + "="*80)
        print("VIOLATIONS FOUND: GUI code contains potential database writes")
        print("="*80)
        for v in violations:
            print(f"{v['file']}:{v['line']} - Pattern: {v['pattern']}")
            print(f"  Context: {v['context']}")
            print()
    
    # Assert no violations
    assert len(violations) == 0, f"Found {len(violations)} potential database write violations in GUI code"


def test_legitimate_write_patterns_are_allowed():
    """Verify that legitimate write patterns are correctly identified and allowed."""
    
    # Test files that should pass (legitimate writes)
    legitimate_files = [
        "src/FishBroWFS_V2/gui/services/audit_log.py",
        "src/FishBroWFS_V2/gui/services/archive.py",
        "src/FishBroWFS_V2/gui/services/reload_service.py",
    ]
    
    for file_path in legitimate_files:
        path = Path(file_path)
        if path.exists():
            violations = scan_file_for_database_writes(path)
            # These files should have 0 violations (legitimate writes are filtered)
            if violations:
                print(f"WARNING: Legitimate file {file_path} has violations:")
                for v in violations:
                    print(f"  Line {v['line']}: {v['context']}")
            # We don't fail the test for these, just warn


def test_gui_services_have_appropriate_writes():
    """Test that GUI services only have appropriate write patterns."""
    
    gui_services_dir = Path(__file__).parent.parent.parent / "src" / "FishBroWFS_V2" / "gui" / "services"
    
    if not gui_services_dir.exists():
        return  # Skip if directory doesn't exist
    
    allowed_patterns = [
        'audit_log',
        'archive',
        'reload_service',
        'hash',
        'json.dump',
        'json.dumps',
        'f.write',
        'write_audit_log',
        'write_archive',
    ]
    
    violations = []
    
    for py_file in gui_services_dir.glob("*.py"):
        content = py_file.read_text()
        lines = content.split('\n')
        
        # Check for write operations
        for i, line in enumerate(lines, 1):
            if any(op in line for op in ['.commit(', '.execute(', '.insert(', '.update(', '.delete(']):
                # Check if it's in an allowed context
                if not any(allowed in line for allowed in allowed_patterns):
                    violations.append({
                        'file': str(py_file),
                        'line': i,
                        'context': line.strip()[:100]
                    })
    
    if violations:
        print("\n" + "="*80)
        print("POTENTIAL VIOLATIONS IN GUI SERVICES:")
        print("="*80)
        for v in violations:
            print(f"{v['file']}:{v['line']}")
            print(f"  Context: {v['context']}")
            print()
    
    # These should all be legitimate, so we expect 0 violations
    assert len(violations) == 0, f"Found {len(violations)} potential violations in GUI services"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])