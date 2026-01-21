# FishBroWFS System Mental Model

> **"RAW is Fact, Feature is Viewpoint, Strategy is Hypothesis, Research is Verification, Artifacts are Evidence, Decision is Action."**

This document outlines the high-level operational logic of the FishBroWFS system. It serves as the "Constitution" for architectural decisions, ensuring strict separation of concerns from data ingestion to trade execution.

## 0️⃣ RAW ( The Immutable Fact Layer)
**"What happened in the market at that moment?"**

*   **Content**: Tick / Minute / Daily market data (Price, Volume, Time).
*   **Nature**: Pure fact. No logic, no strategy assumptions.
*   **Constraints**:
    *   **Immutable**: Never overwritten.
    *   **Logic-Free**: Contains no derived data or opinions.
    *   **Foundation**: If RAW is flawed, the entire system is invalid.

## 1️⃣ Data Prepare (The Data Engineering Layer)
**"Make RAW calculable."**

*   **Action**: Alignment, gap filling, formatting.
*   **Nature**: Data Engineering, not Research.
*   **Constraints**:
    *   **No Judgment**: Does not filter the market or select "good" data.
    *   **No Alpha**: No strategy logic or edge injection.
    *   **Sanitization Only**: Produces clean bars/arrays/parquet for downstream consumption.

## 2️⃣ Feature Registry (The Worldview Layer)
**" How we allow the system to view the market."**

*   **Content**: Fixed window universes, fixed feature families.
*   **Nature**: Static Registry of Viewpoints.
*   **Constraints**:
    *   **Static**: Pre-defined and registered.
    *   **Calculable**: Deterministic computation.
    *   **Opinion-Free**: Defines *how* to look, not *what* is good.

## 3️⃣ Strategy Registry (The Hypothesis Layer)
**" The Trading Hypothesis."**

*   **Content**: Combinations of features to form trading logic (e.g., "If A > B, buy").
*   **Nature**: A verifiable proposition.
*   **Constraints**:
    *   **Hypothetical**: No guarantee of profit.
    *   **Context-Free**: The strategy doesn't validity itself; it just defines the rules.
    *   **No Risk Model**: Does not know about capital or risk preference.

## 4️⃣ WFS / Research (The Verification Lab)
**" Does this hypothesis hold up in history?"**

*   **Action**: Parameter space scanning, backtesting, performance collection.
*   **Output**: Terrain maps (Heatmaps, Plateaus, Robustness), not just a single "best parameter".
*   **Optimization**: Search for "Plateaus" (stable regions), not peaks.
*   **Nature**: Scientific Experimentation.

## 5️⃣ Artifacts (The Audit Evidence Layer)
**" The Legal Record."**

*   **Content**: Immutable record of a specific run (Commit + Data + Config -> Result).
*   **Includes**: Research results, parameter distributions, scores, verdicts.
*   **Constraints**:
    *   **Immutable**: Once written, never changed.
    *   **Red Team Source**: The only source of truth for audits and risk control.
    *   **Read-Only**: UI consumes this, never modifies it.
    *   *(Maps to `outputs/artifacts/`)*

## 6️⃣ Strategy Selection (The Verdict Layer)
**" To trade or not to trade?"**

*   **Action**: Human or Governance protocols applying criteria to Evidence.
*   **Decisions**: Selection of specific parameter sets (Main/Backup), defining plateau boundaries.
*   **Nature**: Judgment / Ruling.
*   **Output**: Approved Strategy Settings with explicit reasoning.

## 7️⃣ Export / Deployment (The Action Layer)
**" Execution."**

*   **Action**: Generating deliverables for production (MultiCharts code, PDF reports, Deployment packages).
*   **Constraints**:
    *   **Derived Only**: Must come strictly from Artifacts.
    *   **No Feedback**: Cannot alter the Research or Strategy layers.
    *   **Reproducible**: Can be regenerated at any time from Artifacts.
    *   *(Maps to `outputs/exports/`)*

---

## The Convergence (Outputs Restructuring)
The system directory structure reflects this flow:
*   **Runtime (`outputs/runtime/`)**: The engine room for Layer 4 (Research/WFS).
*   **Artifacts (`outputs/artifacts/`)**: The storage for Layer 5 (Evidence).
*   **Exports (`outputs/exports/`)**: The factory for Layer 7 (Actions).
*   **Legacy (`outputs/legacy/`)**: Historical data that predates this constitution.
