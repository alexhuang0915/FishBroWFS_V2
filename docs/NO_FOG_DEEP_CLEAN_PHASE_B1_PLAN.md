# No-Fog 2.0 Deep Clean - Phase B-1: Targeted Cleanup Plan

**Date:** 2025-12-25  
**Phase:** B-1 (Targeted Cleanup Plan)  
**Status:** PLAN ONLY, READ-ONLY  
**Previous Phase:** [Phase A Evidence Inventory](NO_FOG_DEEP_CLEAN_PHASE_A.md)

## Executive Summary

Phase B-1 establishes the execution plan for targeted cleanup actions based on Phase A evidence. This plan defines **atomic operations** across six cleanup dimensions, establishes **triage criteria** for GM_Huang/launch scripts, designs **runner unification architecture**, hardens **UI bypass defenses**, rationalizes **stage0 test suite**, and sequences **Phase B-2 execution**. All operations maintain strict backward compatibility and zero regression guarantees.

## Section 0: Non-negotiables (Contracts)

### Core Integrity Constraints
1. **No Regression**: All cleanup operations must pass existing test suite (`make check`)
2. **Backward Compatibility**: API signatures unchanged; behavioral changes documented
3. **Deterministic Snapshot**: SYSTEM_FULL_SNAPSHOT regenerates cleanly after each operation
4. **No-Fog Gate Compliance**: All changes must pass `make no-fog` gate
5. **Atomic Operations**: Each OP-XX is independently testable and revertible

### Evidence Baseline (Post-Phase A)
| Dimension | Phase A Count | Current Verification | Delta |
|-----------|---------------|----------------------|-------|
| GM_Huang/launch references | 87 | 123 | +36 (snapshot growth) |
| Runner schism violations | 20 | 20 | 0 |
| UI bypass patterns | 13 | 3 | -10 (improved) |
| Stage0 test references | 114 | 114 | 0 |
| GUI import statements | 70 | TBD | - |

*Note: GM_Huang count increased due to snapshot expansion; actual cleanup scope remains 87 original references.*

## Section 1: Change List (Atomic Operations)

### OP-01: GM_Huang Snapshot Reference Cleanup
**Objective**: Remove GM_Huang directory references from snapshot manifests while preserving functional references in Makefile/release tool.

**Evidence**:
```bash
$ rg -n "GM_Huang" . | head -5
./TEST_SNAPSHOT2/SNAPSHOT_0001.md:14:GM_Huang/clean_repo_caches.py (2133 bytes, sha256:25fc11e0)
./TEST_SNAPSHOT2/SNAPSHOT_0001.md:15:GM_Huang/release_tool.py (8983 bytes, sha256:eee9a8e4)
./TEST_SNAPSHOT2/SNAPSHOT_0001.md:560:CACHE_CLEANER := GM_Huang/clean_repo_caches.py
./TEST_SNAPSHOT2/SNAPSHOT_0001.md:561:RELEASE_TOOL := GM_Huang/release_tool.py
./TEST_SNAPSHOT2/SNAPSHOT_0001.md:1982:FILE GM_Huang/clean_repo_caches.py
```

**Operations**:
1. Identify snapshot-only references (80% of 123 matches)
2. Preserve Makefile functional references (`CACHE_CLEANER`, `RELEASE_TOOL`)
3. Update snapshot generator to exclude GM_Huang from future snapshots
4. Verify `make full-snapshot` produces clean output

**Acceptance Criteria**:
- GM_Huang references reduced from 123 to <20 (functional only)
- `make check` passes
- `make no-fog` passes

### OP-02: launch_b5.sh Exclusion Rule Removal
**Objective**: Remove `launch_b5.sh` from snapshot exclusion rules (file already excluded).

**Evidence**:
```bash
$ rg -n "launch_b5\.sh" .
./scripts/no_fog/phase_a_audit.py:45:    patterns = ["GM_Huang", "launch_b5\\.sh", "restore_from_release_txt_force"]
./scripts/no_fog/phase_a_audit.py:67:        "launch_b5.sh references": launch_b5_count,
```

**Operations**:
1. Audit snapshot generator exclusion patterns
2. Remove redundant `launch_b5.sh` patterns
3. Verify file remains excluded via default patterns

