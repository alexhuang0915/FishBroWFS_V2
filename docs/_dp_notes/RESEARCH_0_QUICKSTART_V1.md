# Research-0 Quickstart Guide

## Overview

Research-0 is the initial phase of the FishBroWFS research pipeline focused on establishing baseline performance metrics using **No-Flip** (directionally-neutral) feature sets. This phase executes S1, S2, and S3 strategies with configurations that exclude all momentum, trend, and regime-based features, focusing exclusively on structural market characteristics.

**Key Objectives:**
1. Establish baseline performance for non-directional feature sets
2. Validate the research execution pipeline (UI and CLI)
3. Generate comparable artifacts for decision-making
4. Prepare for subsequent research phases

## Available Experiments

Research-0 includes three baseline No-Flip experiments:

| Experiment | Configuration File | Description |
|------------|-------------------|-------------|
| **S1_no_flip** | [`configs/experiments/baseline_no_flip/S1_no_flip.yaml`](../../configs/experiments/baseline_no_flip/S1_no_flip.yaml) | Comprehensive feature baseline using all eligible No-Flip features |
| **S2_no_flip** | [`configs/experiments/baseline_no_flip/S2_no_flip.yaml`](../../configs/experiments/baseline_no_flip/S2_no_flip.yaml) | Pullback continuation adapted to volatility context |
| **S3_no_flip** | [`configs/experiments/baseline_no_flip/S3_no_flip.yaml`](../../configs/experiments/baseline_no_flip/S3_no_flip.yaml) | Extreme reversion using volatility context and channel position |

**Common Characteristics:**
- **Dataset**: CME.MNQ (60-minute timeframe)
- **Season**: 2026Q1 (default)
- **Feature Scope**: Channel, volatility, reversion, and structure features only
- **Exclusions**: No moving averages, momentum indicators, trend indicators, or regime features
- **Build Policy**: `allow_build: false` (requires pre-built feature cache)

## Running via UI (Wizard Page)

The Wizard page is the **only UI-accessible method** for launching Research-0 experiments. The UI is now frozen per the [UI Freeze Policy](UI_FREEZE_POLICY_V1.md), ensuring consistent workflow.

### Step-by-Step Workflow

1. **Access the Wizard**
   - Navigate to the Wizard page in the FishBroWFS application
   - URL: `/wizard` (if running locally)

2. **Quick Launch Section**
   - Locate the "Quick Launch from Experiment YAML" section
   - This section provides direct access to Research-0 experiments

3. **Select Experiment**
   - From the "Experiment YAML" dropdown, select one of:
     - `S1_no_flip.yaml`
     - `S2_no_flip.yaml` 
     - `S3_no_flip.yaml`

4. **Configure Season**
   - Verify/update the "Season" field (default: 2026Q1)
   - This determines the output directory structure

5. **Launch Run**
   - Click the "Launch Run from YAML" button
   - The system will:
     - Validate the YAML configuration
     - Generate a unique run ID
     - Create a run directory with artifacts
     - Return success/failure status

6. **Monitor Execution**
   - Success message includes run ID and directory path
   - Use the "Open run folder" button to inspect artifacts
   - Check the launch log for execution details

### UI Freeze Implications

The UI is **frozen** for Research-0 execution:
- **Visual Consistency**: Layout, styling, and component structure are locked
- **Functional Stability**: Workflow steps and interactions are guaranteed
- **Contract Testing**: All UI changes require test updates per freeze policy
- **Reference**: See [`UI_FREEZE_POLICY_V1.md`](UI_FREEZE_POLICY_V1.md) for details

## Running via CLI

For batch execution or automation, use the command-line interface.

### Basic CLI Execution

