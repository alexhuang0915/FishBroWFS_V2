#!/usr/bin/env python3
"""
Debug script for P2-THETA zero trades issue.
"""
import os
import sys
import numpy as np

# Force object mode
os.environ["FISHBRO_KERNEL_INTENT_MODE"] = "objects"

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.pipeline.stage2_runner import run_stage2
from src.strategy.kernel import _build_entry_intents_from_trigger

def generate_golden_path_data(n_bars=5000):
    """Generate Golden Path synthetic data with explicit step patterns."""
    np.random.seed(42)
    base = 100.0
    noise = np.random.normal(0, 0.5, n_bars)
    
    # Create step pattern
    prices = np.ones(n_bars) * base
    # Step up at bar 1000
    prices[1000:] += 10.0
    # Step down at bar 3000
    prices[3000:] -= 15.0
    
    # Add noise
    prices += np.cumsum(noise) * 0.1
    
    # Ensure strictly positive
    prices = np.abs(prices) + 1.0
    
    # Create OHLC with reasonable spreads
    open_prices = prices
    high_prices = prices + np.random.uniform(0.1, 0.5, n_bars)
    low_prices = prices - np.random.uniform(0.1, 0.5, n_bars)
    close_prices = prices + np.random.normal(0, 0.2, n_bars)
    
    return open_prices, high_prices, low_prices, close_prices

def test_kernel_directly():
    """Test the kernel function directly to see if it produces any intents."""
    print("=== Testing kernel directly ===")
    
    # Generate data
    open_arr, high_arr, low_arr, close_arr = generate_golden_path_data(100)
    
    # Simple parameters
    channel_len = 10
    atr_len = 10
    stop_mult = 2.0
    
    print(f"Data shape: {open_arr.shape}")
    print(f"Parameters: channel={channel_len}, atr={atr_len}, stop={stop_mult}")
    
    # Call kernel function
    try:
        intents = _build_entry_intents_from_trigger(
            open_arr, high_arr, low_arr, close_arr,
            channel_len, atr_len, stop_mult
        )
        print(f"Intents returned: {intents}")
        print(f"Intents shape: {intents.shape if hasattr(intents, 'shape') else 'N/A'}")
        print(f"Intents type: {type(intents)}")
        if hasattr(intents, '__len__'):
            print(f"Number of intents: {len(intents)}")
            if len(intents) > 0:
                print(f"First intent: {intents[0]}")
    except Exception as e:
        print(f"Error calling kernel: {e}")
        import traceback
        traceback.print_exc()

def test_stage2_runner():
    """Test the stage2 runner with minimal parameters."""
    print("\n=== Testing stage2 runner ===")
    
    # Generate data
    open_arr, high_arr, low_arr, close_arr = generate_golden_path_data(500)
    
    # Single parameter set
    params = np.array([[10, 10, 2.0]], dtype=np.float64)
    
    print(f"Data shapes: open={open_arr.shape}, high={high_arr.shape}")
    print(f"Params shape: {params.shape}")
    
    # Call stage2 runner
    try:
        results = run_stage2(
            open_arr, high_arr, low_arr, close_arr,
            params,
            strategy_name="donchian_atr"
        )
        print(f"Results type: {type(results)}")
        print(f"Results keys: {results.keys() if hasattr(results, 'keys') else 'N/A'}")
        
        if isinstance(results, dict):
            for key, value in results.items():
                print(f"  {key}: {type(value)}")
                if hasattr(value, 'shape'):
                    print(f"    shape: {value.shape}")
                elif hasattr(value, '__len__'):
                    print(f"    length: {len(value)}")
                    
            # Check for trades
            if 'trades' in results:
                trades = results['trades']
                print(f"\nTrades: {trades}")
                if hasattr(trades, '__len__'):
                    print(f"Number of trades: {len(trades)}")
                    
            # Check for equity
            if 'equity' in results:
                equity = results['equity']
                print(f"\nEquity: {equity}")
                if equity is not None and hasattr(equity, '__len__'):
                    print(f"Equity length: {len(equity)}")
                    print(f"Equity final: {equity[-1] if len(equity) > 0 else 'N/A'}")
    except Exception as e:
        print(f"Error calling stage2 runner: {e}")
        import traceback
        traceback.print_exc()

def check_environment():
    """Check if environment variable is set."""
    print("\n=== Environment check ===")
    mode = os.environ.get("FISHBRO_KERNEL_INTENT_MODE")
    print(f"FISHBRO_KERNEL_INTENT_MODE: {mode}")
    
    # Check kernel module
    import strategy.kernel
    print(f"Kernel module loaded from: {strategy.kernel.__file__}")

if __name__ == "__main__":
    check_environment()
    test_kernel_directly()
    test_stage2_runner()