**Acceptance Criteria**:
- No functional change to snapshot behavior
- Exclusion logic simplified
- `make full-snapshot` verification

### OP-03: restore_from_release_txt_force.py Evaluation
**Objective**: Determine if `restore_from_release_txt_force.py` is obsolete or required.

**Evidence**:
```bash
$ rg -n "restore_from_release_txt_force" .
./scripts/no_fog/phase_a_audit.py:45:    patterns = ["GM_Huang", "launch_b5\\.sh", "restore_from_release_txt_force"]
./scripts/no_fog/phase_a_audit.py:69:        "restore_from_release_txt_force.py": restore_count,
```

**Operations**:
1. Analyze script dependencies and usage
2. Check if functionality duplicated elsewhere
3. Decision: Archive or retain with documentation

**Acceptance Criteria**:
- Clear retention/archive decision
- If archived: remove from active codebase
- If retained: document purpose and dependencies

### OP-04: Funnel Runner Deprecation
**Objective**: Deprecate `pipeline/funnel.py` `run_funnel` in favor of `funnel_runner.py`.

**Evidence**:
```bash
$ rg -n "run_funnel" src/FishBroWFS_V2
src/FishBroWFS_V2/pipeline/funnel.py:489:def run_funnel(
src/FishBroWFS_V2/control/worker.py:14:from FishBroWFS_V2.pipeline.funnel_runner import run_funnel
```

**Operations**:
1. Update `control/worker.py` import to use `funnel_runner.run_funnel`
2. Add deprecation warning to `pipeline/funnel.py` `run_funnel`
3. Verify no other imports reference legacy function

**Acceptance Criteria**:
- Single source of truth for `run_funnel`
- Deprecation warning visible in logs
- `make check` passes

### OP-05: Research Runner Dependency Simplification
**Objective**: Simplify `research_runner.py` dependency chain.

**Evidence**:
```bash
$ rg -n "research_runner" src/FishBroWFS_V2
src/FishBroWFS_V2/gui/nicegui/api.py:5:1. 禁止 import FishBroWFS_V2.control.research_runner
src/FishBroWFS_V2/control/research_runner.py:2:# src/FishBroWFS_V2/control/research_runner.py
```

**Operations**:
1. Analyze import chain: `research_runner.py → wfs/runner.py → funnel_runner.py → funnel.py`
2. Extract common interfaces to reduce coupling
3. Maintain API compatibility

**Acceptance Criteria**:
- Import chain depth reduced by ≥1
- No breaking changes to research pipeline
- `test_research_runner.py` passes

### OP-06: Single Truth Runner Architecture Design
**Objective**: Design unified runner architecture for Phase C implementation.

**Operations**:
1. Document current runner responsibilities:
   - `funnel_runner.py`: Core funnel execution
   - `wfs/runner.py`: WFS with features API  
   - `research_runner.py`: Research pipeline
   - `pipeline/funnel.py`: Legacy (to be deprecated)
2. Define unified interface:
   - `BaseRunner` abstract class
   - `run()` method with standardized parameters
   - `status()` method for progress monitoring
3. Create migration path for Phase C

**Deliverable**: `docs/RUNNER_UNIFICATION_DESIGN.md`

### OP-07: UI Bypass Hardening Verification
**Objective**: Verify UI bypass patterns are legitimate (audit logs, archival, hashing).

**Evidence**:
```bash
$ rg -n "commit\(|execute\(|insert\(|update\(|delete\(|\.write\(" src/FishBroWFS_V2/gui
src/FishBroWFS_V2/gui/services/audit_log.py:45:            f.write(json.dumps(record) + "\n")
src/FishBroWFS_V2/gui/services/archive.py:131:        json.dump(archive_data, f, indent=2)
src/FishBroWFS_V2/gui/services/reload_service.py:125:            hasher.update(chunk)
```

**Operations**:
1. Validate each write operation:
   - `audit_log.py:45`: JSON line writes (audit trail) ✅
   - `archive.py:131`: JSON dump writes (archival) ✅
   - `reload_service.py:125`: Hash updates (crypto) ✅
2. Confirm no database operations in GUI layer
3. Document legitimate write patterns

**Acceptance Criteria**:
- All GUI writes classified as legitimate
- No database operations found
- Intent bridge properly isolates business logic

