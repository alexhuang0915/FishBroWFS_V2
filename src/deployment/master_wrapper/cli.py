#!/usr/bin/env python3
"""
CLI interface for the Titanium Master Wrapper Generator (Phase 4-C).

Usage:
    python -m src.deployment.master_wrapper.cli generate --strategies-dir ./strategies --quarter 2026Q1
"""

import argparse
import sys
from pathlib import Path
from typing import List

from .generator import (
    PowerLanguageStrategy,
    parse_powerlanguage,
    generate_master_wrapper,
    validate_strategy,
)


def load_strategies_from_directory(strategy_dir: Path) -> List[PowerLanguageStrategy]:
    """Load all PowerLanguage strategies from a directory."""
    strategies = []
    
    if not strategy_dir.exists():
        raise FileNotFoundError(f"Strategy directory not found: {strategy_dir}")
    
    # Look for .el or .txt files
    for ext in [".el", ".txt", ".EL", ".TXT"]:
        for file_path in strategy_dir.glob(f"*{ext}"):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    source_code = f.read()
                
                strategy = parse_powerlanguage(source_code, name=file_path.stem)
                is_valid, errors = validate_strategy(strategy)
                
                if is_valid:
                    strategies.append(strategy)
                    print(f"✓ Loaded: {file_path.name}")
                else:
                    print(f"✗ Rejected: {file_path.name} - {errors}")
                    
            except Exception as e:
                print(f"✗ Error loading {file_path.name}: {e}")
    
    if not strategies:
        raise ValueError(f"No valid strategies found in {strategy_dir}")
    
    return strategies


def create_example_strategy() -> str:
    """Create an example PowerLanguage strategy for testing."""
    return """// Example PowerLanguage Strategy
// This is a simple moving average crossover strategy

Inputs:
    i_FastLen(10),
    i_SlowLen(20);

Vars:
    v_FastMA(0),
    v_SlowMA(0),
    v_MP(0);

v_MP = MarketPosition;

// Calculate moving averages
v_FastMA = Average(Close, i_FastLen);
v_SlowMA = Average(Close, i_SlowLen);

// Entry logic
If v_MP = 0 Then Begin
    If v_FastMA > v_SlowMA Then
        Buy Next Bar at Market;
    If v_FastMA < v_SlowMA Then
        SellShort Next Bar at Market;
End;

// Exit logic
If v_MP > 0 Then Begin
    If v_FastMA < v_SlowMA Then
        Sell Next Bar at Market;
End;

If v_MP < 0 Then Begin
    If v_FastMA > v_SlowMA Then
        BuyToCover Next Bar at Market;
End;
"""


def main_generate(args):
    """Handle the generate command."""
    try:
        # Load strategies
        if args.strategies_dir:
            strategies = load_strategies_from_directory(Path(args.strategies_dir))
        else:
            # Use example strategy if no directory provided
            print("No strategy directory provided. Using example strategy.")
            example_code = create_example_strategy()
            strategy = parse_powerlanguage(example_code, name="Example_MA_Crossover")
            strategies = [strategy]
        
        print(f"Loaded {len(strategies)} valid strategies")
        
        # Generate master wrapper
        parts = generate_master_wrapper(
            strategies=strategies,
            quarter=args.quarter,
            deploy_id=args.deploy_id,
            output_dir=Path(args.output_dir) if args.output_dir else None,
        )
        
        print(f"\nSuccessfully generated {len(parts)} Master wrapper part(s):")
        for part in parts:
            print(f"  - {part.part_name} ({len(part.strategies)} strategies, MaxBarsBack={part.max_bars_back})")
        
        print(f"\nOutput directory: {parts[0].part_name.parent if parts else 'N/A'}")
        print("Deployment guide: Deployment_Guide.html")
        
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def main_validate(args):
    """Handle the validate command."""
    try:
        with open(args.file, 'r', encoding='utf-8') as f:
            source_code = f.read()
        
        strategy = parse_powerlanguage(source_code, name=Path(args.file).stem)
        is_valid, errors = validate_strategy(strategy)
        
        if is_valid:
            print(f"✓ Strategy '{strategy.name}' is VALID")
            print(f"  Inputs: {len(strategy.inputs)}")
            print(f"  Vars: {len(strategy.vars)}")
            print(f"  Arrays: {len(strategy.arrays)}")
            print(f"  Max lookback: {strategy.max_lookback}")
        else:
            print(f"✗ Strategy '{strategy.name}' is INVALID")
            for error in errors:
                print(f"  - {error}")
            
        sys.exit(0 if is_valid else 1)
        
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Titanium Master Wrapper Generator (Phase 4-C)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Command to execute")
    
    # Generate command
    gen_parser = subparsers.add_parser("generate", help="Generate Master wrapper")
    gen_parser.add_argument(
        "--strategies-dir",
        type=str,
        help="Directory containing PowerLanguage strategy files (.el, .txt)"
    )
    gen_parser.add_argument(
        "--quarter",
        type=str,
        required=True,
        help="Quarter identifier (e.g., 2026Q1)"
    )
    gen_parser.add_argument(
        "--deploy-id",
        type=str,
        help="Deployment ID (auto-generated if not provided)"
    )
    gen_parser.add_argument(
        "--output-dir",
        type=str,
        help="Output directory (default: outputs/jobs/{deploy_id}/deployments/)"
    )
    gen_parser.set_defaults(func=main_generate)
    
    # Validate command
    val_parser = subparsers.add_parser("validate", help="Validate a PowerLanguage strategy")
    val_parser.add_argument(
        "file",
        type=str,
        help="PowerLanguage strategy file to validate"
    )
    val_parser.set_defaults(func=main_validate)
    
    # Parse arguments
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(1)
    
    args.func(args)


if __name__ == "__main__":
    main()