#!/usr/bin/env python3
"""
Debug script to see which configs are loaded.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from config import (
    reset_config_load_records,
    get_config_load_records,
    enable_config_recording,
    clear_config_caches,
    load_profile,
    load_strategy,
    load_instruments,
)

def main():
    enable_config_recording(True)
    reset_config_load_records()
    clear_config_caches()
    
    print("Loading profile CME_MNQ_TPE_v1...")
    try:
        p = load_profile("CME_MNQ_TPE_v1")
        print(f"Loaded profile: {p.symbol}")
    except Exception as e:
        print(f"Error: {e}")
    
    print("Loading strategy S1...")
    try:
        s = load_strategy("S1")
        print(f"Loaded strategy: {s.strategy_id}")
    except Exception as e:
        print(f"Error: {e}")
    
    print("Loading instruments...")
    try:
        i = load_instruments()
        print(f"Loaded instruments: {len(i.instruments)}")
    except Exception as e:
        print(f"Error: {e}")
    
    records = get_config_load_records()
    print(f"\nTotal configs loaded: {len(records)}")
    for path, info in records.items():
        print(f"  {path}: count={info['count']}, sha256={info['sha256'][:16]}...")

if __name__ == "__main__":
    main()