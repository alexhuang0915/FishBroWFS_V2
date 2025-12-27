"""Artifacts API for M2 Drill-down.

Provides read-only access to research and portfolio indices.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Any

from control.artifacts import write_json_atomic


def write_research_index(season: str, job_id: str, units: List[Dict[str, Any]]) -> Path:
    """Write research index for a job.
    
    Creates a JSON file at outputs/seasons/{season}/research/{job_id}/research_index.json
    with the structure:
    {
        "season": season,
        "job_id": job_id,
        "units_total": len(units),
        "units": units
    }
    
    Args:
        season: Season identifier (e.g., "2026Q1")
        job_id: Job identifier
        units: List of unit dictionaries, each containing at least:
            - data1_symbol
            - data1_timeframe
            - strategy
            - data2_filter
            - status
            - artifacts dict with canonical_results, metrics, trades paths
    
    Returns:
        Path to the written index file.
    """
    idx = {
        "season": season,
        "job_id": job_id,
        "units_total": len(units),
        "units": units,
    }
    # Ensure the directory exists
    index_dir = Path(f"outputs/seasons/{season}/research/{job_id}")
    index_dir.mkdir(parents=True, exist_ok=True)
    path = index_dir / "research_index.json"
    write_json_atomic(path, idx)
    return path


def list_research_units(season: str, job_id: str) -> List[Dict[str, Any]]:
    """List research units for a given job.
    
    Reads the research index file and returns the units list.
    
    Args:
        season: Season identifier
        job_id: Job identifier
    
    Returns:
        List of unit dictionaries as stored in the index.
    
    Raises:
        FileNotFoundError: If research index file does not exist.
    """
    index_path = Path(f"outputs/seasons/{season}/research/{job_id}/research_index.json")
    if not index_path.exists():
        raise FileNotFoundError(f"Research index not found at {index_path}")
    with open(index_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("units", [])


def get_research_artifacts(
    season: str, job_id: str, unit_key: Dict[str, str]
) -> Dict[str, str]:
    """Get artifact paths for a specific research unit.
    
    The unit_key must contain data1_symbol, data1_timeframe, strategy, data2_filter.
    
    Args:
        season: Season identifier
        job_id: Job identifier
        unit_key: Dictionary with keys data1_symbol, data1_timeframe, strategy, data2_filter
    
    Returns:
        Artifacts dictionary (canonical_results, metrics, trades paths).
    
    Raises:
        KeyError: If unit not found.
    """
    units = list_research_units(season, job_id)
    for unit in units:
        match = all(
            unit.get(k) == v for k, v in unit_key.items()
            if k in ("data1_symbol", "data1_timeframe", "strategy", "data2_filter")
        )
        if match:
            return unit.get("artifacts", {})
    raise KeyError(f"No unit found matching {unit_key}")


def get_portfolio_index(season: str, job_id: str) -> Dict[str, Any]:
    """Get portfolio index for a given job.
    
    Reads portfolio_index.json from outputs/seasons/{season}/portfolio/{job_id}/portfolio_index.json.
    
    Args:
        season: Season identifier
        job_id: Job identifier
    
    Returns:
        Portfolio index dictionary.
    
    Raises:
        FileNotFoundError: If portfolio index file does not exist.
    """
    index_path = Path(f"outputs/seasons/{season}/portfolio/{job_id}/portfolio_index.json")
    if not index_path.exists():
        raise FileNotFoundError(f"Portfolio index not found at {index_path}")
    with open(index_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data


# Optional helper to write portfolio index
def write_portfolio_index(
    season: str,
    job_id: str,
    summary_path: str,
    admission_path: str,
) -> Path:
    """Write portfolio index for a job.
    
    Creates a JSON file at outputs/seasons/{season}/portfolio/{job_id}/portfolio_index.json
    with the structure:
    {
        "season": season,
        "job_id": job_id,
        "summary": summary_path,
        "admission": admission_path
    }
    
    Args:
        season: Season identifier
        job_id: Job identifier
        summary_path: Relative path to summary.json
        admission_path: Relative path to admission.parquet
    
    Returns:
        Path to the written index file.
    """
    idx = {
        "season": season,
        "job_id": job_id,
        "summary": summary_path,
        "admission": admission_path,
    }
    index_dir = Path(f"outputs/seasons/{season}/portfolio/{job_id}")
    index_dir.mkdir(parents=True, exist_ok=True)
    path = index_dir / "portfolio_index.json"
    write_json_atomic(path, idx)
    return path