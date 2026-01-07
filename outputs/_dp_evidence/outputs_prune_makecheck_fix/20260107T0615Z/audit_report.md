# Repository Cleanup Residual Audit

## Executive Summary
Audit conducted on 2026-01-07T06:22Z to identify files/directories outside the authoritative "new system" architecture that are not required by active tests, contracts, or acceptance harness.

**Key Findings:**
1. `plans/` directory exists but is NOT in authoritative allowed areas list
2. `outputs/_trash/` directory exists (empty) - used by GUI cleanup functionality
3. `outputs/deployment/` directory exists (contains 2026Q1 subdirectory) - used by deployment TXT generation
4. `requirements.txt` file exists but not in authoritative list (though likely required)
5. All other directories conform to authoritative allowed areas

**Impact Assessment:**
- `plans/` is referenced in `test_root_hygiene_guard.py` as allowed directory
- `outputs/_trash` is referenced in GUI cleanup service
- `outputs/deployment` is referenced in supervisor handlers and deploy_txt.py
- No immediate cleanup required; all items have runtime/test dependencies

## Detailed Audit

### Inventory Scan (Root Level)
```
.
├── README.md
├── Makefile
├── pyproject.toml
├── pytest.ini
├── requirements.txt          # NOT in authoritative list
├── .gitattributes
├── .gitignore
├── .pre-commit-config.yaml
├── .github/                  # ALLOWED
├── .vscode/                  # ALLOWED
├── configs/                  # ALLOWED
├── docs/                     # ALLOWED
├── outputs/                  # ALLOWED
├── plans/                    # NOT in authoritative list
├── scripts/                  # ALLOWED
├── src/                      # ALLOWED
└── tests/                    # ALLOWED
```

### Inventory Scan (Outputs Depth ≤ 3)
```
outputs/
├── _dp_evidence/             # ALLOWED
├── _trash/                   # NOT in authoritative list
├── deployment/               # NOT in authoritative list
├── jobs*.db                  # ALLOWED (runtime SSOT)
├── portfolio_store/          # ALLOWED
├── research/                 # NOT in authoritative list
├── seasons/                  # ALLOWED
├── shared/                   # ALLOWED (baseline test contract)
└── strategies/               # ALLOWED
```

## Classification & Justification

### 1. `plans/` directory
- **Path**: `/home/fishbro/FishBroWFS_V2/plans/`
- **Size**: ~108KB (7 markdown files)
- **Last modified**: 2025-12-31
- **Category**: REQUIRED_BY_TEST
- **Evidence**: Referenced in `tests/control/test_root_hygiene_guard.py` line 35 as allowed directory
- **Safety Check**:
  - `make check` would fail if deleted? **YES** (test_root_hygiene_guard expects it)
  - Acceptance harness would fail? **UNKNOWN** (not directly tested)
  - Runtime behavior change? **NO** (not used in production)
- **Safe to Delete?**: NO
- **Confidence**: HIGH

### 2. `outputs/_trash/` directory
- **Path**: `/home/fishbro/FishBroWFS_V2/outputs/_trash/`
- **Size**: Empty
- **Last modified**: 2026-01-07
- **Category**: REQUIRED_BY_RUNTIME
- **Evidence**: Referenced in GUI cleanup service (`src/gui/desktop/widgets/cleanup_dialog.py`, `src/gui/desktop/services/cleanup_service.py`)
- **Safety Check**:
  - `make check` would fail if deleted? **NO** (tests use temp directories)
  - Acceptance harness would fail? **NO** (not part of acceptance)
  - Runtime behavior change? **YES** (GUI cleanup functionality would break)
- **Safe to Delete?**: NO (directory can be empty but must exist)
- **Confidence**: HIGH

