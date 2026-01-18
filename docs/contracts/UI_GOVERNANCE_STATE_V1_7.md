# UI Governance State SSOT v1.7

## Overview

The UI Governance State system provides a **Single Source of Truth (SSOT)** for UI state management and state-aware action policies. It implements **zero-silent UI** principles where all disabled actions must provide explanations via reason codes.

## Core Concepts

### 1. UI Governance State
The complete state of the UI that affects action enablement:
- **Selected job ID**: Currently selected job (if any)
- **Active tab**: Currently active UI tab
- **Data readiness status**: Status of data components (registry cache, datasets, etc.)
- **Permission level**: User's permission level (VIEWER, OPERATOR, ADMINISTRATOR, DEVELOPER)
- **UI mode**: UI interaction mode (VIEW, EDIT, ADMIN, DEBUG)
- **System readiness**: Whether system is ready for operations
- **Jobs running**: Whether any jobs are currently running

### 2. State-Aware Action Policies
Policies define UI state requirements for each action type:
- **Selected job requirement**: Whether action requires a selected job
- **Active tab requirement**: Required active tab (if any)
- **Data readiness requirements**: List of data components that must be READY
- **Permission level requirement**: Minimum permission level required
- **UI mode requirement**: Minimum UI mode required
- **System readiness requirement**: Whether system must be ready
- **No jobs running requirement**: Whether action requires no jobs to be running

### 3. Zero-Silent UI
When an action is disabled, the system provides:
- **Reason code**: Standardized `GateReasonCode` explaining why action is disabled
- **Explanation**: Human-readable explanation with context variables
- **Context variables**: Variables for explanation template formatting

## Architecture

### File Structure
```
src/contracts/ui_governance_state.py      # Main SSOT module
src/contracts/ui_action_registry.py       # UI action registry (dependency)
tests/contracts/test_ui_governance_state.py  # Comprehensive tests
```

### Key Components

#### 1. Enums
```python
class UiMode(str, Enum):
    VIEW = "VIEW"           # Read-only view mode
    EDIT = "EDIT"           # Edit mode (can modify configurations)
    ADMIN = "ADMIN"         # Administrative mode (full control)
    DEBUG = "DEBUG"         # Debug mode (developer tools)

class PermissionLevel(str, Enum):
    VIEWER = "VIEWER"       # Can view but not modify
    OPERATOR = "OPERATOR"   # Can run jobs and modify configurations
    ADMINISTRATOR = "ADMINISTRATOR"  # Full system control
    DEVELOPER = "DEVELOPER" # Developer access (debug tools)

class DataReadinessStatus(str, Enum):
    NOT_READY = "NOT_READY"     # Data not loaded or available
    LOADING = "LOADING"         # Data loading in progress
    READY = "READY"             # Data ready for use
    ERROR = "ERROR"             # Data loading failed
    PARTIAL = "PARTIAL"         # Partial data available

class UiTab(str, Enum):
    OP_TAB = "OP_TAB"                     # Operation tab (job submission)
    GATE_SUMMARY_DASHBOARD = "GATE_SUMMARY_DASHBOARD"  # Gate summary dashboard
    REPORT_TAB = "REPORT_TAB"             # Report tab
    AUDIT_TAB = "AUDIT_TAB"               # Audit tab
    REGISTRY_TAB = "REGISTRY_TAB"         # Registry tab
    PORTFOLIO_ADMISSION_TAB = "PORTFOLIO_ADMISSION_TAB"  # Portfolio admission
    ALLOCATION_TAB = "ALLOCATION_TAB"     # Allocation tab
    ANALYSIS_DRAWER = "ANALYSIS_DRAWER"   # Analysis drawer widget
```

#### 2. UI Governance State Model
```python
class UiGovernanceState(BaseModel):
    selected_job_id: Optional[str]
    active_tab: Optional[UiTab]
    data_readiness_status: Dict[str, DataReadinessStatus]
    permission_level: PermissionLevel
    ui_mode: UiMode
    system_ready: bool
    any_jobs_running: bool
    last_state_update: datetime
    
    model_config = ConfigDict(frozen=True)  # Immutable
```

