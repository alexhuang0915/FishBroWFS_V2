# Phase 4-C: Titanium Master Deployment - Switch-Case Master Wrapper Generator

## Overview

This module implements the Phase 4-C requirement: a generator that merges multiple standalone PowerLanguage strategies into a single Master .el file controlled by `i_Strategy_ID` and `i_Lots` inputs. The resulting Master file allows manual but ultra-safe deployment into MultiCharts Portfolio Trader.

## Key Features

1. **AST-Level Transformation**: Parses PowerLanguage strategies, hoists variables/inputs, and applies namespace isolation
2. **Strict Validation**: Rejects strategies with forbidden constructs (Set* syntax, IOG=True, File/DLL operations, etc.)
3. **Automatic Splitting**: Automatically splits into multiple parts when exceeding 50 strategies per file
4. **Namespace Isolation**: Suffixes all strategy-specific identifiers with `_S{id}` to prevent collisions
5. **MaxBarsBack Calculation**: Computes appropriate MaxBarsBack value based on strategy lookbacks
6. **Deployment Guide**: Generates comprehensive HTML deployment guide with strategy assignment table

## Architecture

### Core Components

1. **`PowerLanguageStrategy`**: Data class representing a parsed PowerLanguage strategy
2. **`MasterWrapperGenerator`**: Main generator class that orchestrates the transformation
3. **`MasterWrapperConfig`**: Configuration for generation (quarter, deploy_id, strategies, etc.)
4. **`GeneratedPart`**: Represents a generated Master wrapper part file

### Processing Pipeline

1. **Parse**: Extract inputs, vars, arrays, and logic blocks from PowerLanguage source
2. **Validate**: Check for forbidden constructs and ensure compliance with Phase 4-C constraints
3. **Isolate**: Apply namespace isolation by suffixing identifiers
4. **Hoist**: Collect all declarations into Master Vars section
5. **Generate**: Create Master wrapper with switch-case logic based on `i_Strategy_ID`
6. **Write**: Output files to `outputs/deployments/{DEPLOY_ID}/`

## Constraints (Non-Negotiable)

### Absolute Prohibitions
- ❌ NO `Set*` PowerLanguage syntax (SetStopLoss, SetProfitTarget, SetBreakEven, SetTrailingStop, etc.)
- ❌ NO IOG = True (Bar Close semantics only)
- ❌ NO intrabar logic
- ❌ NO File IO, DLL calls, Plot, Text Drawing, Alert
- ❌ NO `#include` directives
- ❌ NO custom functions/methods

### Allowed Constructs
- ✅ Explicit orders only: `Buy`, `Sell`, `SellShort`, `BuyToCover` with `Next Bar at Market/Stop`
- ✅ Standard indicators: `Average`, `Highest`, `Lowest`, `RSI`, `ATR`, etc.
- ✅ Control flow: `If/Then/Begin/End`, `For` loops
- ✅ Variables, Arrays, IntrabarPersist

## Usage

### Command Line Interface

```bash
# Generate Master wrapper from strategies directory
python -m src.deployment.master_wrapper.cli generate \
    --strategies-dir ./examples/strategies \
    --quarter 2026Q1 \
    --deploy-id my_deployment_001

# Validate a single strategy file
python -m src.deployment.master_wrapper.cli validate ./examples/strategies/ma_crossover.el
```

### Python API

```python
from src.deployment.master_wrapper.generator import (
    parse_powerlanguage,
    generate_master_wrapper,
)

# Parse strategies
strategies = []
with open("strategy.el", "r") as f:
    source = f.read()
    strategy = parse_powerlanguage(source, name="MyStrategy")
    strategies.append(strategy)

# Generate Master wrapper
parts = generate_master_wrapper(
    strategies=strategies,
    quarter="2026Q1",
    deploy_id="custom_id_123",
    output_dir=Path("outputs/deployments/custom_id_123"),
)
```

## Output Artifacts

Generated in `outputs/deployments/{DEPLOY_ID}/`:

1. **`Titanium_Master_{Quarter}_Part{X}.txt`**: Master PowerLanguage file(s)
   - Contains all strategies wrapped in switch-case logic
   - Controlled by `i_Strategy_ID` and `i_Lots` inputs
   - Includes proper `SetMaxBarsBack` declaration

