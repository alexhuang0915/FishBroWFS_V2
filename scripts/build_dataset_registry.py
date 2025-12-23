#!/usr/bin/env python3
"""Build Dataset Registry from derived data files.

Phase 12: Automated dataset registry generation.
Scans data/derived/**/* and creates deterministic index.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import date, datetime
from pathlib import Path
from typing import List, Optional

from FishBroWFS_V2.data.dataset_registry import DatasetIndex, DatasetRecord


def parse_filename_to_dates(filename: str) -> Optional[tuple[date, date]]:
    """Parse YYYY-YYYY or YYYYMMDD-YYYYMMDD date range from filename.
    
    Expected patterns:
    - "2020-2024.parquet" -> (2020-01-01, 2024-12-31)
    - "20200101-20241231.parquet" -> (2020-01-01, 2024-12-31)
    """
    # Remove extension
    stem = Path(filename).stem
    
    # Pattern 1: YYYY-YYYY
    match = re.match(r"^(\d{4})-(\d{4})$", stem)
    if match:
        start_year = int(match.group(1))
        end_year = int(match.group(2))
        return (
            date(start_year, 1, 1),
            date(end_year, 12, 31)
        )
    
    # Pattern 2: YYYYMMDD-YYYYMMDD
    match = re.match(r"^(\d{8})-(\d{8})$", stem)
    if match:
        start_str = match.group(1)
        end_str = match.group(2)
        return (
            date(int(start_str[:4]), int(start_str[4:6]), int(start_str[6:8])),
            date(int(end_str[:4]), int(end_str[4:6]), int(end_str[6:8]))
        )
    
    return None


def compute_file_fingerprints(file_path: Path) -> tuple[str, str]:
    """Compute SHA1 and SHA256 (first 40 chars) hashes of file content (binary).
    
    WARNING: Must use content hash, NOT mtime/size.
    """
    sha1 = hashlib.sha1()
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        # Read in chunks to handle large files
        for chunk in iter(lambda: f.read(8192), b""):
            sha1.update(chunk)
            sha256.update(chunk)
    sha1_digest = sha1.hexdigest()
    sha256_digest = sha256.hexdigest()[:40]  # first 40 hex chars
    return sha1_digest, sha256_digest


def build_registry(derived_root: Path) -> DatasetIndex:
    """Build dataset registry by scanning derived data directory.
    
    Expected directory structure:
        data/derived/{SYMBOL}/{TIMEFRAME}/{START}-{END}.parquet
    
    Contract:
    - Delete index → rerun script → produce identical output (deterministic)
    - Index content must have 1:1 correspondence with physical files
    """
    datasets: List[DatasetRecord] = []
    
    # Walk through derived directory
    for symbol_dir in derived_root.iterdir():
        if not symbol_dir.is_dir():
            continue
        
        symbol = symbol_dir.name
        
        for timeframe_dir in symbol_dir.iterdir():
            if not timeframe_dir.is_dir():
                continue
            
            timeframe = timeframe_dir.name
            
            for parquet_file in timeframe_dir.glob("*.parquet"):
                # Parse date range from filename
                date_range = parse_filename_to_dates(parquet_file.name)
                if not date_range:
                    print(f"Warning: Skipping {parquet_file} - cannot parse date range")
                    continue
                
                start_date, end_date = date_range
                
                # Validate start_date <= end_date
                if start_date > end_date:
                    print(f"Warning: Skipping {parquet_file} - start_date > end_date")
                    continue
                
                # Compute fingerprints
                fingerprint_sha1, fingerprint_sha256_40 = compute_file_fingerprints(parquet_file)
                
                # Construct relative path
                rel_path = parquet_file.relative_to(derived_root)
                
                # Construct dataset ID
                dataset_id = f"{symbol}.{timeframe}.{start_date.year}-{end_date.year}"
                
                # Extract exchange from symbol (e.g., "CME.MNQ" -> "CME")
                exchange = symbol.split(".")[0] if "." in symbol else symbol
                
                # Create dataset record
                record = DatasetRecord(
                    id=dataset_id,
                    symbol=symbol,
                    exchange=exchange,
                    timeframe=timeframe,
                    path=str(rel_path),
                    start_date=start_date,
                    end_date=end_date,
                    fingerprint_sha1=fingerprint_sha1,
                    fingerprint_sha256_40=fingerprint_sha256_40,
                    tz_provider="IANA",
                    tz_version="unknown"
                )
                
                datasets.append(record)
                print(f"Registered: {dataset_id} ({start_date} to {end_date})")
    
    # Sort datasets for deterministic output
    datasets.sort(key=lambda r: r.id)
    
    return DatasetIndex(
        generated_at=datetime.now(),
        datasets=datasets
    )


def main() -> None:
    """Main entry point for CLI."""
    import sys
    
    # Determine paths
    project_root = Path(__file__).parent.parent
    derived_root = project_root / "data" / "derived"
    output_dir = project_root / "outputs" / "datasets"
    output_file = output_dir / "datasets_index.json"
    
    # Check if derived directory exists
    if not derived_root.exists():
        print(f"Error: Derived data directory not found: {derived_root}")
        print("Expected structure: data/derived/{SYMBOL}/{TIMEFRAME}/{START}-{END}.parquet")
        sys.exit(1)
    
    # Build registry
    print(f"Scanning derived data in: {derived_root}")
    index = build_registry(derived_root)
    
    # Ensure output directory exists
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Write index to file
    with open(output_file, "w", encoding="utf-8") as f:
        json_data = index.model_dump_json(indent=2)
        f.write(json_data)
    
    print(f"Dataset registry written to: {output_file}")
    print(f"Registered {len(index.datasets)} datasets")
    
    # Print summary
    if index.datasets:
        print("\nDataset summary:")
        for record in index.datasets:
            print(f"  - {record.id}: {record.start_date} to {record.end_date}")


if __name__ == "__main__":
    main()
