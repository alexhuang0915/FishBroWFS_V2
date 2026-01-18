# UI Wizard Engine v1.8 - Technical Specification

## Overview

The UI Wizard Engine v1.8 provides guided workflows for two primary use cases:
1. **Run Job Wizard**: Guided job creation → submit → track → gate fetch
2. **Gate Fix Wizard**: Primary fail → explain → recommended actions → verify

The engine implements **zero-silent validation**: every blocked "Next" action shows a `reason_code → explain` using the v1.4 Explain Dictionary.

## Architecture

### 1. SSOT Contracts (Phase 1)
**Location**: `src/contracts/ui/wizard/`

#### Core Models:
- **`WizardState`**: Immutable state with `ConfigDict(frozen=True)`
  - `wizard_id`, `wizard_type`, `current_step`, `selections`, `validation_history`
  - Update methods: `update_step()`, `update_selections()`, `mark_completed()`
- **`WizardAction`**: Action with `action_type`, `target_step`, `context`
  - `to_ui_action_target()`: Maps to UI governance targets
- **`WizardActionDecision`**: Validation result with `reason_code`, `explanation`, `severity`
- **`WizardResult`**: Completion result with statistics and metadata

#### Wizard Types:
- `WizardType.RUN_JOB`: 14-step workflow for job creation
- `WizardType.GATE_FIX`: 12-step workflow for gate fixing

### 2. ViewModel Layer (Phase 2)
**Location**: `src/gui/services/wizard/`

#### Core Components:
- **`WizardViewModel`**: 600+ lines of business logic
  - 20+ action handlers for different `WizardActionType`
  - Zero-silent validation integration with UI governance v1.7
  - State management with immutable updates
- **`WizardStepValidator`**: Abstract base for step validation
  - `RunJobStepValidator`: 14-step validation rules
  - `GateFixStepValidator`: 12-step validation rules
- **`WizardActionExecutor`**: Action execution with error handling
  - Batch execution support
  - Statistics tracking

### 3. UI Shell (Phase 3)
**Location**: `src/gui/desktop/wizard/`

#### Core Components:
- **`WizardDialog`**: QDialog with QStackedWidget
  - Step management with navigation
  - Integration with ViewModel
- **`WizardStepWidget`**: Base class for step widgets
  - 7 concrete implementations for different step types
- **`WizardNavigationBar`**: Next/Previous/Cancel buttons
  - Zero-silent validation display
- **`WizardValidationBanner`**: Shows validation errors and explanations

### 4. Integration Layer (Phase 4)
**Location**: `src/gui/services/wizard/wizard_launcher.py`

#### Core Components:
- **`WizardLauncherService`**: Singleton service for wizard management
  - `launch_run_job_wizard()`: Guided job creation
  - `launch_gate_fix_wizard()`: Gate failure fixing
  - Signal-based completion/cancellation handling
- **Integration Points**:
  - ActionRouterService for UI action routing
  - UI governance state v1.7 for action validation
  - Supervisor client for job submission
  - Gate summary service for gate data

## Zero-Silent Validation

### Principle
Every blocked UI action must provide:
1. **`reason_code`**: Machine-readable code (e.g., `NO_STRATEGY_SELECTED`)
2. **`explanation`**: Human-readable explanation from v1.4 dictionary
3. **`severity`**: `INFO`, `WARNING`, `BLOCKING`, `ERROR`
4. **`recommended_action`**: What the user should do next

### Implementation
```python
# Example validation in WizardAction validation
if not wizard_state.selections.strategy_ids:
    return WizardActionDecision.blocked(
        reason_code="NO_STRATEGY_SELECTED",
        message="No strategy selected",
        severity=ValidationSeverity.BLOCKING,
        recommended_action="Select at least one strategy",
    )
```

## UI Governance Integration

### v1.7 State Integration
The wizard engine reuses the existing UI governance state:
- **Action validation**: `validate_action_for_target()` checks if wizard actions are enabled
- **State awareness**: Wizard actions respect UI state (e.g., job submission disabled during maintenance)
- **Policy enforcement**: UI action policies apply to wizard workflows

### Action Mapping
Wizard actions map to UI action targets:
- `WizardActionType.SUBMIT_JOB` → `"wizard://job_submit"`
- `WizardActionType.APPLY_FIX` → `"wizard://gate_fix_apply"`
- `WizardActionType.SHOW_EXPLANATION` → `"wizard://explain_view"`

## Run Job Wizard Workflow

### 14-Step Sequence
1. **WIZARD_START** → Initialize wizard
2. **SELECT_STRATEGY** → Choose strategy(ies)
3. **SELECT_TIMEFRAME** → Choose timeframe
4. **SELECT_INSTRUMENT** → Choose instrument(s)
5. **SELECT_MODE** → Choose run mode
6. **VALIDATE_STEP** → Validate selections
7. **CONFIRM_SELECTIONS** → User confirmation
8. **SUBMIT_JOB** → Submit job to supervisor
9. **FETCH_JOB_STATUS** → Monitor job status
10. **FETCH_GATE_SUMMARY** → Get gate results
11. **SHOW_EXPLANATION** → Explain gate results
12. **SHOW_RECOMMENDATIONS** → Show recommendations
13. **VALIDATE_COMPLETION** → Final validation
14. **WIZARD_COMPLETE** → Finish wizard

