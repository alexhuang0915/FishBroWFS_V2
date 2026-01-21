# HY2: Root Hygiene Exceptions Discovery

**Timestamp**: 2026-01-16T17:17:12Z  
**Task**: Allow explicit root dirs (.roo, .qdrant_storage) without wildcard

## SSOT Locations Confirmed

### 1. Allowed Directories SSOT
**Location**: `tests/control/test_root_hygiene_guard.py` lines 29-41 (hardcoded set)

**Original Contents**:
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

**Missing**: `.roo` and `.qdrant_storage`

### 2. Allowed Files SSOT
**Location**: `docs/contracts/ROOT_TOPLEVEL_ALLOWLIST_V1.txt`
- Confirmed to be for root files only (not directories)
- Already includes `.rooignore` file

### 3. Test Failure Confirmation
Ran test before changes:
```
FAILED tests/control/test_root_hygiene_guard.py::test_root_hygiene_no_forbidden_files
Failed: Root hygiene violations (2):
Unexpected directory: .qdrant_storage
Unexpected directory: .roo
```

## Current Root Directory State
From `git status --porcelain`:
```
?? .qdrant_storage/
?? .roo/
```

Both directories exist but are untracked (good).

## Git Ignore Status
Checked `.gitignore` - entries for `.roo/` and `.qdrant_storage/` were missing (added during implementation).

## No Wildcard Patterns Found
Searched codebase for wildcard dot-directory patterns:
- No `".*"` patterns in `allowed_dirs`
- No regex patterns matching all dot directories
- Governance intact: explicit exceptions only

## Summary
SSOT confirmed as hardcoded set in test file. Minimal change required: add `.roo` and `.qdrant_storage` to `allowed_dirs` with explanatory comments.