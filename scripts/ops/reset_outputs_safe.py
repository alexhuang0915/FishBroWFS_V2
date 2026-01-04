#!/usr/bin/env python3
"""
Safe Outputs Reset Utility.

Resets outputs directory while preserving critical evidence and diagnostic files.
MUST NOT touch the authoritative raw data: /home/fishbro/FishBroWFS_V2/FishBroData/raw
"""

from __future__ import annotations

import argparse
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Set

# Default items to keep (preserve in place or move to trash)
DEFAULT_KEEP_ITEMS = {
    "_dp_evidence",
    "diagnostics",
    "forensics",
    "fingerprints",
}

# Items that can optionally be dropped
OPTIONAL_ITEMS = {
    "jobsdb",
}

# Canonical outputs skeleton to recreate
CANONICAL_SKELETON = [
    "seasons",
    "seasons/2026Q1",
    "seasons/2026Q1/runs",
    "seasons/2026Q1/portfolios",
    "seasons/2026Q1/shared",
    "shared",
    "system",
    "system/state",
    "system/logs",
    "_trash",
]


def parse_args(args_list: list[str] | None = None) -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Safe reset of outputs directory while preserving critical evidence."
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Confirm execution (required for actual reset)",
    )
    parser.add_argument(
        "--keep",
        nargs="+",
        default=list(DEFAULT_KEEP_ITEMS),
        help=f"Items to keep (default: {', '.join(sorted(DEFAULT_KEEP_ITEMS))})",
    )
    parser.add_argument(
        "--drop",
        nargs="+",
        default=[],
        help=f"Optional items to drop (available: {', '.join(sorted(OPTIONAL_ITEMS))})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without making changes",
    )
    parser.add_argument(
        "--outputs-root",
        default="outputs",
        help="Path to outputs directory (default: 'outputs')",
    )
    return parser.parse_args(args_list)


def validate_args(args: argparse.Namespace) -> bool:
    """Validate command line arguments."""
    outputs_root = Path(args.outputs_root)
    if not outputs_root.exists():
        print(f"ERROR: Outputs root does not exist: {outputs_root}")
        return False
    
    # Check for raw data protection
    raw_data_path = Path("/home/fishbro/FishBroWFS_V2/FishBroData/raw")
    if outputs_root.resolve() == raw_data_path.resolve():
        print(f"ERROR: Cannot reset raw data directory: {raw_data_path}")
        return False
    
    # Validate keep items
    for item in args.keep:
        if item not in DEFAULT_KEEP_ITEMS and item not in OPTIONAL_ITEMS:
            print(f"WARNING: Unknown keep item: {item}")
    
    # Validate drop items
    for item in args.drop:
        if item not in OPTIONAL_ITEMS:
            print(f"WARNING: Unknown drop item: {item}")
    
    return True


def get_items_to_preserve(args: argparse.Namespace) -> Set[str]:
    """Determine which items to preserve based on keep/drop arguments."""
    preserve = set(args.keep)
    
    # Remove any items that are explicitly dropped
    for item in args.drop:
        if item in preserve:
            preserve.remove(item)
    
    return preserve


def move_to_trash(
    outputs_root: Path,
    item_name: str,
    timestamp: str,
    dry_run: bool = False,
) -> Path:
    """Move an item to the trash directory with timestamp."""
    source_path = outputs_root / item_name
    if not source_path.exists():
        return Path()
    
    trash_dir = outputs_root / "_trash" / f"{item_name}.{timestamp}"
    
    if dry_run:
        print(f"  Would move: {source_path} -> {trash_dir}")
        return trash_dir
    
    try:
        # Ensure trash directory exists
        trash_dir.parent.mkdir(parents=True, exist_ok=True)
        
        # Move the item
        shutil.move(str(source_path), str(trash_dir))
        print(f"  Moved: {source_path} -> {trash_dir}")
        return trash_dir
    except Exception as e:
        print(f"  ERROR moving {source_path}: {e}")
        return Path()


