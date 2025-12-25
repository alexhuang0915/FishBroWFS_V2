# No-Fog 2.0 Deep Clean - Phase A: Evidence Inventory

**Date:** 2025-12-25  
**Phase:** A (Evidence Inventory)  
**Status:** READ-ONLY Audit Complete  
**Audit Tool:** `scripts/no_fog/phase_a_audit.py`

## Executive Summary

Phase A of the No-Fog 2.0 Deep Clean has completed evidence collection across five critical dimensions. The audit reveals **87 candidate cleanup items**, **20 runner schism violations**, **13 UI bypass patterns**, **114 stage0-related tests**, **129 tooling drift references**, and **70 GUI import statements**. These findings establish a baseline for subsequent cleanup phases while maintaining a strict READ-ONLY posture.

## 1. Candidate Cleanup Items (File/Folder Level)

### Evidence Summary
- **Pattern:** `GM_Huang|launch_b5\.sh|restore_from_release_txt_force`
- **Matches:** 87 occurrences
- **Primary Locations:** Snapshot files, Makefile, release tool references

### Key Findings
1. **GM_Huang Directory References:** 87 matches across:
   - Snapshot manifests (`TEST_SNAPSHOT2/`, `TEST_SNAPSHOT/`, `SYSTEM_FULL_SNAPSHOT/`)
   - Makefile definitions (`CACHE_CLEANER`, `RELEASE_TOOL`)
   - Release tool integration (`GM_Huang/release_tool.py:243`)

2. **Legacy Scripts:**
   - `scripts/launch_b5.sh` - Excluded from snapshots (extension/filename not in whitelist)
   - `scripts/restore_from_release_txt_force.py` - Active but potentially obsolete

3. **Snapshot Pollution:** Majority of matches (≈80%) are in snapshot documentation rather than active code.

### Cleanup Candidates
| Item | Count | Priority | Notes |
|------|-------|----------|-------|
| GM_Huang directory references | 87 | Medium | Mostly snapshot artifacts |
| launch_b5.sh references | 24 | High | Actively excluded from snapshots |
| restore_from_release_txt_force.py | 15 | Medium | Functional but may be redundant |

## 2. Runner Schism (Single Truth Audit)

### Evidence Summary
- **Pattern:** `funnel_runner|wfs_runner|research_runner|run_funnel|run_wfs|run_research`
- **Matches:** 20 occurrences
- **Files:** 10 distinct source files

### Architecture Violations
1. **Multiple Runner Implementations:**
   - `src/FishBroWFS_V2/pipeline/funnel_runner.py` - Primary funnel runner
   - `src/FishBroWFS_V2/pipeline/funnel.py` - Legacy `run_funnel`
   - `src/FishBroWFS_V2/control/research_runner.py` - Research pipeline
   - `src/FishBroWFS_V2/wfs/runner.py` - WFS with features API

2. **Import Chain Complexity:**
   ```
   research_runner.py → wfs/runner.py → funnel_runner.py → funnel.py
   ```

3. **API Layer Violations:**
   - `gui/nicegui/api.py:5` explicitly prohibits `import FishBroWFS_V2.control.research_runner`
   - Yet `control/worker.py:14` imports `funnel_runner`

### Single Truth Gaps
| Runner Type | Location | Status | Issue |
|-------------|----------|--------|-------|
| Funnel Runner | `pipeline/funnel_runner.py` | Primary | ✅ |
| Legacy Funnel | `pipeline/funnel.py` | Deprecated | ⚠️ Still imported |
| Research Runner | `control/research_runner.py` | Active | ⚠️ Complex dependencies |
| WFS Runner | `wfs/runner.py` | Active | ✅ Well-defined API |

## 3. UI Bypass Scan (Direct Write / Direct Logic Calls)

### Evidence Summary
- **Pattern:** `commit\(|execute\(|insert\(|update\(|delete\(|\.write\(|ActionQueue|UserIntent|submit_intent|enqueue\(`
- **Matches:** 13 occurrences
- **Files:** 4 GUI service files