#### 3. State-Aware Action Policy
```python
class UiActionPolicy(BaseModel):
    action_type: UiActionType
    requires_selected_job: bool
    requires_active_tab: Optional[UiTab]
    requires_data_ready: List[str]
    requires_permission_level: PermissionLevel
    requires_ui_mode: UiMode
    requires_system_ready: bool
    requires_no_jobs_running: bool
    disabled_reason_code: str  # GateReasonCode
    explanation_template: str
    
    model_config = ConfigDict(frozen=True)
    
    def check_action_enabled(self, state: UiGovernanceState) -> Dict[str, Any]:
        # Returns dict with enabled status, reason code, and explanation
```

#### 4. Action Policy Registry
```python
class UiActionPolicyRegistry(BaseModel):
    policies: Dict[UiActionType, UiActionPolicy]
    
    model_config = ConfigDict(frozen=True)
    
    def check_action_enabled(
        self, 
        action_type: UiActionType, 
        state: UiGovernanceState
    ) -> Dict[str, Any]:
        # Checks if action is enabled given current state
```

#### 5. Singleton State Holder
```python
class UiGovernanceStateHolder:
    """Singleton state holder (similar to active_run_state.py)"""
    
    _instance: Optional[UiGovernanceStateHolder] = None
    
    def get_state(self) -> UiGovernanceState:
        """Get current UI governance state."""
    
    def update_state(self, **kwargs) -> None:
        """Update UI governance state with new values."""
    
    # Convenience methods:
    def set_selected_job(self, job_id: Optional[str]) -> None
    def set_active_tab(self, tab: Optional[UiTab]) -> None
    def set_data_status(self, component: str, status: DataReadinessStatus) -> None
    def set_permission_level(self, level: PermissionLevel) -> None
    def set_ui_mode(self, mode: UiMode) -> None
    def set_system_ready(self, ready: bool) -> None
    def set_any_jobs_running(self, running: bool) -> None

# Global singleton instance
ui_governance_state = UiGovernanceStateHolder()
```

## Default Action Policies

The system includes default policies for all UI action types:

### Job Operations
- **JOB_DETAILS**: Requires selected job
- **JOB_ABORT**: Requires selected job + OPERATOR permission
- **JOB_EXPLAIN**: Requires selected job
- **JOB_SUBMISSION**: Requires system readiness + OPERATOR permission

### Navigation Operations
- **NAVIGATE_JOB_ADMISSION**: Requires selected job
- **NAVIGATE_ARTIFACT**: Requires selected job
- **NAVIGATE_EXPLAIN**: Requires selected job
- **NAVIGATE_GATE_DASHBOARD**: Requires system readiness

### Registry Operations
- **REGISTRY_DATASETS**: Requires registry_cache READY
- **REGISTRY_STRATEGIES**: Requires registry_cache READY
- **REGISTRY_INSTRUMENTS**: Requires registry_cache READY
- **REGISTRY_TIMEFRAMES**: Requires registry_cache READY

### Gate Operations
- **GATE_SUMMARY**: Requires GATE_SUMMARY_DASHBOARD tab active
- **GATE_DASHBOARD**: Requires GATE_SUMMARY_DASHBOARD tab active

### System Operations
- **SYSTEM_PRIME_REGISTRIES**: Requires ADMINISTRATOR permission
- **SYSTEM_HEALTH**: Always available (no requirements)

### Season Operations
- **SEASON_MANAGEMENT**: Requires EDIT mode + OPERATOR permission
- **SEASON_COMPARE**: Requires EDIT mode + OPERATOR permission
- **SEASON_EXPORT**: Requires EDIT mode + OPERATOR permission

## Integration

### 1. ActionRouterService Integration
The `ActionRouterService` now checks UI governance state before handling actions:

