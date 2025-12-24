# FishBroWFS_V2 Warnings Policy

## Purpose

This document outlines the policy for handling warnings in the FishBroWFS_V2 codebase. The goal is to maintain a clean, warning-free development environment while being explicit about which warnings are acceptable and which should be treated as regressions.

## Phase 2 Technical Debt Cleanup (Completed)

The following warnings were eliminated in Phase 2:

### 1. Pydantic v2 Migration Warnings
- **Issue**: `class Config:` deprecated in favor of `model_config = ConfigDict(...)`
- **Fix**: Converted all class-based Config to ConfigDict
  - `src/FishBroWFS_V2/core/schemas/manifest.py`: UnifiedManifest.Config → model_config
- **Issue**: `.dict()` method deprecated in favor of `.model_dump()`
- **Fix**: Replaced all `.dict()` calls with `.model_dump()`
  - `src/FishBroWFS_V2/portfolio/artifacts_writer_v1.py`
  - `src/FishBroWFS_V2/portfolio/cli.py`
  - `src/FishBroWFS_V2/portfolio/signal_series_writer.py`
  - `src/FishBroWFS_V2/portfolio/writer.py` (already had fallback)

### 2. Python 3.12 datetime.utcnow() Deprecation
- **Issue**: `datetime.utcnow()` deprecated in favor of timezone-aware UTC
- **Fix**: Replaced with `datetime.now(timezone.utc).replace(tzinfo=None)` for backward compatibility
  - `src/FishBroWFS_V2/core/schemas/portfolio_v1.py`: AdmissionDecisionV1.decision_ts default_factory
- **Note**: The `.replace(tzinfo=None)` preserves naive datetime output to maintain existing artifact contracts.

### 3. Pydantic Field Name Shadowing
- **Issue**: Field name "schema" shadows BaseModel attribute in `SignalSeriesMetaV1`
- **Fix**: Renamed field to `schema_id` with alias="schema"
  - `src/FishBroWFS_V2/core/schemas/portfolio.py`: SignalSeriesMetaV1
  - Updated usage in `src/FishBroWFS_V2/portfolio/signal_series_writer.py` to use `by_alias=True`

## Acceptable Warnings (Not Suppressed)

### 1. Multiprocessing Fork Warnings
- **Source**: Python's multiprocessing module when using fork() with multi-threaded processes
- **Location**: Tests that spawn subprocesses (e.g., `tests/test_jobs_db_concurrency_smoke.py`)
- **Decision**: Acceptable external warning; does not indicate code issues in FishBroWFS_V2
- **Action**: No suppression; monitor for changes in Python behavior

### 2. Third-party Library Deprecation Warnings
- **Source**: Pydantic internal usage of deprecated datetime methods
- **Example**: `pydantic/main.py:250` warning about `datetime.utcnow()`
- **Decision**: External library issue; will be resolved when pydantic updates
- **Action**: No suppression; track pydantic updates

### 3. Pydantic Field Validation Warnings
- **Source**: Pydantic field validation that doesn't affect functionality
- **Decision**: Acceptable if they don't indicate semantic issues
- **Action**: Review periodically, but no suppression

## Zero-Suppression Policy

We do **NOT** use global warning suppression mechanisms:

- No `filterwarnings = ignore` in `pyproject.toml`
- No `warnings.filterwarnings()` in code to hide warnings
- No `norecursedirs` to hide test directories
- No moving tests to avoid collection

All warnings must be addressed at the source or explicitly documented as acceptable.

## Regression Prevention

### New Warnings as Regressions
Any new warning that appears in `make check` output should be treated as a regression:

1. **Immediate investigation**: Determine if warning indicates a real issue
2. **Fix or document**: Either fix the warning or add to acceptable warnings list with justification
3. **CI enforcement**: Consider adding warning count check to CI pipeline

### Warning Monitoring
- Run `make check` regularly to monitor warning count
- Use `pytest -Werror` in development to catch new warnings early
- Review warning output in PR reviews

## Maintenance

This document should be updated when:
1. New warning categories are identified as acceptable
2. External library updates eliminate existing warnings
3. New suppression mechanisms are considered (must be justified)

## Related Files

- `pyproject.toml`: Contains pytest configuration without warning filters
- `Makefile`: `make check` target runs tests with warning reporting
- Test files: Should not contain warning suppression unless absolutely necessary

## Last Updated

2025-12-24 (Phase 2 Tech Debt Cleanup)