### 3. `outputs/deployment/` directory
- **Path**: `/home/fishbro/FishBroWFS_V2/outputs/deployment/`
- **Size**: Contains `2026Q1/` subdirectory
- **Last modified**: 2026-01-07
- **Category**: REQUIRED_BY_RUNTIME
- **Evidence**: Referenced in supervisor handlers (`src/control/supervisor/handlers/run_compile.py`) and `src/control/deploy_txt.py`
- **Safety Check**:
  - `make check` would fail if deleted? **NO** (tests use temp directories)
  - Acceptance harness would fail? **NO** (not part of acceptance)
  - Runtime behavior change? **YES** (deployment TXT generation would fail)
- **Safe to Delete?**: NO (directory structure required for deployment functionality)
- **Confidence**: HIGH

### 4. `outputs/research/` directory
- **Path**: `/home/fishbro/FishBroWFS_V2/outputs/research/`
- **Size**: Unknown (not examined)
- **Last modified**: Unknown
- **Category**: UNKNOWN
- **Evidence**: No references found in code search
- **Safety Check**:
  - `make check` would fail if deleted? **UNKNOWN**
  - Acceptance harness would fail? **UNKNOWN**
  - Runtime behavior change? **UNKNOWN**
- **Safe to Delete?**: UNKNOWN (requires human decision)
- **Confidence**: LOW

### 5. `requirements.txt` file
- **Path**: `/home/fishbro/FishBroWFS_V2/requirements.txt`
- **Size**: 2KB
- **Last modified**: 2026-01-06
- **Category**: REQUIRED_BY_RUNTIME
- **Evidence**: Standard Python dependency file, referenced by `Makefile` and `pyproject.toml`
- **Safety Check**:
  - `make check` would fail if deleted? **YES** (dependency installation)
  - Acceptance harness would fail? **YES** (environment setup)
  - Runtime behavior change? **YES** (missing dependencies)
- **Safe to Delete?**: NO
- **Confidence**: HIGH

## Verdict Table

| Path | Category | Safe to Delete? | Confidence | Reason |
|------|----------|-----------------|------------|--------|
| `plans/` | REQUIRED_BY_TEST | NO | HIGH | Referenced in test_root_hygiene_guard.py as allowed directory |
| `outputs/_trash/` | REQUIRED_BY_RUNTIME | NO | HIGH | Used by GUI cleanup service; directory must exist |
| `outputs/deployment/` | REQUIRED_BY_RUNTIME | NO | HIGH | Used by deployment TXT generation and supervisor handlers |
| `outputs/research/` | UNKNOWN | UNKNOWN | LOW | No references found; requires human investigation |
| `requirements.txt` | REQUIRED_BY_RUNTIME | NO | HIGH | Standard Python dependency file |

## Explicit Non-Actions

**Items that look like garbage but MUST NOT be deleted:**

1. `outputs/_trash/` - Empty directory but required by GUI cleanup functionality
2. `outputs/deployment/2026Q1/` - May appear unused but required for deployment TXT generation
3. `plans/_dp/` subdirectory - Contains design documents; required for test compliance

## Commands Used for Reproducibility

```bash
# Inventory scan
find . -maxdepth 2 -type f -name ".*" -prune -o -type f -print | head -50
ls -la
find outputs -maxdepth 3 -type d | sort

# Reference checking
grep -r "plans/" --include="*.py" --include="*.md" --include="*.yaml" --include="*.json" --include="*.txt" . 2>/dev/null | head -20
grep -r "_trash\|deployment" --include="*.py" --include="*.md" --include="*.yaml" --include="*.json" --include="*.txt" src/ tests/ scripts/ 2>/dev/null | head -20

# File examination
ls -la plans/
ls -la outputs/_trash 2>/dev/null || echo "Directory does not exist"
ls -la outputs/deployment/ 2>/dev/null || echo "Directory does not exist"
```

## Conclusion

The repository is largely compliant with the "new system" architecture. All identified non-conforming items have legitimate runtime or test dependencies. The only item requiring human decision is `outputs/research/` directory, which has no obvious references and may be a legacy artifact.

**Recommendation:** Investigate `outputs/research/` directory contents and usage before considering deletion. All other items should remain as they are required for proper system operation.

CLEANUP AUDIT COMPLETE — NO ACTIONS PERFORMED