#!/usr/bin/env python3
"""
Demonstration script for Phase 4-C Titanium Master Wrapper Generator.

This script shows how to use the generator with example strategies.
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from deployment.master_wrapper.generator import (
    parse_powerlanguage,
    validate_strategy,
    generate_master_wrapper,
)


def demonstrate_validation():
    """Demonstrate strategy validation."""
    print("=== Strategy Validation Demo ===")
    
    # Valid strategy
    valid_code = """Inputs: i_Len(20); Vars: v_MA(0); v_MA = Average(Close, i_Len);
    If MarketPosition = 0 and Close > v_MA Then Buy Next Bar at Market;"""
    
    strategy = parse_powerlanguage(valid_code, "ValidStrategy")
    is_valid, errors = validate_strategy(strategy)
    
    print(f"Valid Strategy: {is_valid}")
    if errors:
        print(f"Errors: {errors}")
    
    # Invalid strategy with SetStopLoss
    invalid_code = """Inputs: i_Len(20); Vars: v_MA(0); v_MA = Average(Close, i_Len);
    If MarketPosition = 0 and Close > v_MA Then Buy Next Bar at Market;
    SetStopLoss(100);"""
    
    strategy = parse_powerlanguage(invalid_code, "InvalidStrategy")
    is_valid, errors = validate_strategy(strategy)
    
    print(f"\nInvalid Strategy (with SetStopLoss): {is_valid}")
    if errors:
        print(f"Errors: {errors}")
    
    print()


def demonstrate_generation():
    """Demonstrate Master wrapper generation."""
    print("=== Master Wrapper Generation Demo ===")
    
    # Create example strategies
    strategies = []
    
    # Strategy 1: MA Crossover
    ma_code = """Inputs: i_Fast(10), i_Slow(20);
    Vars: v_Fast(0), v_Slow(0), v_MP(0);
    v_MP = MarketPosition;
    v_Fast = Average(Close, i_Fast);
    v_Slow = Average(Close, i_Slow);
    If v_MP = 0 and v_Fast > v_Slow Then Buy Next Bar at Market;
    If v_MP > 0 and v_Fast < v_Slow Then Sell Next Bar at Market;"""
    
    strategies.append(parse_powerlanguage(ma_code, "MA_Crossover"))
    
    # Strategy 2: Breakout
    breakout_code = """Inputs: i_Len(20);
    Vars: v_High(0), v_MP(0);
    v_MP = MarketPosition;
    v_High = Highest(High, i_Len);
    If v_MP = 0 and Close > v_High Then Buy Next Bar at Market;
    If v_MP > 0 and Close < v_High Then Sell Next Bar at Market;"""
    
    strategies.append(parse_powerlanguage(breakout_code, "Breakout"))
    
    # Strategy 3: RSI Mean Reversion
    rsi_code = """Inputs: i_RSILen(14);
    Vars: v_RSI(0), v_MP(0);
    v_MP = MarketPosition;
    v_RSI = RSI(Close, i_RSILen);
    If v_MP = 0 and v_RSI < 30 Then Buy Next Bar at Market;
    If v_MP > 0 and v_RSI > 70 Then Sell Next Bar at Market;"""
    
    strategies.append(parse_powerlanguage(rsi_code, "RSI_MeanReversion"))
    
    print(f"Loaded {len(strategies)} strategies:")
    for i, s in enumerate(strategies, 1):
        is_valid, errors = validate_strategy(s)
        status = "✓" if is_valid else "✗"
        print(f"  {status} Strategy {i}: {s.name}")
    
    # Generate Master wrapper
    print("\nGenerating Master wrapper...")
    
    try:
        parts = generate_master_wrapper(
            strategies=strategies,
            quarter="2026Q1",
            deploy_id="demo_001",
            output_dir=Path("outputs/deployments/demo_001"),
        )
        
        print(f"Successfully generated {len(parts)} part(s):")
        for part in parts:
            print(f"  - {part.part_name} ({len(part.strategies)} strategies)")
        
        # Show snippet of generated code
        if parts:
            part = parts[0]
            print(f"\nSample of generated code (first 30 lines):")
            lines = part.source_code.split('\n')[:30]
            for i, line in enumerate(lines, 1):
                print(f"{i:3}: {line}")
        
        print(f"\nOutput directory: outputs/deployments/demo_001/")
        print("Deployment guide: outputs/deployments/demo_001/Deployment_Guide.html")
        
    except Exception as e:
        print(f"Error during generation: {e}")
        import traceback
        traceback.print_exc()


def demonstrate_namespace_isolation():
    """Demonstrate namespace isolation."""
    print("\n=== Namespace Isolation Demo ===")
    
    from deployment.master_wrapper.generator import isolate_namespace
    
    # Simple strategy with variables
    code = """Vars: myVar(10), myArray[20];
    myVar = myVar + 1;
    If myVar > 15 Then Buy Next Bar at Market;"""
    
    strategy = parse_powerlanguage(code, "TestStrategy")
    strategy.vars = {"myVar": "10"}
    strategy.arrays = {"myArray": "20"}
    strategy.logic_blocks = ["myVar = myVar + 1;", "If myVar > 15 Then Buy Next Bar at Market;"]
    
    print("Original strategy variables:")
    for var in strategy.vars:
        print(f"  - {var}")
    
    # Apply namespace isolation
    isolated = isolate_namespace(strategy, 5)  # Strategy ID 5
    
    print("\nAfter namespace isolation (Strategy ID 5):")
    for var in isolated.vars:
        print(f"  - {var}")
    
    print("\nIsolated logic:")
    for block in isolated.logic_blocks:
        print(f"  {block}")


if __name__ == "__main__":
    print("Phase 4-C: Titanium Master Wrapper Generator Demo")
    print("=" * 60)
    
    demonstrate_validation()
    demonstrate_namespace_isolation()
    demonstrate_generation()
    
    print("\n" + "=" * 60)
    print("Demo completed successfully!")
    print("\nTo run the full CLI:")
    print("  python -m src.deployment.master_wrapper.cli generate --strategies-dir examples/strategies --quarter 2026Q1")
    print("\nTo validate a strategy:")
    print("  python -m src.deployment.master_wrapper.cli validate examples/strategies/ma_crossover.el")