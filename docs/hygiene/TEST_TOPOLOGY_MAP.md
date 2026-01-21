# Test Topology Map

## 1. Policy & Governance (CRITICAL - MUST KEEP)
**Role**: Enforces system constraints, immutability, and safety.
**Directory Patterns**:
- `tests/governance/`: Batch immutability, metadata validation.
- `tests/policy/`: Policy enforcement logic.
- `tests/gate/`: Build gates, release gates.
- `tests/hardening/`: Security, integrity, and stress tests.
- `tests/hygiene/`: Import restrictions, root hygiene.
**Examples**: `test_phase14_governance.py`, `test_root_hygiene_guard.py`.

## 2. Product Core (Product)
**Role**: Validates core business logic and engine mechanics.
**Directory Patterns**:
- `tests/control/`: Supervisor, job lifecycle, state management.
- `tests/core/`: Data structures, contracts.
- `tests/engine/`: (If exists) Trading engine logic.
- `tests/portfolio/`: Portfolio construction and validation.
- `tests/strategy/`: Strategy implementation logic.
- `tests/contracts/`: System-wide contracts.
**Examples**: `test_portfolio_validate.py`, `test_supervisor_db_contract_v1.py`.

## 3. UI System (Product)
**Role**: Desktop application tests.
**Directory Patterns**:
- `tests/gui_desktop/`: Tests for the Qt Desktop application (Control Station).
- `tests/gui_services/`: Backend services for the UI.
**Examples**: `test_desktop_auto_starts_supervisor.py`.

## 4. Unclassified / Potential Legacy (Candidates)
**Role**: Tests that may refer to obsolete components or old structures.
**Directory Patterns**:
- `tests/gui/`: Check if this overlaps with `tests/gui_desktop`.
- `tests/*.py`: Top-level tests should ideally be categorized.
    - `test_artifact_contract.py`
    - `test_audit_schema_contract.py`
    - `test_s1_pass.py` (Script wrapper?)
**Examples**: `test_b5_query_params.py` (What is b5?), `test_s1_error.py`.

## 5. Deployment & Data
**Role**: Deployment scripts and data ingestion.
**Directory Patterns**:
- `tests/deployment/`
- `tests/data/`
