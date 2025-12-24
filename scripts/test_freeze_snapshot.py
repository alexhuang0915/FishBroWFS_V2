#!/usr/bin/env python3
"""
Test script for freeze snapshot functionality.
"""

import sys
from pathlib import Path

# Add src to path
src_dir = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_dir))

from FishBroWFS_V2.core.season_state import freeze_season, unfreeze_season, load_season_state
from FishBroWFS_V2.core.snapshot import create_freeze_snapshot, verify_snapshot_integrity


def main():
    """Test freeze snapshot functionality."""
    print("=== Testing Freeze Snapshot Functionality ===\n")
    
    # Get current season
    from FishBroWFS_V2.core.season_context import current_season
    season = current_season()
    print(f"Current season: {season}")
    
    # Check current state
    state = load_season_state(season)
    print(f"Current state: {state.state}")
    
    if state.is_frozen():
        print("Season is already frozen. Unfreezing first...")
        unfreeze_season(season, by="cli", reason="test")
        state = load_season_state(season)
        print(f"Unfrozen. New state: {state.state}")
    
    # Test snapshot creation
    print("\n--- Testing snapshot creation ---")
    try:
        snapshot_path = create_freeze_snapshot(season)
        print(f"Snapshot created: {snapshot_path}")
        
        # Verify snapshot
        print("Verifying snapshot integrity...")
        result = verify_snapshot_integrity(season)
        if result["ok"]:
            print(f"✓ Snapshot integrity OK ({result['total_checked']} artifacts)")
        else:
            print(f"✗ Snapshot integrity issues:")
            if result["missing_files"]:
                print(f"  Missing files: {len(result['missing_files'])}")
            if result["changed_files"]:
                print(f"  Changed files: {len(result['changed_files'])}")
            if result["new_files"]:
                print(f"  New files: {len(result['new_files'])}")
    except Exception as e:
        print(f"✗ Snapshot creation failed: {e}")
    
    # Test freeze with snapshot
    print("\n--- Testing freeze with snapshot ---")
    try:
        frozen_state = freeze_season(
            season,
            by="cli",
            reason="test freeze with snapshot",
            create_snapshot=True
        )
        print(f"✓ Season frozen: {frozen_state.state}")
        print(f"  Frozen at: {frozen_state.frozen_ts}")
        print(f"  Reason: {frozen_state.reason}")
        
        # Check if snapshot was created
        from FishBroWFS_V2.core.season_context import season_dir
        snapshot_path = season_dir(season) / "governance" / "freeze_snapshot.json"
        if snapshot_path.exists():
            print(f"✓ Freeze snapshot exists: {snapshot_path}")
        else:
            print(f"✗ Freeze snapshot not found (expected at: {snapshot_path})")
    except Exception as e:
        print(f"✗ Freeze failed: {e}")
    
    # Clean up: unfreeze
    print("\n--- Cleaning up ---")
    try:
        unfrozen_state = unfreeze_season(season, by="cli", reason="test cleanup")
        print(f"✓ Season unfrozen: {unfrozen_state.state}")
    except Exception as e:
        print(f"✗ Unfreeze failed: {e}")
    
    print("\n=== Test completed ===")


if __name__ == "__main__":
    main()