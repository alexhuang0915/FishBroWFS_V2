"""Data discovery service for scanning raw data directories.

Phase 13: Real DATA Discovery - populate OP DATA selectors with actual datasets.
"""
import os
import logging
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)

# Authoritative path (MANDATORY per spec)
RAW_DATA_PATH = Path("/home/fishbro/FishBroWFS_V2/FishBroData/raw")


def discover_raw_datasets() -> List[str]:
    """Scan the authoritative raw data path and extract dataset identifiers.
    
    Returns:
        Sorted, unique list of dataset identifiers (e.g., ["CME.MNQ", "TWF.MXF"]).
        Returns empty list if directory doesn't exist or contains no recognizable files.
    """
    if not RAW_DATA_PATH.exists():
        logger.warning(f"Raw data path does not exist: {RAW_DATA_PATH}")
        return []
    
    if not RAW_DATA_PATH.is_dir():
        logger.warning(f"Raw data path is not a directory: {RAW_DATA_PATH}")
        return []
    
    identifiers = set()
    
    for item in RAW_DATA_PATH.iterdir():
        if not item.is_file():
            continue
        
        # Extract identifier from filename
        # Expected pattern: "{IDENTIFIER} HOT-Minute-Trade.txt" or "{IDENTIFIER}_SUBSET.txt"
        name = item.name
        # Remove known suffixes
        if name.endswith(" HOT-Minute-Trade.txt"):
            identifier = name[:-len(" HOT-Minute-Trade.txt")]
        elif name.endswith("_SUBSET.txt"):
            identifier = name[:-len("_SUBSET.txt")]
        else:
            # Try to extract before first space or underscore
            identifier = name.split()[0] if ' ' in name else name.split('_')[0]
            # Remove file extension
            identifier = identifier.rsplit('.', 1)[0] if '.' in identifier else identifier
        
        # Clean up identifier (should be like "CME.MNQ")
        if identifier and '.' in identifier:
            identifiers.add(identifier)
        else:
            logger.debug(f"Skipping file with unrecognized identifier pattern: {name}")
    
    return sorted(identifiers)


def get_dataset_options() -> List[str]:
    """Get dataset options for UI selectors.
    
    Returns:
        List of dataset identifiers sorted alphabetically.
        Includes a fallback empty list with placeholder if no datasets found.
    """
    datasets = discover_raw_datasets()
    if not datasets:
        logger.warning("No datasets discovered in raw data path")
        # Return empty list - UI should handle empty state
        return []
    return datasets


if __name__ == "__main__":
    # Quick test
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
    datasets = discover_raw_datasets()
    print(f"Discovered {len(datasets)} datasets:")
    for d in datasets:
        print(f"  - {d}")