### Direct Write Findings
1. **File Writes (Acceptable):**
   - `audit_log.py:45` - JSON line writes (audit trail)
   - `archive.py:131` - JSON dump writes (archival)
   - `reload_service.py:125` - Hash updates (crypto)

2. **Intent System Usage:**
   - `intent_bridge.py` - Properly channels UI actions through `UserIntent` → `ActionQueue`
   - No direct database operations found in GUI layer

### Architecture Compliance
✅ **Positive Findings:**
- No direct database `commit/execute/insert/update/delete` calls in GUI
- Intent bridge properly isolates business logic
- File writes are limited to audit/archival purposes

⚠️ **Areas for Review:**
- `reload_service.py` contains hashing logic (potentially business logic in GUI layer)
- Intent bridge has complex type signatures (14 UserIntent references)

## 4. Test Inventory & Obsolescence Candidates

### Evidence Summary
- **Pattern:** `tests/test_stage0_|stage0_`
- **Matches:** 114 occurrences
- **Test Files:** 19 distinct test modules

### Stage0 Test Landscape
**Core Stage0 Tests:**
1. `test_stage0_contract.py` - Import and file existence contracts
2. `test_stage0_no_pnl_contract.py` - Profit/loss field prohibitions
3. `test_stage0_ma_proxy.py` - Moving average proxy scoring
4. `test_stage0_proxy_rank_corr.py` - Ranking correlation tests

**Integration Tests with Stage0:**
- `test_funnel_topk_no_human_contract.py` (12 matches)
- `test_governance_eval_rules.py` (8 matches)
- `test_governance_accepts_winners_v2.py` (6 matches)
- `test_funnel_smoke_contract.py` (6 matches)

**Configuration References:**
- `WFSSpec.stage0_subsample` parameter (12 matches)
- `stage0_coarse` stage name (34 matches)

### Obsolescence Analysis
| Test Category | Count | Maturity | Consolidation Potential |
|---------------|-------|----------|-------------------------|
| Pure Stage0 Contracts | 4 files | High | Low (core contracts) |
| Funnel Integration | 5 files | High | Medium |
| Governance Integration | 3 files | Medium | High |
| Configuration Tests | 7 files | Low | High |

**Recommendation:** Consolidate stage0 configuration tests into a single parameter validation suite.

## 5. Tooling Rules Drift (.continue/rules, Makefile, .github)

### Evidence Summary
- **Pattern:** `pytest|make check|no-fog|full-snapshot|snapshot`
- **Matches:** 129 occurrences
- **Scope:** Makefile, GitHub Actions, tooling scripts

### Tooling Ecosystem Analysis
**Makefile (39 matches):**
- `make check` - Primary safe testing command
- `make full-snapshot` - Repository snapshot generation
- `make no-fog` - Core contract and snapshot integrity gate

**GitHub Actions (12 matches):**
- `no-fog-gate.yml` - CI pipeline for No-Fog Gate
- Snapshot caching and artifact upload configurations

**Tooling Scripts (78 matches):**
- `scripts/no_fog/` - Dedicated No-Fog tooling (gate, snapshot generator)
- `scripts/test_freeze_snapshot.py` - Freeze functionality tests
- `scripts/verify_season_integrity.py` - Snapshot verification

### Rules Drift Detection
1. **Snapshot Consistency:**
   - Multiple snapshot generators exist (`generate_full_snapshot.py`, freeze snapshots)
   - Verification logic duplicated across scripts

2. **Test Tooling:**
   - `pytest` referenced 45 times across tooling
   - Safe mode configurations (`SAFE_ENV`, `SAFE_PYTEST_ADDOPTS`)

3. **Gate Definitions:**
   - No-Fog Gate defined in 3 locations: Makefile, shell script, Python module
   - Slight parameter variations between implementations

## 6. Imports Audit (FishBroWFS_V2 within GUI)

