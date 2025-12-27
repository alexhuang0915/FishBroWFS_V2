#!/usr/bin/env python3
"""
Create a subset of raw TXT file for testing.
"""
import pandas as pd
from pathlib import Path

def main():
    raw_path = Path("FishBroData/raw/CME.MNQ HOT-Minute-Trade.txt")
    subset_path = Path("FishBroData/raw/CME.MNQ_SUBSET.txt")
    
    # Read with pandas (assuming header)
    df = pd.read_csv(raw_path)
    # Convert Date column to datetime
    df['Date'] = pd.to_datetime(df['Date'], format='%Y/%m/%d')
    # Filter to year 2020 only (or a few days)
    df_subset = df[df['Date'].dt.year == 2020].copy()
    # Limit to first 1000 rows if still large
    if len(df_subset) > 1000:
        df_subset = df_subset.head(1000)
    
    # Write back with same format
    df_subset['Date'] = df_subset['Date'].dt.strftime('%Y/%-m/%-d')
    df_subset.to_csv(subset_path, index=False)
    print(f"Created subset with {len(df_subset)} rows at {subset_path}")

if __name__ == "__main__":
    main()