```bash
# Run S1 No-Flip experiment
python scripts/run_baseline.py \
  --strategy S1 \
  --config configs/experiments/baseline_no_flip/S1_no_flip.yaml \
  --allow-build False

# Run S2 No-Flip experiment  
python scripts/run_baseline.py \
  --strategy S2 \
  --config configs/experiments/baseline_no_flip/S2_no_flip.yaml \
  --allow-build False

# Run S3 No-Flip experiment
python scripts/run_baseline.py \
  --strategy S3 \
  --config configs/experiments/baseline_no_flip/S3_no_flip.yaml \
  --allow-build False
```

### Batch Execution

```bash
# Run all No-Flip experiments sequentially
for strategy in S1 S2 S3; do
  python scripts/run_baseline.py \
    --strategy $strategy \
    --config configs/experiments/baseline_no_flip/${strategy}_no_flip.yaml \
    --allow-build False
done
```

### CLI Options

| Option | Description | Default |
|--------|-------------|---------|
| `--strategy` | Strategy ID (S1, S2, S3) | **Required** |
| `--config` | Path to experiment YAML | **Required** |
| `--season` | Season identifier | 2026Q1 |
| `--dataset` | Dataset ID | CME.MNQ |
| `--tf` | Timeframe in minutes | 60 |
| `--allow-build` | Allow building missing features | False |

### Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | CLI argument error |
| 2 | Config loading/validation error |
| 3 | Feature cache verification error |
| 4 | Research runner error |

## Artifact Locations and Structure

### Output Directory Hierarchy

```
outputs/seasons/{season}/runs/{run_id}/
├── intent.json          # Original intent specification
├── derived.json         # Derived parameters and metadata
├── run_record.json      # Canonical run record with status
├── launch.log           # Launch timestamp and basic info
└── (future artifacts)   # Results, metrics, etc.
```

### Example Run Path

```
outputs/seasons/2026Q1/runs/run_b3682449/
├── intent.json
├── derived.json  
├── run_record.json
└── launch.log
```

### Artifact Descriptions

1. **`intent.json`**
   - Original experiment specification
   - Contains strategy, dataset, timeframe, and feature requirements
   - Generated from the experiment YAML configuration

2. **`derived.json`**
   - Computed parameters and metadata
   - Includes estimated combinations, risk class, and execution parameters
   - Generated by the derivation service

3. **`run_record.json`**
   - Canonical run record with status tracking
   - Contains version, run_id, season, status, and artifact references
   - Used by the run index service for cataloging

4. **`launch.log`**
   - Timestamp of launch
   - Basic execution information
   - Useful for debugging and auditing

### Verification Checklist

After launching a run, verify:
- ✅ All four artifact files exist in the run directory
- ✅ `run_record.json` has status "CREATED" or "RUNNING"
- ✅ `intent.json` matches the selected experiment configuration
- ✅ No error messages in `launch.log`

## Decision Framework (KEEP/KILL/FREEZE Criteria)

Research-0 outputs feed into a structured decision framework for strategy evaluation.

### Evaluation Dimensions

| Dimension | Description | Measurement |
|-----------|-------------|-------------|
| **Performance** | Risk-adjusted returns | Sharpe ratio, max drawdown, win rate |
| **Robustness** | Consistency across conditions | Regime stability, parameter sensitivity |
| **Feature Utility** | Contribution of non-directional features | Feature importance, signal quality |
| **Operational** | Execution reliability | Success rate, error frequency |

### Decision Categories

#### KEEP (Proceed to Research-1)
- **Criteria**: 
  - Positive risk-adjusted returns (Sharpe > 0.5)
  - Stable across market regimes
  - Non-directional features show predictive value
  - Technical execution successful
- **Action**: Advance to next research phase with expanded feature sets

#### KILL (Terminate Research Line)
- **Criteria**:
  - Negative or negligible performance (Sharpe < 0)
  - High parameter sensitivity or overfitting
  - Technical failures or inconsistent execution
  - Non-directional features show no predictive value
- **Action**: Archive results, document learnings, terminate strategy variant