## Gate Fix Wizard Workflow

### 12-Step Sequence
1. **WIZARD_START** → Initialize wizard
2. **SELECT_JOB** → Choose job with gate failures
3. **SELECT_GATE** → Choose specific gate to fix
4. **SHOW_EXPLANATION** → Explain gate failure
5. **SHOW_RECOMMENDATIONS** → Show fix recommendations
6. **SELECT_FIX** → Choose fix type
7. **VALIDATE_STEP** → Validate fix selection
8. **APPLY_FIX** → Apply the fix
9. **VERIFY_FIX** → Verify fix application
10. **FETCH_GATE_SUMMARY** → Get updated gate results
11. **VALIDATE_COMPLETION** → Final validation
12. **WIZARD_COMPLETE** → Finish wizard

## Integration with Existing Components

### 1. OP Tab Integration
- Reuses card components from OP tab
- Integrates with ActionRouterService for navigation
- Uses existing supervisor client for job submission

### 2. Gate Summary Service
- Uses `ConsolidatedGateSummaryService` for gate data
- Integrates with `GateReasonCardsRegistry` for explanations
- Reuses `CrossJobGateSummaryService` for multi-job analysis

### 3. Explain Dictionary (v1.4)
- All `reason_code` values map to v1.4 explain dictionary
- Explanations are fetched from centralized dictionary
- Consistent explanation patterns across UI

## Error Handling

### Graceful Degradation
1. **Network failures**: Retry with exponential backoff
2. **Validation failures**: Show explanation with recommended action
3. **State corruption**: Reset wizard with user confirmation
4. **UI component failures**: Fallback to basic components

### Statistics Tracking
- Execution time per step
- Validation success/failure rates
- User interaction patterns
- Completion rates by wizard type

## Testing Strategy

### Governance Locks
1. **Contract tests**: Verify frozen models cannot be mutated
2. **Validation tests**: Test all reason_code → explain mappings
3. **Integration tests**: Test wizard → UI governance integration
4. **E2E tests**: Complete wizard workflows

### Test Coverage
- **100%** of reason_code mappings
- **100%** of step transitions
- **100%** of action validations
- **90%+** of business logic

## Performance Considerations

### State Management
- Immutable state for predictable updates
- Efficient diffing for UI updates
- Lazy loading of step widgets

### Memory Usage
- Wizard state: ~1KB per wizard
- Step widgets: Loaded on demand
- Validation history: Limited to last 100 validations

### Responsiveness
- Non-blocking action execution
- Async job submission and status checking
- Progressive loading of explanations

## Deployment Plan

### Phase 1: Core Contracts
- ✅ **Completed**: SSOT wizard contracts
- ✅ **Completed**: Frozen Pydantic models
- ✅ **Completed**: Zero-silent validation framework

### Phase 2: Business Logic
- ✅ **Completed**: Wizard ViewModel
- ✅ **Completed**: Step validators
- ✅ **Completed**: Action executor

### Phase 3: UI Components
- ✅ **Completed**: Wizard UI shell structure
- 🔄 **In Progress**: Step widget implementations
- 🔄 **In Progress**: Navigation components

### Phase 4: Integration
- ✅ **Completed**: Wizard launcher service
- 🔄 **In Progress**: ActionRouterService integration
- 🔄 **In Progress**: UI governance integration

### Phase 5: Testing
- 🔄 **In Progress**: Governance lock tests
- 🔄 **In Progress**: Integration tests
- 🔄 **In Progress**: E2E tests

## Future Enhancements

### v1.9 Planned Features
1. **Wizard templates**: Save and reuse wizard configurations
2. **Batch wizards**: Run multiple jobs in sequence
3. **Advanced validation**: Cross-field validation rules
4. **Custom steps**: Plugin system for custom wizard steps

### v2.0 Roadmap
1. **Visual workflow editor**: Drag-and-drop wizard design
2. **AI-assisted steps**: LLM-powered recommendations
3. **Multi-language support**: Internationalization
4. **Accessibility**: WCAG 2.1 compliance

## Conclusion

The UI Wizard Engine v1.8 provides a robust, zero-silent framework for guided workflows that:
1. **Reuses** existing UI governance infrastructure (v1.7)
2. **Integrates** with explain dictionary (v1.4)
3. **Provides** consistent user experience across workflows
4. **Ensures** no silent failures with comprehensive validation

The architecture follows SSOT principles with clear separation between contracts, business logic, and UI components, enabling maintainable evolution and reliable operation.