2. **`Deployment_Guide.html`**: Comprehensive deployment guide
   - Strategy assignment table (Part, Strategy_ID, Symbol, Timeframe, etc.)
   - Deployment instructions
   - Logic hashes for verification

## Example Master Wrapper Structure

```easylanguage
// ========================================
// Titanium Master Deployment
// Quarter: 2026Q1
// Part: A
// Generator Version: 1.0.0
// Deploy Hash: abcd1234
// ========================================

SetMaxBarsBack(150);

Inputs:
    i_Strategy_ID(0),
    i_Lots(1);

Vars:
    // --- Strategy 01 Vars ---
    i_FastMA_S01(10),
    i_SlowMA_S01(20),
    v_Fast_S01(0),
    v_Slow_S01(0),
    
    // --- Strategy 02 Vars ---
    i_ChannelLen_S02(20),
    v_HighChannel_S02(0),
    
    // --- Shared ---
    v_MP(0);

v_MP = MarketPosition;

If i_Strategy_ID = 1 Then Begin
    // Strategy 01 logic with renamed variables
    v_Fast_S01 = Average(Close, i_FastMA_S01);
    v_Slow_S01 = Average(Close, i_SlowMA_S01);
    // ... rest of strategy 01 logic
End
Else If i_Strategy_ID = 2 Then Begin
    // Strategy 02 logic with renamed variables
    v_HighChannel_S02 = Highest(High, i_ChannelLen_S02);
    // ... rest of strategy 02 logic
End
Else Begin
    // Safety no-op
End;
```

## Validation Rules

The generator performs strict validation:

1. **Set* Syntax Detection**: Any occurrence of `SetStopLoss`, `SetProfitTarget`, etc. causes rejection
2. **IOG Check**: `IOG = True` or `IntraBarOrderGeneration = True` causes rejection
3. **Forbidden Constructs**: File, DLL, Plot, Alert, Text, PaintBar, #include cause rejection
4. **Explicit Orders Required**: Must contain at least one allowed order syntax pattern
5. **No Intrabar Logic**: Intrabar constructs are rejected

## Testing

Run the test suite:

```bash
pytest tests/deployment/test_master_wrapper.py -v
```

Test coverage includes:
- Strategy parsing and validation
- Namespace isolation
- Master wrapper generation
- Automatic splitting for >50 strategies
- Error handling for invalid strategies

## Integration with Existing Pipeline

The Phase 4-C generator is designed to integrate with the existing FishBroWFS_V2 deployment pipeline:

1. **Input**: Frozen Season Manifest or portfolio compilation output
2. **Processing**: Generate Master wrapper for selected strategies
3. **Output**: Deployment package ready for MultiCharts Portfolio Trader
4. **Verification**: Evidence logs written to `outputs/_dp_evidence/`

## Compliance with Phase 4-C Requirements

✅ **ADR-4C-STOP-001 (LOCKED)**: Never uses any Set* PowerLanguage syntax  
✅ **IOG = False only**: Bar Close semantics enforced  
✅ **Explicit orders only**: Buy/Sell/SellShort/BuyToCover with Next Bar at Market/Stop  
✅ **No File IO, DLL, Plot, Text Drawing**  
✅ **Max 50 strategies per Master file**: Auto-splits if exceeded  
✅ **Namespace isolation**: Suffix renaming (_S{id}) for all strategy-specific identifiers  
✅ **Variable hoisting**: All declarations moved to Master Vars section  
✅ **MaxBarsBack calculation**: Based on strategy lookbacks + buffer  
✅ **Output to allowed directories**: `outputs/deployments/{DEPLOY_ID}/` only  
✅ **Deployment guide generation**: HTML with strategy assignment table  

## Limitations

1. **Simplified Parser**: The current parser uses regex patterns rather than a full AST. For production use, a more robust PowerLanguage parser would be needed.
2. **Lookback Estimation**: MaxBarsBack calculation is based on simple pattern matching; a more accurate analysis would require full expression evaluation.
3. **Order Syntax Validation**: Only checks for presence of allowed patterns, not semantic correctness.

## Future Enhancements

1. **Full AST Parser**: Implement a complete PowerLanguage parser for more accurate transformations
2. **Semantic Validation**: Validate order semantics and exit logic preservation
3. **Integration Tests**: Test with real MultiCharts compilation and trade list comparison
4. **Performance Optimization**: Optimize for large numbers of strategies (>1000)
5. **GUI Integration**: Integrate with FishBro Desktop UI for interactive deployment