#### FREEZE (Requires Further Investigation)
- **Criteria**:
  - Mixed or inconclusive results
  - Technical issues requiring resolution
  - Requires additional data or feature validation
  - Borderline performance metrics
- **Action**: Pause research line, conduct targeted investigations, reassess

### Decision Workflow

1. **Collect Artifacts**: Gather all run outputs for the experiment
2. **Extract Metrics**: Compute performance and robustness metrics
3. **Apply Criteria**: Evaluate against KEEP/KILL/FREEZE thresholds
4. **Document Decision**: Record rationale in research log
5. **Execute Action**: Proceed with next phase, termination, or investigation

## Next Steps After Research-0

### Successful Execution (All Experiments)
1. **Review Results**: Analyze performance metrics across S1/S2/S3
2. **Compare Baselines**: Establish directional vs non-directional performance delta
3. **Plan Research-1**: Design expanded feature sets based on findings
4. **Update Documentation**: Incorporate learnings into research blueprint

### Partial Success (Some Experiments)
1. **Diagnose Failures**: Identify root causes of unsuccessful runs
2. **Address Issues**: Fix technical or configuration problems
3. **Re-execute**: Run failed experiments with corrections
4. **Adjust Framework**: Update criteria based on partial results

### Complete Failure (All Experiments)
1. **Root Cause Analysis**: Investigate systemic issues
2. **Pipeline Validation**: Verify feature cache, data availability, execution environment
3. **Remediate**: Address identified issues
4. **Re-attempt**: Execute Research-0 with fixes

## Troubleshooting

### Common Issues and Solutions

| Issue | Symptoms | Resolution |
|-------|----------|------------|
| **Missing Feature Cache** | `RuntimeError: Missing required features in cache` | Ensure features are built: `python scripts/build_features_subset.py` |
| **Invalid YAML** | `yaml.YAMLError` in launch | Validate YAML syntax: `python -m yamllint config.yaml` |
| **Permission Denied** | `PermissionError` when writing outputs | Check directory permissions: `chmod 755 outputs/seasons` |
| **UI Wizard Not Loading** | Blank page or errors | Verify NiceGUI server is running: `python main.py` |
| **Run Directory Not Created** | Launch succeeds but no directory | Check `outputs/seasons/{season}/runs/` for new run_* folder |

### Verification Commands

```bash
# Verify feature cache exists
ls -la outputs/shared/2026Q1/CME.MNQ/features/features_60m.npz

# List recent runs
ls -la outputs/seasons/2026Q1/runs/ | tail -10

# Check run status
python -m src.gui.nicegui.services.run_launcher_service test
```

### Getting Help

1. **Check Logs**: Review `outputs/seasons/{season}/runs/{run_id}/launch.log`
2. **UI Diagnostics**: Use the Forensics page for UI-specific issues
3. **System Diagnostics**: Run `python scripts/ui_forensics_dump.py`
4. **Documentation**: Refer to [`WFS_BLUEPRINT_NO_FLIP_V1.md`](WFS_BLUEPRINT_NO_FLIP_V1.md)

## References

- **No-Flip Blueprint**: [`WFS_BLUEPRINT_NO_FLIP_V1.md`](WFS_BLUEPRINT_NO_FLIP_V1.md)
- **UI Freeze Policy**: [`UI_FREEZE_POLICY_V1.md`](UI_FREEZE_POLICY_V1.md)
- **Strategy Pruning**: [`STRATEGY_PRUNING_POLICY_V1.md`](STRATEGY_PRUNING_POLICY_V1.md)
- **Run Launcher Service**: [`src/gui/nicegui/services/run_launcher_service.py`](../../src/gui/nicegui/services/run_launcher_service.py)
- **Baseline Runner**: [`scripts/run_baseline.py`](../../scripts/run_baseline.py)

---

**Version**: V1 (2025-12-31)  
**Status**: Active  
**Applicability**: Research-0 Phase Only  
**Next Review**: After Research-0 completion