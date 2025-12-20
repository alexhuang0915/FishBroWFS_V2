"""Research Governance Layer main entry point.

Phase 9: Generate canonical results and research index.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from FishBroWFS_V2.research.registry import build_research_index


def generate_canonical_results(outputs_root: Path, research_dir: Path) -> Path:
    """
    Generate canonical_results.json from all runs.
    
    Args:
        outputs_root: Root outputs directory
        research_dir: Research output directory
        
    Returns:
        Path to canonical_results.json
    """
    research_dir.mkdir(parents=True, exist_ok=True)
    
    # Scan all runs
    seasons_dir = outputs_root / "seasons"
    if not seasons_dir.exists():
        # Create empty results
        results_path = research_dir / "canonical_results.json"
        with open(results_path, "w", encoding="utf-8") as f:
            json.dump({"results": []}, f, indent=2, ensure_ascii=False, sort_keys=True)
        return results_path
    
    results = []
    
    # Scan seasons
    for season_dir in seasons_dir.iterdir():
        if not season_dir.is_dir():
            continue
        
        runs_dir = season_dir / "runs"
        if not runs_dir.exists():
            continue
        
        # Scan runs
        for run_dir in runs_dir.iterdir():
            if not run_dir.is_dir():
                continue
            
            try:
                metrics = extract_canonical_metrics(run_dir)
                results.append(metrics.to_dict())
            except ExtractionError:
                # Skip runs with missing artifacts
                continue
    
    # Write results
    results_path = research_dir / "canonical_results.json"
    results_data = {
        "results": results,
        "total_runs": len(results),
    }
    
    with open(results_path, "w", encoding="utf-8") as f:
        json.dump(results_data, f, indent=2, ensure_ascii=False, sort_keys=True)
    
    return results_path


def main() -> int:
    """Main entry point for research governance layer."""
    outputs_root = Path("outputs")
    research_dir = outputs_root / "research"
    
    try:
        # Generate canonical results
        print(f"Generating canonical_results.json...")
        generate_canonical_results(outputs_root, research_dir)
        
        # Build research index
        print(f"Building research_index.json...")
        build_research_index(outputs_root, research_dir)
        
        print(f"Research governance layer completed successfully.")
        print(f"Output directory: {research_dir}")
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())