```python
def handle_action(self, target: str, context: Optional[Dict[str, Any]] = None) -> bool:
    # Check if action is enabled based on UI governance state
    validation_result = validate_action_for_target(target)
    if not validation_result.get("enabled", True):
        logger.warning(f"Action disabled by UI governance state: {target}")
        return False
    # ... handle action
```

### 2. Checking Action Enablement
```python
from contracts.ui_governance_state import check_ui_action_enabled

# Check if action is enabled
result = check_ui_action_enabled(UiActionType.JOB_DETAILS)
if result["enabled"]:
    # Action is enabled
    pass
else:
    # Action is disabled with reason
    reason_code = result["reason_code"]
    explanation = result["explanation"]
```

### 3. Validating Action Targets
```python
from contracts.ui_governance_state import validate_action_for_target

# Validate any action target
result = validate_action_for_target("job_details://job_123")
if result["enabled"]:
    # Target is valid and enabled
    pass
```

### 4. Updating UI State
```python
from contracts.ui_governance_state import ui_governance_state

# Update UI state
ui_governance_state.set_selected_job("job_123")
ui_governance_state.set_active_tab(UiTab.GATE_SUMMARY_DASHBOARD)
ui_governance_state.set_permission_level(PermissionLevel.OPERATOR)
ui_governance_state.set_ui_mode(UiMode.EDIT)
ui_governance_state.set_system_ready(True)
ui_governance_state.set_any_jobs_running(False)
```

## Governance Rules

### 1. Frozen Models
All Pydantic models use `ConfigDict(frozen=True)` for immutability:
- Prevents accidental state mutations
- Ensures thread safety
- Enforces SSOT principles

### 2. Zero-Silent UI
Every disabled action must provide:
- A `GateReasonCode` for machine-readable classification
- A human-readable explanation with context variables
- No silent failures allowed

### 3. State-Aware Policies
Every UI action must have a state-aware policy defined:
- Policies define precise UI state requirements
- Missing policies default to "allow" for backward compatibility
- New actions must have explicit policies

### 4. Singleton State Holder
- Single source of truth for UI state
- Thread-safe access pattern
- Similar to `active_run_state.py` pattern

## Testing

Comprehensive tests cover:
- Model validation and immutability
- Action policy evaluation
- State holder singleton pattern
- Integration with ActionRouterService
- Frozen model enforcement

Run tests with:
```bash
pytest tests/contracts/test_ui_governance_state.py -v
```

## Migration Guide

### For UI Developers
1. **Check action enablement** before performing actions
2. **Update UI state** when context changes (selected job, active tab, etc.)
3. **Handle disabled actions** by showing reason codes and explanations

### For Action Implementers
1. **Define policies** for new action types in `create_default_action_policies()`
2. **Use reason codes** from `GateReasonCode` enum
3. **Provide explanations** with context variable placeholders

### For System Integrators
1. **Initialize UI state** at application startup
2. **Update state** based on user interactions
3. **Integrate with existing** permission and mode systems

## Future Extensions

### 1. State Persistence
- Save/load UI state from disk
- Restore state across application sessions

### 2. State History
- Track state changes over time
- Undo/redo state transitions

### 3. Advanced Policies
- Conditional requirements based on multiple state variables
- Time-based policies (e.g., "only allow during business hours")
- User role-based policies beyond permission levels

### 4. UI State Visualization
- Debug panel showing current UI state
- Policy evaluation visualizer
- State change timeline

## Related Documents

- [UI Action Registry SSOT](ui_action_registry.md) - UI action definitions
- [Gate Reason Codes](gate_reason_codes.md) - Standardized reason codes
- [Active Run State](active_run_state.md) - Similar singleton pattern

## Version History

### v1.7 (Current)
- Initial implementation with complete UI governance state SSOT
- State-aware action policies for all UI action types
- Zero-silent UI with reason codes and explanations
- Integration with ActionRouterService
- Comprehensive test suite
- Full documentation

### v1.0 (Baseline)
- Basic UI state tracking
- Simple action enablement checks
- No policy system or reason codes