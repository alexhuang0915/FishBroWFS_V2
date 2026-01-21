# CI Speedup Plan V1

## Objective
Create a fast developer loop by splitting tests into "fast" (logic/contracts) and "gui" (visual/slow) tiers.

## Targets

### `make check-fast`
**Coverage**:
- `tests/contracts/`: All contract tests (Gate, Hygiene, Policy, Hardening).
- `tests/product/`: Core domain logic (Control, Supervisor, etc.), filtered by `not slow and not legacy_ui`.

**Use Case**:
- Pre-commit hook.
- Rapid iteration on backend logic.
- Config validation.

### `make check-gui`
**Coverage**:
- `tests/gui_desktop/`: All UI tests (Headless or Headed).

**Use Case**:
- UI developement.
- Verification of QT logic.

### `make check` (Legacy/Full)
**Coverage**:
- Retains original behavior (Hardening + Product).
- To be maintained as the "Gate" for now.

## Timing Benchmark
*(To be populated on first run)*
