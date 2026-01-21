# Root Hygiene Allowlist SSOT Discovery

**Discovery Date**: 2026-01-16T17:13:43Z  
**Target Directories**: `.roo/` and `.qdrant_storage/`  
**Discovery Method**: Codebase search and file analysis

## 1. SSOT Locations Identified

### 1.1 Allowed Root Files (Non-directories)
**SSOT File**: `docs/contracts/ROOT_TOPLEVEL_ALLOWLIST_V1.txt`

**Current Contents**:
```
# Version: V1
# Allowlist for repo root files (non-directories)
README.md
main.py
Makefile
pyproject.toml
pytest.ini
requirements.txt
SNAPSHOT_CLEAN.jsonl
.gitattributes
.gitignore
.cursorignore
.pre-commit-config.yaml
FishBroWFS_UI.bat
.rooignore
pyrightconfig.json
```

**Data Structure**: Simple line-based list, one entry per line
**Matching Method**: Exact filename match (case-sensitive)
**Usage**: Read by `tests/control/test_root_hygiene_guard.py` lines 23-27

### 1.2 Allowed Root Directories
**SSOT Location**: Hardcoded in `tests/control/test_root_hygiene_guard.py` lines 29-41

**Current Contents**:
```python
allowed_dirs = {
    'src',
    'tests',
    'docs',
    'plans',
    'scripts',
    'outputs',
    'configs',
    '.continue',
    '.github',
    '.vscode',
    'FishBroData',  # Data directory for the project
}
```

**Data Structure**: Python set literal
**Matching Method**: Exact directory name match (case-sensitive)
**Note**: `.roo` and `.qdrant_storage` are NOT in this set

### 1.3 Forbidden Patterns
**SSOT Location**: Hardcoded in `tests/control/test_root_hygiene_guard.py` lines 44-54

**Current Contents**:
```python
forbidden_patterns = [
    r'^tmp_.*\.py$',
    r'.*_verification.*\.py$',
    r'.*_report.*\.md$',
    r'^AS_IS_.*\.md$',
    r'^GAP_LIST\.md$',
    r'^S2S3_CONTRACT\.md$',
    r'.*\.zip$',
    r'.*\.tar\.gz$',
    r'.*\.save$',  # Backup files like .gitattributes.save
]
```

**Matching Method**: Regular expression matching against filenames

### 1.4 Ignore Items
**SSOT Location**: Hardcoded in `tests/control/test_root_hygiene_guard.py` lines 57-65

**Current Contents**:
```python
ignore_items = {
    '.git',
    '.venv',
    '__pycache__',
    '.pytest_cache',
    '.mypy_cache',
    '.pytest_cache',
    'examples',
}
```

**Purpose**: These items are completely ignored (not checked)

## 2. Current Root Directory State

From `list_files` output:
```
.cursorignore
.gitattributes
.gitignore
.pre-commit-config.yaml
.rooignore
Makefile
pyproject.toml
pyrightconfig.json
pytest.ini
requirements.txt
.github/
.qdrant_storage/
.roo/
.vscode/
configs/
docs/
outputs/
plans/
scripts/
src/
tests/
```

**Key Observations**:
1. `.roo/` directory exists but is NOT in `allowed_dirs`
2. `.qdrant_storage/` directory exists but is NOT in `allowed_dirs`
3. `.continue/` is in `allowed_dirs` but does NOT exist in root
4. `FishBroData/` is in `allowed_dirs` but does NOT exist in root

## 3. Test Logic Analysis

The test `test_root_hygiene_no_forbidden_files()` performs:

1. Reads allowed files from external SSOT (`ROOT_TOPLEVEL_ALLOWLIST_V1.txt`)
2. Uses hardcoded `allowed_dirs` set for directory validation
3. Iterates through `os.listdir(root)`, skipping `ignore_items`
4. For each item:
   - If directory: checks if in `allowed_dirs`
   - If file: checks if in `allowed_files` OR matches `forbidden_patterns`
5. Records violations and fails test if any violations found

## 4. Minimal Changes Required

To allow `.roo/` and `.qdrant_storage/` directories:

### Option A: Modify Hardcoded SSOT (Recommended)
Add entries to the `allowed_dirs` set in `tests/control/test_root_hygiene_guard.py`:

```python
allowed_dirs = {
    'src',
    'tests',
    'docs',
    'plans',
    'scripts',
    'outputs',
    'configs',
    '.continue',
    '.github',
    '.vscode',
    'FishBroData',  # Data directory for the project
    '.roo',         # AI configuration and rules directory
    '.qdrant_storage',  # Vector database storage
}
```

**Change Impact**: 
- Single file modification
- No configuration files to update
- Test will pass after change

### Option B: Create External SSOT for Directories
Create a new SSOT file (e.g., `docs/contracts/ROOT_DIR_ALLOWLIST_V1.txt`) and modify test to read from it.

**Pros**: Consistent with files SSOT pattern
**Cons**: More complex, requires test logic changes

## 5. Recommendations

1. **Preferred Approach**: Use Option A (modify hardcoded set) because:
   - The directory list is relatively stable
   - No other tests or code reference this list
   - Simpler change with minimal risk

2. **Considerations**:
   - `.continue/` and `FishBroData/` remain in allowlist but don't exist (acceptable)
   - Ensure `.rooignore` file is already in files allowlist (it is)

3. **Verification**:
   - Run `pytest tests/control/test_root_hygiene_guard.py -v` after change
   - Should pass with no violations

## 6. Evidence Files

- `tests/control/test_root_hygiene_guard.py` - Full test source
- `docs/contracts/ROOT_TOPLEVEL_ALLOWLIST_V1.txt` - Files allowlist
- Root directory listing (above)

## 7. Summary

**SSOT Locations**:
1. Files: `docs/contracts/ROOT_TOPLEVEL_ALLOWLIST_V1.txt` (external)
2. Directories: `tests/control/test_root_hygiene_guard.py` lines 29-41 (hardcoded)
3. Patterns: Same test file lines 44-54 (hardcoded)
4. Ignore items: Same test file lines 57-65 (hardcoded)

**Minimal Change**: Add `.roo` and `.qdrant_storage` to the `allowed_dirs` set in `tests/control/test_root_hygiene_guard.py`.