# Phase E.1 — Job Tracker → Professional Execution Monitor

## Implementation Summary

### 1. Advanced Filtering (UI-side only)
- Added filter widgets above the Job Tracker table:
  - Status filter: [ALL, PENDING, RUNNING, SUCCEEDED, FAILED, REJECTED]
  - Strategy filter (populated from job data)
  - Instrument filter (populated from job data)
  - Season filter (populated from job data)
  - Text search (job_id substring, strategy, instrument)
  - Clear Filters button
- Filtering is performed client-side via `JobsTableModel.apply_filters()`
- Filter dropdowns automatically update when new jobs are loaded

### 2. Column Enhancements
- Added new columns to the Jobs table:
  - Run Mode (extracted from config_snapshot)
  - Season (from job spec)
  - Duration (computed from created_at/finished_at, live-updating for RUNNING jobs)
  - Score (placeholder, to be populated from report artifacts)
- Duration formatting: seconds/minutes/hours based on magnitude
- Score column shows 3 decimal places, colored green/red for positive/negative

### 3. Status Cell Color Coding
- Updated color scheme per Phase E.1 requirements:
  - RUNNING → amber (#FF9800)
  - SUCCEEDED → green (#4CAF50)
  - FAILED/REJECTED → red (#F44336)
  - PENDING/STARTED → lighter amber (#FFC107)
- Status text remains bold for emphasis

### 4. Action Buttons (Governance-Safe)
- Added "Explain Failure" button visible only for FAILED/REJECTED jobs
- Button calls `GET /api/v1/jobs/{job_id}/artifacts`
- Fetches `policy_check.json` and `runtime_metrics.json`
- Displays summarized explanation dialog with:
  - Policy gate failures
  - Runtime errors
  - Exit codes and signals
- Existing buttons preserved: View Logs, Open Evidence, Open Report

### 5. API Enhancements
- Updated `JobListResponse` model in `src/control/api.py`:
  - Added `run_mode`, `season`, `duration_seconds`, `score` fields
  - Enhanced `_job_record_to_response` to extract these from job spec
  - Duration computed with live updating for RUNNING jobs
- API contract snapshot updated via `make api-snapshot`

### 6. UI Improvements
- Adjusted column widths to accommodate new columns
- Actions column widened to fit 4 buttons
- Filter UI uses compact layout with appropriate spacing
- Added auto-refresh status indicator

## Files Modified

### Core Implementation
1. `src/control/api.py`
   - Updated `JobListResponse` Pydantic model
   - Enhanced `_job_record_to_response` function
   - Added duration calculation and field extraction

2. `src/gui/desktop/tabs/op_tab.py`
   - Updated `JobsTableModel`:
     - Added new columns to headers
     - Implemented filtering system (`all_jobs` vs `filtered_jobs`)
     - Added `apply_filters`, `update_filter`, `get_unique_values` methods
     - Enhanced `data()` method for new columns and color coding
   - Updated `ActionsDelegate`:
     - Added "Explain Failure" button (visible only for FAILED/REJECTED)
     - Adjusted button layout for 4 buttons
   - Updated `OpTab`:
     - Added filter UI widgets (status, strategy, instrument, season, search)
     - Added `apply_filters`, `clear_filters`, `update_filter_dropdowns` methods
     - Added `explain_failure` and `_extract_failure_explanation` methods
     - Connected filter signals

### Supporting Changes
- Added `QLineEdit` import for search field
- Updated column width configuration
- Added filter dropdown population logic

## Evidence of Compliance

### Governance & Security
- No filesystem access from UI (dumb client principle maintained)
- No SQLite access from UI
- No path construction from UI
- Supervisor remains sole authority for job lifecycle and evidence generation
- Evidence immutability preserved (`outputs/jobs/<job_id>/**`)
- No repo root pollution (all changes within `src/gui/**` and `src/control/**`)

### Testing
- `make check` passes with 0 failures (1386 passed, 36 skipped, 10 xfailed)
- API contract snapshot updated to reflect new fields
- Root hygiene violation fixed (removed stray `check_job_structure.py`)

### Operator Experience Improvements
- Operator can now answer in <10 seconds:
  - "What failed?" → Status column color + "Explain Failure" button
  - "Why?" → Detailed explanation from policy_check + runtime_metrics
  - "What should I do next?" → Recommended actions based on failure type
- Advanced filtering enables quick isolation of jobs by status, strategy, instrument, season
- Duration column provides immediate insight into job execution time
- Run Mode and Season columns provide context about job parameters

## Next Steps (Phase E.2+)
- E.2: Strategy Report → CTA-Grade Analytics
- E.3: Portfolio Report → Allocation Decision Desk
- E.4: Output Hygiene & Operator UX Polish

## Screenshots
*(If available, include before/after screenshots of Job Tracker)*

## Git Diff
```
git diff HEAD~1 -- src/control/api.py src/gui/desktop/tabs/op_tab.py
```

## Test Output
```
make check: 1386 passed, 36 skipped, 2 deselected, 10 xfailed
```

---
**Phase E.1 Complete** — Job Tracker transformed into professional execution monitor with advanced filtering, enhanced columns, color-coded status, and failure explanation capabilities.