# FishBroWFS_V2 – Architecture Index

This document provides navigation to authoritative documents.
It is not a specification itself.

---

## Core Authority
- **PROJECT_RECORD.md** - Historical timeline and authoritative decisions
- **NON_GOALS.md** - What the system explicitly does NOT do
- **ARCHITECTURE_DECISIONS.md** - ADR (Architecture Decision Records) collection

---

## Engine / Funnel
- **phase0_4/PHASE4_DEFINITION.md** - Engine constitution and MC-Exact semantics
- **phase0_4/STAGE0_FUNNEL.md** - Stage 0 funnel definition
- **phase5_governance/PHASE5_FUNNEL_B2.md** - Funnel architecture (B2)
- **phase5_governance/PHASE5_OOM_GATE_B3.md** - OOM Gate implementation (B3)

---

## Governance / Audit
- **phase5_governance/PHASE5_GOVERNANCE_B4.md** - Governance system (B4)
- **phase5_governance/PHASE5_ARTIFACTS.md** - Artifact system definition
- **phase5_governance/PHASE5_AUDIT.md** - Audit schema and requirements

---

## Data
- **phase6_data/DATA_INGEST_V1.md** - Raw data ingest constitution (Phase 6.5)
- **PROJECT_RECORD.md** (Phase 6.6) - Derived data (Session/DST/K-bar) decisions

---

## Strategy
- **phase7_strategy/STRATEGY_CONTRACT_V1.md** - Strategy contract and rules

---

## Performance
- **perf/PERF_HARNESS.md** - Performance testing harness

---

## How to Use This Index

1. **Starting point**: Read PROJECT_RECORD.md for historical context
2. **Understanding constraints**: Read NON_GOALS.md and ARCHITECTURE_DECISIONS.md
3. **Deep dive**: Follow links to specific phase documents
4. **Implementation**: Refer to code in `src/FishBroWFS_V2/` matching the phase

---

## Document Status

- **FROZEN**: No changes allowed without explicit ADR
- **DONE**: Implementation complete, may have minor updates
- **ACTIVE**: Under development

All documents are authoritative. PROJECT_RECORD.md is the single source of truth for historical decisions.
