# FishBroWFS_V2 – Non-Goals (Authoritative)

This document defines what FishBroWFS_V2 is **explicitly NOT designed to do**.
Any proposal that violates these non-goals must be rejected.

---

## 1. This is NOT a Trading Platform

FishBroWFS_V2 does NOT:
- Connect to brokers
- Place live orders
- Manage real-time positions
- Handle latency, slippage, or execution routing

Execution belongs to external systems (e.g. MultiCharts, brokers).

---

## 2. This is NOT a Fast Prototyping Sandbox

FishBroWFS_V2 does NOT:
- Allow ad-hoc parameter hacking
- Allow implicit defaults or magic behavior
- Allow silent fallbacks on errors

All behavior must be explicit, deterministic, and auditable.

---

## 3. This is NOT a Data Cleaning Tool

FishBroWFS_V2 does NOT:
- Sort raw data
- Deduplicate timestamps
- Fill missing values
- Guess timezones

Raw data is treated as immutable historical evidence.

---

## 4. This is NOT an Indicator Playground

FishBroWFS_V2 does NOT:
- Optimize indicator internals for visual smoothness
- Adjust formulas for better backtest results
- Tweak definitions to "look nicer"

Indicators are defined to match external reference systems exactly.

---

## 5. This is NOT a Machine Learning Platform

FishBroWFS_V2 does NOT:
- Train models
- Perform feature selection automatically
- Use probabilistic inference
- Apply adaptive online learning

Any ML-style logic must live outside this system.

---

## 6. This is NOT a GUI-First System

FishBroWFS_V2 does NOT:
- Prioritize UI convenience over correctness
- Hide system state behind dashboards
- Allow actions without audit trails

The system is CLI-first, artifact-first, audit-first.

---

## 7. This is NOT a Performance-At-All-Costs Engine

FishBroWFS_V2 does NOT:
- Sacrifice correctness for speed
- Apply unsafe micro-optimizations
- Introduce hidden caches or mutable globals

Performance improvements must be measurable and reversible.

---

## Final Rule

If a change makes the system:
- Less deterministic
- Less auditable
- Less explainable to your future self

Then it violates the core mission and must not be merged.
