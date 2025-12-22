
"""Result Registry - scan outputs and build research index.

Phase 9: Scan outputs/ directory and create canonical_results.json and research_index.json.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from FishBroWFS_V2.research.decision import load_decisions
from FishBroWFS_V2.research.extract import extract_canonical_metrics, ExtractionError


def build_research_index(outputs_root: Path, out_dir: Path) -> Path:
    """
    Build research index from scanned outputs.
    
    Scans outputs/seasons/{season}/runs/{run_id}/ and extracts canonical metrics.
    Outputs two files:
    - canonical_results.json: List of all CanonicalMetrics as dicts
    - research_index.json: Sorted lightweight index with run_id, score_final, decision, keys
    
    Sorting rules (fixed):
    1. score_final desc
    2. score_net_mdd desc
    3. trades desc
    
    Args:
        outputs_root: Root outputs directory (e.g., Path("outputs"))
        out_dir: Output directory for research artifacts (e.g., Path("outputs/research"))
        
    Returns:
        Path to research_index.json
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    
    # Scan all runs
    canonical_results = []
    seasons_dir = outputs_root / "seasons"
    
    if seasons_dir.exists():
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
                    canonical_results.append(metrics.to_dict())
                except ExtractionError:
                    # Skip runs with missing artifacts
                    continue
    
    # Write canonical_results.json (list of CanonicalMetrics as dict)
    canonical_path = out_dir / "canonical_results.json"
    with open(canonical_path, "w", encoding="utf-8") as f:
        json.dump(canonical_results, f, indent=2, ensure_ascii=False, sort_keys=True)
    
    # Load decisions (if any)
    decisions = load_decisions(out_dir)
    decision_map: Dict[str, str] = {}
    for decision_entry in decisions:
        run_id = decision_entry.get("run_id")
        decision = decision_entry.get("decision")
        if run_id and decision:
            # Last-write-wins: later entries overwrite earlier ones
            decision_map[run_id] = decision
    
    # Build lightweight index with sorting
    index_entries = []
    for result in canonical_results:
        run_id = result.get("run_id")
        if not run_id:
            continue
        
        entry = {
            "run_id": run_id,
            "score_final": result.get("score_final", 0.0),
            "score_net_mdd": result.get("score_net_mdd", 0.0),
            "trades": result.get("trades", 0),
            "decision": decision_map.get(run_id, "UNDECIDED"),
            "keys": {
                "portfolio_id": result.get("portfolio_id"),
                "strategy_id": result.get("strategy_id"),
                "symbol": result.get("symbol"),
            },
        }
        index_entries.append(entry)
    
    # Sort: score_final desc, then score_net_mdd desc, then trades desc
    index_entries.sort(
        key=lambda x: (
            -x["score_final"],  # Negative for descending
            -x["score_net_mdd"],
            -x["trades"],
        )
    )
    
    # Write research_index.json
    index_data = {
        "entries": index_entries,
        "total_runs": len(index_entries),
    }
    
    index_path = out_dir / "research_index.json"
    with open(index_path, "w", encoding="utf-8") as f:
        json.dump(index_data, f, indent=2, ensure_ascii=False, sort_keys=True)
    
    return index_path


