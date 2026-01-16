# Root Hygiene Exceptions

## Purpose
This document records explicit exceptions to the root hygiene rules defined in `tests/control/test_root_hygiene_guard.py`. Root hygiene ensures the repository root contains only allowed project files and directories.

## Rule Summary
The root hygiene test (`test_root_hygiene_no_forbidden_files`) enforces:
1. **Allowed files**: Listed in `ROOT_TOPLEVEL_ALLOWLIST_V1.txt`
2. **Allowed directories**: Hardcoded set in the test
3. **Forbidden patterns**: Hardcoded regex patterns
4. **Ignore items**: Development artifacts that are completely ignored

## Explicit Exceptions

### `.roo/` Directory
- **Status**: Explicitly allowed
- **Reason**: Roo Code / agent configuration state directory
- **Justification**: Contains AI agent configuration, rules, and state files that must remain in repo root for tooling compatibility
- **Governance**: Must not contain user data or large files; subject to `.rooignore` rules

### `.qdrant_storage/` Directory  
- **Status**: Explicitly allowed
- **Reason**: Local vector database storage (path-sensitive)
- **Justification**: Qdrant vector database requires fixed location; cannot be moved to `outputs/` due to path dependencies
- **Governance**: Should be git-ignored; contains binary data not suitable for version control

## Prohibited Patterns
- **NO** wildcard allowance for dot-prefixed directories (e.g., `.*/`)
- **NO** blanket exceptions for "all tool directories"
- **NO** exceptions without documented justification in this file

## Maintenance
1. When adding new root directory exceptions:
   - Add to `allowed_dirs` set in `tests/control/test_root_hygiene_guard.py`
   - Add entry to this document with justification
   - Ensure directory is git-ignored if appropriate
2. Review exceptions quarterly during hygiene audit
3. Remove exceptions if directory becomes obsolete

## Related Files
- `docs/contracts/ROOT_TOPLEVEL_ALLOWLIST_V1.txt` - Allowed root files
- `tests/control/test_root_hygiene_guard.py` - Enforcement test
- `.gitignore` - Git exclusion patterns

## Version History
- **2026-01-16**: Created with exceptions for `.roo/` and `.qdrant_storage/`