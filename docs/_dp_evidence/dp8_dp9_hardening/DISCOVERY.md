# DP8/DP9 Hardening Mini-Phase: Discovery

## Discovery Process
Used `codebase_search` to locate relevant files and understand the root causes of test failures.

## Key Findings

### 1. GateV1 vs GateItemV1 Naming Issue
**Search Query**: "GateV1 class definition"
**Results**: No exact match found for `GateV1` class definition.

**Search Query**: "GateItemV1 class"
**Results**: Found in `src/contracts/portfolio/gate_summary_schemas.py`:
```python
class GateItemV1(BaseModel):
    name: str
    verdict: GateVerdict
    severity: Optional[GateSeverity] = None
    reason_cards: Optional[List[ReasonCardV1]] = None
    evaluated_at_utc: datetime
    evaluator: str
    source: str
```

**Analysis**: Tests reference `GateV1` but the canonical class is `GateItemV1`. This is a naming inconsistency between test expectations and implementation.

### 2. GateSummaryV1 Schema Requirements
**Search Query**: "GateSummaryV1 class"
**Results**: Found in `src/contracts/portfolio/gate_summary_schemas.py`:
```python
class GateSummaryV1(BaseModel):
    job_id: str
    evaluated_at_utc: datetime
    evaluator: str
    source: str
    gates: List[GateItemV1]
    counts: Optional[Dict[str, int]] = None
    
    @property
    def total_gates(self) -> int:
        return len(self.gates)
```

**Key Insights**:
- `total_gates` is a property, not a field
- `evaluated_at_utc`, `evaluator`, `source` are required fields
- `counts` is optional Dict[str, int]

### 3. Job Admission Policy Engine Logic
**Search Query**: "job_admission_policy_engine evaluate_job"
**Results**: Found in `src/gui/services/job_admission_policy_engine.py`:
```python
def evaluate_job(
    job_id: str,
    gate_summary: GateSummaryV1,
    rules: List[JobAdmissionRule] = DEFAULT_RULES,
) -> JobAdmissionDecision:
```

**Policy Rules Analysis**:
- `REJECT_ALWAYS_REJECT`: Rejects if any gate has verdict == REJECTED
- `MAX_FAIL_GATES`: Only triggers when verdict == ADMITTED and fail_gates > threshold
- Critical gates (like "Data Alignment") cause immediate rejection

### 4. Function Name Changes
**Search Query**: "get_job_artifact_dir"
**Results**: No exact match found.

**Search Query**: "get_job_evidence_dir"
**Results**: Found in `src/control/job_artifacts.py`:
```python
def get_job_evidence_dir(job_id: str) -> Path:
```

**Analysis**: Tests were patching deprecated/non-existent functions. The correct function is `get_job_evidence_dir`.

### 5. PySide6 Import Issues
**Search Query**: "PySide6 import"
**Results**: Found in `tests/gui/services/test_action_router_service.py`:
```python
from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
```

**Analysis**: UI tests fail in headless environment without PySide6 installed. Need proper test skipping.

## Root Causes Identified

1. **Naming Inconsistency**: Tests use `GateV1` but implementation uses `GateItemV1`
2. **Schema Validation Errors**: Tests missing required fields (`evaluated_at_utc`, `evaluator`, `source`)
3. **Policy Logic Mismatch**: Test expectations don't match actual policy behavior
4. **Deprecated Functions**: Tests reference functions that don't exist
5. **Headless Environment**: UI tests fail without PySide6

## Evidence Files Examined

1. `src/contracts/portfolio/gate_summary_schemas.py` - Gate schemas
2. `src/gui/services/job_admission_policy_engine.py` - Admission policy logic
3. `tests/gui/services/test_job_admission_policy_engine.py` - DP8 tests
4. `tests/gui/services/test_action_router_service.py` - DP9 tests
5. `src/control/job_artifacts.py` - Evidence directory functions

## Conclusion
The test failures are due to:
- Naming/schema alignment issues between tests and implementation
- Missing required fields in test data
- Incorrect mock patches for deprecated functions
- Headless environment incompatibility for UI tests

All issues are fixable without changing production logic.