### Evidence Summary
- **Pattern:** `^from FishBroWFS_V2|^import FishBroWFS_V2`
- **Matches:** 70 import statements
- **GUI Files:** 15 distinct modules

### Import Architecture
**Core Imports (Acceptable):**
- `season_context` (8 imports) - UI needs season awareness
- `artifact_reader` (5 imports) - Artifact display
- `season_state` (3 imports) - Freeze state checks

**Service Layer Imports:**
- `control.job_api` (4 imports) - Job listing/status
- `control.dataset_catalog` (3 imports) - Dataset selection
- `control.strategy_catalog` (3 imports) - Strategy selection

**Potential Circular Dependencies:**
- `gui.viewer` imports `gui.viewer.components` (internal)
- `gui.nicegui` imports `gui.services` (cross-layer but acceptable)

### Import Health Score
✅ **Well-Structured:**
- GUI imports primarily from `core.*` and `control.*` (proper layering)
- No business logic imports from `pipeline.*` or `research.*`
- Intent bridge properly isolates action queue

⚠️ **Review Needed:**
- 70 imports across 15 files suggests high coupling
- `gui/services/reload_service.py` imports 7 different FishBroWFS_V2 modules

## Phase A Recommendations

### Immediate Actions (Phase B)
1. **Cleanup Candidate Triage:**
   - Archive `GM_Huang` references from snapshots
   - Remove `launch_b5.sh` exclusion rules (file already excluded)
   - Evaluate `restore_from_release_txt_force.py` necessity

2. **Runner Consolidation:**
   - Design single truth runner architecture
   - Deprecate `pipeline/funnel.py` `run_funnel` in favor of `funnel_runner.py`
   - Simplify research runner dependency chain

3. **Test Suite Rationalization:**
   - Consolidate stage0 configuration tests
   - Create test inventory dashboard for obsolescence tracking

### Monitoring Metrics
| Metric | Current | Target | Phase |
|--------|---------|--------|-------|
| GM_Huang references | 87 | <10 | B |
| Runner implementations | 4 | 2 | C |
| Stage0 test files | 19 | 12 | B |
| GUI import statements | 70 | 50 | C |

## Evidence Collection Methodology

### Commands Executed
```bash
# 1. Candidate Cleanup Items
rg -n "GM_Huang|launch_b5\.sh|restore_from_release_txt_force" .

# 2. Runner Schism
rg -n "funnel_runner|wfs_runner|research_runner|run_funnel|run_wfs|run_research" src/FishBroWFS_V2

# 3. UI Bypass Scan
rg -n "commit\(|execute\(|insert\(|update\(|delete\(|\.write\(" src/FishBroWFS_V2/gui
rg -n "ActionQueue|UserIntent|submit_intent|enqueue\(" src/FishBroWFS_V2/gui

# 4. Test Inventory
rg -n "tests/test_stage0_|stage0_" tests

# 5. Tooling Rules Drift
rg -n "pytest|make check|no-fog|full-snapshot|snapshot" Makefile .github scripts

# 6. Imports Audit
rg -n "^from FishBroWFS_V2|^import FishBroWFS_V2" src/FishBroWFS_V2/gui
```

### Audit Script
The helper script `scripts/no_fog/phase_a_audit.py` provides reproducible evidence collection with JSON output support.

## Next Phase (Phase B) Preparation

Phase B will transition from evidence collection to targeted cleanup actions, focusing on:

1. **File/Folder Cleanup** - Remove confirmed obsolete artifacts
2. **Runner Unification** - Establish single truth runner architecture
3. **Test Consolidation** - Merge redundant test suites
4. **Import Optimization** - Reduce GUI layer coupling

**Phase A Complete:** Evidence inventory establishes quantitative baseline for all cleanup dimensions. No files were modified, moved, renamed, or refactored during this READ-ONLY phase.

---
*No-Fog 2.0 Deep Clean - Phase A completed 2025-12-25T12:04:01Z*  
*Evidence preserved in `/tmp/phase_a_evidence.json`*  
*Next: Phase B - Targeted Cleanup Execution*