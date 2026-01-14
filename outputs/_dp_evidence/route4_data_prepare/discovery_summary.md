# Route 4 Discovery Summary

## Existing Data Preparation Infrastructure Found

### 1. **prepare_orchestration.py** (`src/control/prepare_orchestration.py`)
- **Function**: `prepare_with_data2_enforcement()` - Main orchestration function
- **Purpose**: Prepares Data1 and Data2 with dependency enforcement
- **Key Features**:
  - Checks if Data2 feeds have fingerprints/manifests
  - Auto-builds missing Data2 feeds
  - Returns success/failure with detailed reports
  - Includes `check_data2_readiness()` function to check feed status

### 2. **BuildDataHandler** (`src/control/supervisor/handlers/build_data.py`)
- **Job Type**: `BUILD_DATA`
- **Purpose**: Supervisor handler for data preparation jobs
- **Execution Modes**:
  - Via Python function (`prepare_with_data2_enforcement`)
  - Fallback to CLI subprocess
- **Parameters**: `dataset_id`, `timeframe_min`, `force_rebuild`, `mode`

### 3. **Dataset Resolver** (`src/gui/services/dataset_resolver.py`)
- **Class**: `DatasetResolver`
- **Purpose**: Resolves DATA1/DATA2 dataset IDs from strategy/instrument/timeframe/mode
- **Status Detection**: `READY`, `MISSING`, `STALE`, `UNKNOWN`
- **Gate Evaluation**: `evaluate_data2_gate()` implements Option C (AUTO/strategy-dependent)

### 4. **Worker Integration** (`src/gui/desktop/worker.py`)
- **Worker**: Uses `prepare_with_data2_enforcement` for building bars/features cache
- **Purpose**: Background worker for data preparation tasks

### 5. **Shared Build System** (`src/control/shared_build.py`)
- **Functions**: `build_shared()`, `_build_bars_cache()`, `_build_features_cache()`
- **Purpose**: Low-level cache building functions

## Key Insights for Route 4 Implementation

### ✅ Existing Capabilities
1. **Data preparation logic exists** and is functional
2. **Status detection** is already implemented in DatasetResolver
3. **Gate evaluation** follows Option C (AUTO/strategy-dependent)
4. **Supervisor integration** via BUILD_DATA job type
5. **Worker pattern** for background execution

### 🔧 Gaps to Address (Route 4 Scope)
1. **No explicit UI for data preparation** - Users can't trigger prepare actions
2. **No progress reporting** during preparation
3. **No separation between Prepare and Run** in UI
4. **No persistent prepare state** tracking
5. **No Explain Hub integration** for prepare status/actions

### 📋 Implementation Strategy
1. **DataPrepareService**: Wrap existing `prepare_with_data2_enforcement` with Qt signals
2. **UI Integration**: Add prepare panel to Explain Hub (Layer 2)
3. **Gate Enforcement**: Block Run button when required datasets not READY
4. **State Persistence**: Write prepare result artifacts for UI restoration
5. **Testing**: Add service tests and UI behavior tests

### 🎯 Key Integration Points
- Use existing `DatasetResolver` for status detection
- Use existing `prepare_with_data2_enforcement` for preparation logic
- Use existing `BuildDataHandler` via supervisor client
- Extend `DerivedDatasets` model with new statuses: `PREPARING`, `FAILED`

## Next Steps
1. Implement `DataPrepareService` with Qt signals
2. Create UI panel for Explain Hub
3. Update gate enforcement logic
4. Add tests
5. Verify with `make check`