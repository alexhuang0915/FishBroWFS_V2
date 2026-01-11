# qt-guard Workstream Report
## Repo-Level Hardening Tests for Qt/PySide6 + Pydantic-v2 Anti-Patterns

### Overview
Created repo-level hardening tests that fail CI if Qt/PySide6 + Pydantic-v2 anti-patterns appear. These tests enforce modern Qt6 patterns and prevent Pylance red errors by detecting common mistakes that cause type checking failures.

### Anti-Patterns Detected

#### 1. Qt5-Style Enums (130 violations)
**Pattern**: Using flat enums like `Qt.Horizontal`, `Qt.AlignCenter`, `QMessageBox.Ok`
**Required**: Qt6 nested enums like `Qt.Orientation.Horizontal`, `Qt.AlignmentFlag.AlignCenter`, `QMessageBox.StandardButton.Ok`
**Impact**: Pylance cannot resolve flat enums in Qt6, causing red errors and type checking failures.

#### 2. Pydantic default_factory with Class Reference (2 violations)
**Pattern**: `Field(default_factory=ClassName)`
**Required**: `Field(default_factory=lambda: ClassName())`
**Impact**: Pydantic v2 requires callable factories; class references cause runtime errors.

#### 3. Widget Attribute Injection (11 violations)
**Pattern**: Direct attribute assignment like `.job_id = value`, `.season = value`
**Required**: Use `setProperty('job_id', value)` and `property('job_id')`
**Impact**: Dynamic attributes bypass Qt's property system, causing type checking failures.

### Test Implementation

**File**: [`tests/hardening/test_qt_pydantic_pylance_guard.py`](tests/hardening/test_qt_pydantic_pylance_guard.py)

**Test Functions**:
1. `test_no_qt5_enums()` - Fails if Qt5-style enums found
2. `test_no_pydantic_default_factory_class()` - Fails if Pydantic default_factory uses class reference
3. `test_no_widget_attribute_injection()` - Fails if widget attribute injection found
4. `test_guard_summary()` - Combined summary test

**Key Features**:
- Scans all Python files in `src/` directory
- Provides actionable error messages with file paths and line numbers
- Includes fix hints for each violation
- Conservative scanning with allowlists for built-in functions

### Results Summary

| Anti-Pattern | Violations Found | Test Status |
|--------------|------------------|-------------|
| Qt5-style enums | 130 | FAILED (expected) |
| Pydantic default_factory | 2 | FAILED (expected) |
| Widget attribute injection | 11 | FAILED (expected) |

### Safety Impact

1. **CI Blocking**: These tests will fail CI when anti-patterns exist, preventing regression
2. **Type Safety**: Enforces patterns that prevent Pylance red errors
3. **Modern Qt6**: Ensures codebase uses correct Qt6 nested enum patterns
4. **Pydantic v2 Compliance**: Ensures correct default_factory usage

### Integration with Phase 5.1 Safety Gates

The qt-guard workstream complements Phase 5.1 safety gates by:
- Adding repo-level hardening for UI/desktop code
- Preventing type system violations that bypass static analysis
- Enforcing consistent patterns across the codebase

### Evidence Files

1. `00_env.txt` - Environment information
2. `COMMANDS.txt` - Command execution order
3. `PYTEST_OUTPUT.txt` - Test execution output
4. `MAKE_CHECK_OUTPUT.txt` - Full test suite output
5. Discovery files:
   - `discovery_qt5_enums.txt`
   - `discovery_pydantic_default_factory.txt`
   - `discovery_widget_attr_injection.txt`

### Conclusion

The qt-guard hardening tests successfully identify anti-patterns that cause Pylance red errors and type checking failures. By failing CI when these patterns exist, they enforce modern Qt6 and Pydantic v2 practices, improving code quality and developer experience.

**Status**: COMPLETE - Tests are implemented and correctly failing due to existing violations (expected behavior).