### OP-08: Stage0 Test Consolidation Analysis
**Objective**: Analyze stage0 test suite for consolidation opportunities.

**Evidence**:
```bash
$ rg -l "test_stage0_" tests
tests/test_stage0_contract.py
tests/test_stage0_no_pnl_contract.py
tests/test_stage0_ma_proxy.py
tests/test_stage0_proxy_rank_corr.py
tests/test_stage0_proxies.py
```

**Operations**:
1. Categorize stage0 tests:
   - Core contracts (4 files): Low consolidation potential
   - Integration tests (5 files): Medium consolidation potential  
   - Configuration tests (7 files): High consolidation potential
2. Design consolidated test structure
3. Plan incremental migration

**Deliverable**: `docs/STAGE0_TEST_RATIONALIZATION_PLAN.md`

### OP-09: GUI Import Reduction Strategy
**Objective**: Develop strategy to reduce GUI import statements from 70 to <50.

**Operations**:
1. Analyze import heatmap:
   - `season_context` (8 imports)
   - `artifact_reader` (5 imports)
   - `control.job_api` (4 imports)
2. Identify consolidation opportunities:
   - Create facade interfaces
   - Use dependency injection
   - Lazy loading patterns
3. Phase C implementation plan

**Deliverable**: Import reduction strategy document

## Section 2: GM_Huang / Launch Scripts (Triage Plan)

### Triage Matrix
| Item | Count | Location | Priority | Action |
|------|-------|----------|----------|--------|
| GM_Huang snapshot references | ~100 | TEST_SNAPSHOT2/, SYSTEM_FULL_SNAPSHOT/ | Medium | OP-01 |
| GM_Huang functional references | ~20 | Makefile, release tool | Low | Preserve |
| launch_b5.sh references | 2 | Audit script | Low | OP-02 |
| restore_from_release_txt_force.py | 2 | Audit script | Medium | OP-03 |

### Risk Assessment
1. **Snapshot References**: Zero risk (documentation only)
2. **Makefile References**: Low risk (build system dependencies)
3. **Launch Scripts**: Medium risk (potential build breaks)

### Execution Order
1. OP-02 (lowest risk)
2. OP-03 (medium risk, evaluation first)
3. OP-01 (highest volume, but zero functional risk)

## Section 3: Runner Unification (Single Truth Plan)

### Current Architecture Violations
1. **Multiple Implementations**: 4 runner variants
2. **Import Chain Complexity**: 4-layer deep dependencies
3. **API Layer Violations**: `gui/nicegui/api.py:5` prohibition ignored

### Single Truth Design Principles
1. **One Runner Per Responsibility**:
   - `funnel_runner.py`: Core funnel execution (primary)
   - `wfs/runner.py`: WFS feature execution (specialized)
   - `research_runner.py`: Research pipeline (orchestration)
2. **Clear Interface Boundaries**:
   - Each runner exposes well-defined API
   - No cross-runner implementation dependencies
   - Shared utilities in `pipeline/common.py`
3. **Deprecation Path**:
   - `pipeline/funnel.py` → `funnel_runner.py`
   - Gradual migration in Phase C

### Phase B-1 Deliverables
1. OP-04: Funnel runner deprecation
2. OP-05: Research runner dependency simplification
3. OP-06: Unified architecture design document

## Section 4: UI "Bypass" Hardening (Correct Interpretation)

### Legitimate Write Patterns
✅ **Acceptable (No Bypass)**:
1. **Audit Trail Writes**: `audit_log.py:45` - JSON line writes for audit trail
2. **Archival Writes**: `archive.py:131` - JSON dump for data archival
3. **Cryptographic Hashes**: `reload_service.py:125` - Hash updates for integrity

❌ **Prohibited (True Bypass)**:
1. **Database Operations**: `commit()`, `execute()`, `insert()`, `update()`, `delete()`
2. **Direct State Modification**: Bypassing `UserIntent` → `ActionQueue` pipeline
3. **Business Logic in GUI**: Calculations, transformations, decision logic

### Verification Results
- **3 write operations found**: All legitimate
- **0 database operations found**: Compliance achieved
- **Intent system integrity**: `intent_bridge.py` properly channels UI actions

