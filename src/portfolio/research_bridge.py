
"""Research to Portfolio Bridge.

Phase 11: Bridge research decisions to executable portfolio specifications.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Set, Tuple, Optional

from .decisions_reader import read_decisions_log
from .hash_utils import stable_json_dumps, sha1_text
from .spec import PortfolioLeg, PortfolioSpec


def load_research_index(research_root: Path) -> dict:
    """Load research index from research directory.
    
    Args:
        research_root: Path to research directory (outputs/seasons/{season}/research/)
        
    Returns:
        Research index data
    """
    index_path = research_root / "research_index.json"
    if not index_path.exists():
        raise FileNotFoundError(f"research_index.json not found at {index_path}")
    
    with open(index_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def build_portfolio_from_research(
    *,
    season: str,
    outputs_root: Path,
    symbols_allowlist: Set[str],
    run_ids_allowlist: Optional[Set[str]] = None,
) -> Tuple[str, PortfolioSpec, dict]:
    """Build portfolio from research decisions.
    
    Args:
        season: Season identifier (e.g., "2026Q1")
        outputs_root: Root outputs directory
        symbols_allowlist: Set of allowed symbols (e.g., {"CME.MNQ", "TWF.MXF"})
        run_ids_allowlist: Optional set of run IDs to restrict to (intersection with KEEP decisions).
            If None, all KEEP decisions are used.
        
    Returns:
        Tuple of (portfolio_id, portfolio_spec, manifest_dict)
    """
    # Paths
    research_root = outputs_root / "seasons" / season / "research"
    decisions_log_path = research_root / "decisions.log"
    
    # Load research data
    research_index = load_research_index(research_root)
    decisions = read_decisions_log(decisions_log_path)
    
    # Process decisions to get final decision for each run_id
    final_decisions = _get_final_decisions(decisions)
    
    # Filter to only KEEP decisions
    keep_run_ids = {
        run_id for run_id, decision_info in final_decisions.items()
        if decision_info.get('decision', '').upper() == 'KEEP'
    }
    
    # Apply run_ids_allowlist if provided
    if run_ids_allowlist is not None:
        keep_run_ids = keep_run_ids.intersection(run_ids_allowlist)
    
    # Extract research entries and filter by allowlist
    research_entries = research_index.get('entries', [])
    filtered_entries = []
    missing_run_ids = []
    
    for entry in research_entries:
        run_id = entry.get('run_id', '')
        if not run_id:
            continue
            
        if run_id not in keep_run_ids:
            continue
            
        symbol = entry.get('keys', {}).get('symbol', '')
        if symbol not in symbols_allowlist:
            continue
            
        # Check if we have all required metadata
        keys = entry.get('keys', {})
        if not keys.get('strategy_id'):
            missing_run_ids.append(run_id)
            continue
            
        filtered_entries.append(entry)
    
    # Create portfolio legs
    legs = _create_portfolio_legs(filtered_entries, final_decisions)
    
    # Sort legs deterministically
    sorted_legs = _sort_legs_deterministically(legs)
    
    # Generate portfolio ID
    portfolio_id = _generate_portfolio_id(
        season=season,
        symbols_allowlist=symbols_allowlist,
        legs=sorted_legs
    )
    
    # Create portfolio spec
    portfolio_spec = PortfolioSpec(
        portfolio_id=portfolio_id,
        version=f"{season}_research",
        legs=sorted_legs
    )
    
    # Create manifest
    manifest = _create_manifest(
        portfolio_id=portfolio_id,
        season=season,
        symbols_allowlist=symbols_allowlist,
        decisions_log_path=decisions_log_path,
        research_index_path=research_root / "research_index.json",
        legs=sorted_legs,
        missing_run_ids=missing_run_ids,
        total_decisions=len(decisions),
        keep_decisions=len(keep_run_ids)
    )
    
    return portfolio_id, portfolio_spec, manifest


def _get_final_decisions(decisions: List[dict]) -> Dict[str, dict]:
    """Get final decision for each run_id (last entry wins)."""
    final_map = {}
    
    for entry in decisions:
        run_id = entry.get('run_id', '')
        if not run_id:
            continue
            
        # Store entry (last one wins)
        final_map[run_id] = {
            'decision': entry.get('decision', ''),
            'note': entry.get('note', ''),
            'ts': entry.get('ts')
        }
    
    return final_map


def _create_portfolio_legs(
    entries: List[dict],
    final_decisions: Dict[str, dict]
) -> List[PortfolioLeg]:
    """Create PortfolioLeg objects from filtered research entries."""
    legs = []
    
    for entry in entries:
        run_id = entry.get('run_id', '')
        keys = entry.get('keys', {})
        
        # Extract required fields
        symbol = keys.get('symbol', '')
        strategy_id = keys.get('strategy_id', '')
        
        # Extract from entry metadata
        strategy_version = entry.get('strategy_version', '1.0.0')
        timeframe_min = entry.get('timeframe_min', 60)
        session_profile = entry.get('session_profile', 'default')
        
        # Extract metrics if available
        score_final = entry.get('score_final')
        trades = entry.get('trades')
        
        # Get note from final decision
        decision_info = final_decisions.get(run_id, {})
        note = decision_info.get('note', '')
        
        # Create leg_id from run_id (or generate deterministic ID)
        leg_id = f"{run_id}_{symbol}_{strategy_id}"
        
        # Create leg
        leg = PortfolioLeg(
            leg_id=leg_id,
            symbol=symbol,
            timeframe_min=timeframe_min,
            session_profile=session_profile,
            strategy_id=strategy_id,
            strategy_version=strategy_version,
            params={},  # Empty params for research-generated legs
            enabled=True,
            tags=["research_generated", season] if 'season' in locals() else ["research_generated"]
        )
        
        legs.append(leg)
    
    return legs


def _sort_legs_deterministically(legs: List[PortfolioLeg]) -> List[PortfolioLeg]:
    """Sort legs deterministically."""
    def sort_key(leg: PortfolioLeg) -> tuple:
        return (
            leg.symbol or '',
            leg.timeframe_min or 0,
            leg.strategy_id or '',
            leg.leg_id or ''
        )
    
    return sorted(legs, key=sort_key)


def _generate_portfolio_id(
    season: str,
    symbols_allowlist: Set[str],
    legs: List[PortfolioLeg]
) -> str:
    """Generate deterministic portfolio ID."""
    
    # Extract core fields from legs for ID generation
    legs_core = []
    for leg in legs:
        legs_core.append({
            'leg_id': leg.leg_id,
            'symbol': leg.symbol,
            'strategy_id': leg.strategy_id,
            'strategy_version': leg.strategy_version,
            'timeframe_min': leg.timeframe_min,
            'session_profile': leg.session_profile
        })
    
    # Sort for determinism
    sorted_allowlist = sorted(symbols_allowlist)
    sorted_legs_core = sorted(legs_core, key=lambda x: x['leg_id'])
    
    # Create ID payload
    id_payload = {
        'season': season,
        'symbols_allowlist': sorted_allowlist,
        'legs_core': sorted_legs_core,
        'generator_version': 'phase11_v1'
    }
    
    # Generate SHA1 and take first 12 chars
    json_str = stable_json_dumps(id_payload)
    full_hash = sha1_text(json_str)
    return full_hash[:12]


def _create_manifest(
    portfolio_id: str,
    season: str,
    symbols_allowlist: Set[str],
    decisions_log_path: Path,
    research_index_path: Path,
    legs: List[PortfolioLeg],
    missing_run_ids: List[str],
    total_decisions: int,
    keep_decisions: int
) -> dict:
    """Create portfolio manifest with metadata."""
    
    # Calculate symbol breakdown
    symbols_breakdown = {}
    for leg in legs:
        symbol = leg.symbol
        symbols_breakdown[symbol] = symbols_breakdown.get(symbol, 0) + 1
    
    # Calculate file hashes
    decisions_log_hash = _calculate_file_hash(decisions_log_path) if decisions_log_path.exists() else ""
    research_index_hash = _calculate_file_hash(research_index_path) if research_index_path.exists() else ""
    
    return {
        'portfolio_id': portfolio_id,
        'season': season,
        'generated_at': datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
        'symbols_allowlist': sorted(symbols_allowlist),
        'inputs': {
            'decisions_log_path': str(decisions_log_path.relative_to(decisions_log_path.parent.parent.parent)),
            'decisions_log_sha1': decisions_log_hash,
            'research_index_path': str(research_index_path.relative_to(research_index_path.parent.parent.parent)),
            'research_index_sha1': research_index_hash,
        },
        'counts': {
            'total_decisions': total_decisions,
            'keep_decisions': keep_decisions,
            'num_legs_final': len(legs),
            'symbols_breakdown': symbols_breakdown,
        },
        'warnings': {
            'missing_run_ids': missing_run_ids,
        }
    }


def _calculate_file_hash(file_path: Path) -> str:
    """Calculate SHA1 hash of a file."""
    if not file_path.exists():
        return ""
    
    hasher = hashlib.sha1()
    with open(file_path, 'rb') as f:
        for chunk in iter(lambda: f.read(4096), b''):
            hasher.update(chunk)
    return hasher.hexdigest()