def recreate_skeleton(outputs_root: Path, dry_run: bool = False) -> None:
    """Recreate the canonical outputs skeleton."""
    for dir_path in CANONICAL_SKELETON:
        full_path = outputs_root / dir_path
        
        if dry_run:
            if not full_path.exists():
                print(f"  Would create: {full_path}")
            continue
        
        try:
            full_path.mkdir(parents=True, exist_ok=True)
            if not full_path.exists():
                print(f"  Created: {full_path}")
        except Exception as e:
            print(f"  ERROR creating {full_path}: {e}")


def reset_outputs(args: argparse.Namespace) -> bool:
    """Main reset logic."""
    outputs_root = Path(args.outputs_root)
    preserve_items = get_items_to_preserve(args)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    print(f"Outputs root: {outputs_root.absolute()}")
    print(f"Preserving: {', '.join(sorted(preserve_items))}")
    print(f"Timestamp: {timestamp}")
    print(f"Mode: {'DRY RUN' if args.dry_run else 'EXECUTE'}")
    print()
    
    # Step 1: Move preserved items to trash (or keep in place)
    moved_items = []
    for item in sorted(preserve_items):
        item_path = outputs_root / item
        if item_path.exists():
            trash_path = move_to_trash(outputs_root, item, timestamp, args.dry_run)
            if trash_path:
                moved_items.append((item, trash_path))
        else:
            print(f"  Note: {item} does not exist, nothing to preserve")
    
    # Step 2: Remove everything except _trash
    print("\nRemoving non-preserved items...")
    for item in outputs_root.iterdir():
        if item.name == "_trash":
            continue  # Keep trash directory
        
        # Skip if this was just moved to trash
        if any(item.name == moved_item[0] for moved_item in moved_items):
            continue
        
        if args.dry_run:
            print(f"  Would remove: {item}")
        else:
            try:
                if item.is_file():
                    item.unlink()
                    print(f"  Removed file: {item}")
                else:
                    shutil.rmtree(item)
                    print(f"  Removed directory: {item}")
            except Exception as e:
                print(f"  ERROR removing {item}: {e}")
    
    # Step 3: Recreate skeleton
    print("\nRecreating canonical skeleton...")
    recreate_skeleton(outputs_root, args.dry_run)
    
    # Step 4: Restore preserved items from trash (if they were moved)
    if not args.dry_run:
        print("\nRestoring preserved items...")
        for item_name, trash_path in moved_items:
            if not trash_path.exists():
                continue
            
            restore_path = outputs_root / item_name
            try:
                shutil.move(str(trash_path), str(restore_path))
                print(f"  Restored: {item_name}")
            except Exception as e:
                print(f"  ERROR restoring {item_name}: {e}")
    
    print("\nReset completed successfully!")
    return True


def safe_reset_outputs(
    outputs_root: Path,
    keep_items: List[str],
    drop_jobsdb: bool = False,
    dry_run: bool = False,
) -> bool:
    """
    Safe reset of outputs directory.
    
    Args:
        outputs_root: Path to outputs directory
        keep_items: List of item names to preserve
        drop_jobsdb: Whether to drop jobs.db file
        dry_run: If True, only show what would be done
        
    Returns:
        True if successful
    """
    # Convert to argparse-like namespace for compatibility
    class Args:
        pass
    
    args = Args()
    args.outputs_root = str(outputs_root)
    args.keep = keep_items
    args.drop = ["jobsdb"] if drop_jobsdb else []
    args.dry_run = dry_run
    args.yes = not dry_run  # For dry run, we don't need --yes
    
    # Validate
    if not validate_args(args):
        return False
    
    # Execute reset
    return reset_outputs(args)


def main(args_list: list[str] | None = None) -> int:
    """Main entry point."""
    args = parse_args(args_list)
    
    if not validate_args(args):
        return 1
    
    if not args.yes and not args.dry_run:
        print("ERROR: --yes flag is required for actual reset")
        print("       Use --dry-run to see what would be done")
        return 1
    
    try:
        success = reset_outputs(args)
        return 0 if success else 1
    except KeyboardInterrupt:
        print("\nReset interrupted by user")
        return 1
    except Exception as e:
        print(f"\nERROR during reset: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())