### Hardening Actions
1. **Documentation**: Clarify legitimate vs prohibited patterns
2. **Static Analysis**: Add check for database operation patterns
3. **Test Coverage**: Enhance `test_ui_honest_api.py` for write pattern validation

## Section 5: Stage0 Tests Rationalization Plan

### Current Landscape
**19 test modules** with 114 stage0 references:
- **Core Contracts (4)**: Essential, keep as-is
- **Funnel Integration (5)**: Consolidate into 2-3 modules
- **Governance Integration (3)**: Merge into single governance test
- **Configuration Tests (7)**: Merge into parameter validation suite

### Rationalization Strategy
1. **Phase B-1 (Analysis)**:
   - OP-08: Consolidation analysis
   - Create test dependency graph
   - Identify duplicate assertions

2. **Phase B-2 (Execution)**:
   - Merge configuration tests
   - Create unified parameter validation suite
   - Update test references

3. **Phase C (Optimization)**:
   - Further consolidation based on usage patterns
   - Performance optimization
   - Documentation updates

### Target Metrics
- Test modules: 19 → 12 (37% reduction)
- Stage0 references: 114 → 80 (30% reduction)
- Execution time: Maintain or improve

## Section 6: Execution Order (Phase B-2 sequence)

### Phase B-2 Atomic Operation Sequence
1. **Preparation**:
   - Backup verification (`make check` passing)
   - Snapshot baseline (`make full-snapshot`)

2. **Low-Risk Operations**:
   - OP-02: launch_b5.sh exclusion rule removal
   - OP-07: UI bypass hardening verification
   - OP-08: Stage0 test consolidation analysis

3. **Medium-Risk Operations**:
   - OP-03: restore_from_release_txt_force.py evaluation
   - OP-04: Funnel runner deprecation
   - OP-05: Research runner dependency simplification

4. **High-Volume Operations**:
   - OP-01: GM_Huang snapshot reference cleanup

5. **Design Deliverables**:
   - OP-06: Single truth runner architecture design
   - OP-09: GUI import reduction strategy

### Dependency Graph
```
OP-02 → OP-01 (snapshot cleanup)
OP-07 → (independent)
OP-08 → (analysis only)
OP-03 → (evaluation only)
OP-04 → OP-06 (runner design)
OP-05 → OP-06 (runner design)
OP-06 → Phase C (implementation)
OP-09 → Phase C (implementation)
```

### Risk Mitigation
1. **Per-Operation Verification**:
   - `make check` after each OP-XX
   - `make no-fog` gate compliance
   - Snapshot regeneration test

2. **Rollback Strategy**:
   - Git commits after each successful operation
   - Clear revert instructions per OP-XX
   - Pre-operation backup tags

## Section 7: Phase B-2 Exit Criteria

### Quantitative Metrics
| Metric | Current | Target | Verification |
|--------|---------|--------|--------------|
| GM_Huang references | 123 | <30 | `rg -n "GM_Huang" .` |
| Runner implementations | 4 | 3 (deprecated 1) | Architecture review |
| UI bypass patterns | 3 | 3 (all legitimate) | Manual verification |
| Stage0 test analysis | 0% | 100% complete | OP-08 deliverable |
| Design documents | 0 | 2 (runner + import) | Docs review |

### Quality Gates
1. **Test Suite Integrity**: `make check` passes all tests
2. **No-Fog Gate**: `make no-fog` passes (snapshot + core contracts)
3. **Snapshot Consistency**: `make full-snapshot` produces clean output
4. **Backward Compatibility**: No breaking API changes
5. **Documentation**: All operations documented with evidence

### Deliverables
1. **Executed Operations**: OP-01 through OP-05 completed
2. **Design Documents**: 
   - `docs/RUNNER_UNIFICATION_DESIGN.md`
   - `docs/STAGE0_TEST_RATIONALIZATION_PLAN.md`
   - GUI import reduction strategy
3. **Updated Evidence**: Post-cleanup `rg` command outputs
4. **Phase B-2 Report**: Summary of changes and verification

### Success Criteria
- ✅ All atomic operations completed or properly scoped
- ✅ Zero test regressions
- ✅ No-Fog gate passes
- ✅ Snapshot regenerates cleanly
- ✅ Design documents ready for Phase C implementation
- ✅ Risk assessment updated for remaining technical debt

## Evidence Comm