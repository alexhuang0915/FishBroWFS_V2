
#!/usr/bin/env python3
"""
Funnel pipeline CLI entry point.

Reads config and runs funnel pipeline, outputting stage run directories.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Add src to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from FishBroWFS_V2.pipeline.funnel_runner import run_funnel


def load_config(config_path: Path) -> dict:
    """
    Load configuration from JSON file.
    
    Args:
        config_path: Path to JSON config file
        
    Returns:
        Configuration dictionary
    """
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)


def main() -> int:
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Run funnel pipeline (Stage0 → Stage1 → Stage2)"
    )
    parser.add_argument(
        "--config",
        type=Path,
        required=True,
        help="Path to JSON configuration file",
    )
    parser.add_argument(
        "--outputs-root",
        type=Path,
        default=Path("outputs"),
        help="Root outputs directory (default: outputs)",
    )
    
    args = parser.parse_args()
    
    try:
        # Load config
        cfg = load_config(args.config)
        
        # Ensure outputs root exists
        args.outputs_root.mkdir(parents=True, exist_ok=True)
        
        # Run funnel
        result_index = run_funnel(cfg, args.outputs_root)
        
        # Print stage run directories (for tracking)
        print("Funnel pipeline completed successfully.")
        print("\nStage run directories:")
        for stage_idx in result_index.stages:
            print(f"  {stage_idx.stage.value}: {stage_idx.run_dir}")
            print(f"    run_id: {stage_idx.run_id}")
        
        return 0
        
    except Exception as e:
        print(f"ERROR: Funnel pipeline failed: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())


