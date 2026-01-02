# FishBroWFS Portfolio Governance Constitution
**Version: 1.0**
**Status: Ratified**
**Scope: Capital Survival Layer**

---

### PREAMBLE: ENGINEERING STATE DISCLOSURE

This Constitution is enacted under the following acknowledged condition:

- The Stage 2 Kernel is currently undergoing **Phase 8 Engineering Repair**
  due to a verified Zero-Trade defect discovered during P2 Precision Governance.
- Portfolio Governance defined herein **does not assume kernel correctness**.
- The purpose of this Constitution is to govern capital allocation,
  risk containment, and lifecycle control regardless of signal source quality.

This separation is intentional and non-negotiable.

---

### ARTICLE I — PHILOSOPHY

1. Research is the process of discovering what might work.
2. Governance is the process of ensuring nothing can destroy the system.
3. A Portfolio exists to **survive regimes**, not to maximize backtest returns.
4. No strategy is trusted; all strategies are disposable.
5. Capital preservation has priority over opportunity capture.

---

### ARTICLE II — THE STRATEGY UNIT (THE ATOM)

1. A Strategy is treated as a **Black Box Contract**.

2. Inputs:
   - Market Data
   - Execution Context
   - Configuration Parameters (Frozen at admission)

3. Outputs (Required Interface):
   - Signal ∈ [-1.0, +1.0]
   - Volatility (annualized or equivalent risk metric)
   - Metadata (regime tags, diagnostics)

4. Immutability Rule:
   - Once a strategy enters `CANDIDATE` state,
     the tuple `(StrategyID, VersionHash)` is **FROZEN**.
   - Any change creates a **new strategy**.

---

### ARTICLE III — LIFECYCLE STATE MACHINE

A strategy MUST exist in exactly one of the following states:

1. INCUBATION  
   - Research phase (WFS Stage 0–3)
   - Parameters mutable
   - No capital relevance

2. CANDIDATE  
   - Passed WFS Plateau validation
   - Parameters frozen
   - Awaiting Portfolio admission

3. PAPER_TRADING  
   - Live data, no capital
   - Signal integrity verification only

4. LIVE  
   - Allocated real capital
   - Subject to all kill-switches

5. PROBATION
   - Triggered when Drawdown > 0.5 × Historical MaxDD
   - Exposure reduced

6. FREEZE
   - Halted by governance intervention
   - No new positions, existing positions held
   - Awaiting manual review or automated demotion

7. RETIRED
   - Triggered when Drawdown > MaxDD
     OR structural failure detected
   - Permanent death
   - No resurrection

---

### ARTICLE IV — PORTFOLIO ADMISSION & CONSTRUCTION

1. Non-Correlation Mandate:
   - A strategy MUST NOT enter LIVE
     if its rolling 30-day correlation with the existing portfolio > 0.7
   - Exception:
     - Replacement Mode (explicitly declared superior successor)

2. Regime Buckets:
   - Portfolio is partitioned into regime buckets
     (e.g., Trend, Mean Reversion, Carry, Volatility)
   - New strategies must:
     - Fill an empty bucket, OR
     - Reduce concentration in an existing bucket

3. Risk Budgeting:
   - Capital allocation is risk-based, not capital-based
   - Allocation rule:
     Allocation_i ∝ TargetVol / σ_i
   - No equal-weighting allowed

---

### ARTICLE V — EXECUTION INTEGRITY (KILL-SWITCHES)

1. Strategy Kill-Switch:
   - Immediate liquidation if:
     Drawdown > 1.2 × Historical MaxDD

2. Portfolio Circuit Breaker:
   - If Portfolio Drawdown > 15%:
     - Halt all new entries
     - Reduce all exposures by 50%

3. Zero Discretion Rule:
   - Algorithms enforce the law
   - Manual action permitted ONLY for emergency halt

---

### ARTICLE VI — DATA & AUDITABILITY

1. Separation of Church and State:
   - Strategy State and Portfolio State MUST be stored independently

2. Daily Snapshot Requirement:
   - A `PortfolioSnapshot` MUST be recorded daily
   - Snapshot includes:
     - Positions
     - Exposure
     - Risk metrics
     - Lifecycle states

3. Auditability:
   - Historical snapshots are immutable
   - No backfill or rewrite permitted

---

### CLOSING STATEMENT

This Constitution exists to prevent self-deception.
Profit is optional.
Survival is mandatory.