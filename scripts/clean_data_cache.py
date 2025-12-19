"""Clean parquet data cache.

Binding #4: Parquet is Cache, Not Truth.
This script deletes all .parquet and .meta.json files from cache root.
Raw TXT files are never deleted.
"""

from __future__ import annotations

import sys
from pathlib import Path


def main() -> int:
    """Clean parquet cache files.
    
    Scans cache_root (default: parquet_cache/) and deletes:
    - All .parquet files
    - All .meta.json files
    
    Raw TXT files are never deleted.
    
    Returns:
        0 on success, 1 on error
    """
    # Default cache root (can be overridden via env var or config)
    cache_root = Path("parquet_cache")
    
    # Check if cache root exists
    if not cache_root.exists():
        print(f"Cache root does not exist: {cache_root}")
        print("Nothing to clean.")
        return 0
    
    if not cache_root.is_dir():
        print(f"Cache root is not a directory: {cache_root}")
        return 1
    
    # Find all .parquet and .meta.json files
    parquet_files = list(cache_root.glob("*.parquet"))
    meta_files = list(cache_root.glob("*.meta.json"))
    
    total_files = len(parquet_files) + len(meta_files)
    
    if total_files == 0:
        print(f"No cache files found in {cache_root}")
        return 0
    
    print(f"Found {len(parquet_files)} parquet files and {len(meta_files)} meta files")
    print(f"Deleting {total_files} cache files...")
    
    deleted_count = 0
    error_count = 0
    
    # Delete parquet files
    for parquet_file in parquet_files:
        try:
            parquet_file.unlink()
            deleted_count += 1
            print(f"  Deleted: {parquet_file.name}")
        except Exception as e:
            print(f"  Error deleting {parquet_file.name}: {e}", file=sys.stderr)
            error_count += 1
    
    # Delete meta files
    for meta_file in meta_files:
        try:
            meta_file.unlink()
            deleted_count += 1
            print(f"  Deleted: {meta_file.name}")
        except Exception as e:
            print(f"  Error deleting {meta_file.name}: {e}", file=sys.stderr)
            error_count += 1
    
    print(f"\nCompleted: {deleted_count} files deleted, {error_count} errors")
    
    if error_count > 0:
        return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
