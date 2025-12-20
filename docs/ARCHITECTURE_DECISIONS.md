# FishBroWFS_V2 – Architecture Decisions

This document records non-negotiable architectural decisions
and the reasoning behind them.

---

## ADR-001: Strategy / Engine Separation

**Decision:**
- Strategy describes intent only
- Engine determines execution semantics

**Reason:**
- Prevent strategy authors from accidentally changing fill logic
- Ensure MC-Exact semantic alignment

**Status:** FROZEN

---

## ADR-002: Raw Data Immutability

**Decision:**
- Raw data must not be modified in any way

**Reason:**
- Prevent silent historical distortion
- Ensure fingerprint-based verification

**Status:** FROZEN

---

## ADR-003: Funnel Architecture with OOM Gate

**Decision:**
- Introduce multi-stage funnel
- Enforce OOM Gate before allocation

**Reason:**
- Avoid brute-force backtesting
- Make failure explicit and early

**Status:** FROZEN

---

## ADR-004: Session and DST Handling in Derived Layer Only

**Decision:**
- Session logic and DST conversion exist only in Derived Data

**Reason:**
- Raw layer must remain timezone-agnostic
- Derived transformations must be inspectable and reversible

**Status:** FROZEN

---

## ADR-005: Deterministic Strategy Contract

**Decision:**
- All strategies must be pure functions

**Reason:**
- Enable reproducibility
- Allow safe parameter exploration

**Status:** FROZEN

---

## ADR-006: Portfolio as First-Class Artifact

**Decision:**
- Portfolios are versioned, hashed, and auditable artifacts

**Reason:**
- Enable comparative research
- Prevent configuration drift

**Status:** FROZEN

---

## ADR-007: Artifact-First Governance

**Decision:**
- Artifacts are the source of truth, not logs or UI

**Reason:**
- Long-term inspectability
- Human-readable forensic trail

**Status:** FROZEN

---

## ADR-008: Timezone Database Versioning

**Decision:**
- Record tzdb provider and version in manifest

**Reason:**
- DST rules change over time
- Enable exact reproduction of historical classifications

**Status:** FROZEN

---

## ADR-009: BREAK as Absolute K-Bar Boundary

**Decision:**
- BREAK sessions are absolute boundaries for K-bar aggregation

**Reason:**
- Trading sessions have natural breaks
- K-bars must not cross session boundaries

**Status:** FROZEN

---

## ADR-010: Strategy Registry Explicit Loading

**Decision:**
- Built-in strategies loaded via explicit function call

**Reason:**
- Avoid import side effects
- Enable deterministic registry state

**Status:** FROZEN
