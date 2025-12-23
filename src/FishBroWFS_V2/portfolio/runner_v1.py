"""Portfolio runner V1 - assembles candidate signals from artifacts."""

import logging
from pathlib import Path
from typing import List, Dict, Optional, Tuple
import pandas as pd

from FishBroWFS_V2.core.schemas.portfolio_v1 import (
    PortfolioPolicyV1,
    PortfolioSpecV1,
    SignalCandidateV1,
    OpenPositionV1,
)
from FishBroWFS_V2.portfolio.engine_v1 import PortfolioEngineV1
from FishBroWFS_V2.portfolio.instruments import load_instruments_config

logger = logging.getLogger(__name__)


def detect_entry_events(signal_series_df: pd.DataFrame) -> pd.DataFrame:
    """
    Detect entry events from signal series.
    
    Entry event: position_contracts changes from 0 to non-zero.
    
    Args:
        signal_series_df: DataFrame from signal_series.parquet
        
    Returns:
        DataFrame with entry events only
    """
    if signal_series_df.empty:
        return pd.DataFrame()
    
    # Ensure sorted by ts
    df = signal_series_df.sort_values("ts").reset_index(drop=True)
    
    # Detect position changes
    df["position_change"] = df["position_contracts"].diff()
    
    # First row special case
    if len(df) > 0:
        # If first position is non-zero, it's an entry
        if df.loc[0, "position_contracts"] != 0:
            df.loc[0, "position_change"] = df.loc[0, "position_contracts"]
    
    # Entry events: position_change > 0 (long) or < 0 (short)
    # For v1, we treat both as entry events
    entry_mask = df["position_change"] != 0
    
    return df[entry_mask].copy()


def load_signal_series(
    outputs_root: Path,
    season: str,
    strategy_id: str,
    instrument_id: str,
) -> Optional[pd.DataFrame]:
    """
    Load signal series parquet for a strategy.
    
    Path pattern: outputs/{season}/runs/.../artifacts/signal_series.parquet
    This is a simplified version - actual path may vary.
    """
    # Try to find the signal series file
    # This is a placeholder - actual implementation needs to find the correct run directory
    pattern = f"**/{strategy_id}/**/signal_series.parquet"
    matches = list(outputs_root.glob(pattern))
    
    if not matches:
        logger.warning(f"No signal series found for {strategy_id}/{instrument_id} in {season}")
        return None
    
    # Use first match
    parquet_path = matches[0]
    try:
        df = pd.read_parquet(parquet_path)
        # Filter by instrument if needed
        if "instrument" in df.columns:
            df = df[df["instrument"] == instrument_id].copy()
        return df
    except Exception as e:
        logger.error(f"Failed to load {parquet_path}: {e}")
        return None


def assemble_candidates(
    spec: PortfolioSpecV1,
    outputs_root: Path,
    instruments_config_path: Path = Path("configs/portfolio/instruments.yaml"),
) -> List[SignalCandidateV1]:
    """
    Assemble candidate signals from frozen seasons.
    
    Args:
        spec: Portfolio specification
        outputs_root: Root outputs directory
        instruments_config_path: Path to instruments config
        
    Returns:
        List of candidate signals
    """
    # Load instruments config for margin calculations
    instruments_cfg = load_instruments_config(instruments_config_path)
    
    candidates = []
    
    for season in spec.seasons:
        for strategy_id in spec.strategy_ids:
            for instrument_id in spec.instrument_ids:
                # Load signal series
                df = load_signal_series(
                    outputs_root / season,
                    season,
                    strategy_id,
                    instrument_id,
                )
                
                if df is None or df.empty:
                    continue
                
                # Detect entry events
                entry_events = detect_entry_events(df)
                
                if entry_events.empty:
                    continue
                
                # Get instrument spec for margin calculation
                instrument_spec = instruments_cfg.instruments.get(instrument_id)
                if instrument_spec is None:
                    logger.warning(f"Instrument {instrument_id} not found in config, skipping")
                    continue
                
                # Try to load metadata for candidate_score
                candidate_score = 0.0
                # Look for score in metadata files
                # This is a simplified implementation - actual implementation would need to
                # locate and parse the appropriate metadata file
                # For v1, we'll use a placeholder approach
                
                # Create candidates from entry events
                for _, row in entry_events.iterrows():
                    # Calculate required margin
                    # For v1: use margin_initial_base from the signal series
                    # If not available, estimate from position * margin_per_contract * fx
                    if "margin_initial_base" in row:
                        required_margin = abs(row["margin_initial_base"])
                    else:
                        # Estimate conservatively
                        position = abs(row["position_contracts"])
                        required_margin = (
                            position
                            * instrument_spec.initial_margin_per_contract
                            * instruments_cfg.fx_rates[instrument_spec.currency]
                        )
                    
                    # Get signal strength (use close as placeholder if not available)
                    signal_strength = 1.0  # Default
                    if "signal_strength" in row:
                        signal_strength = row["signal_strength"]
                    elif "close" in row:
                        # Use normalized close as proxy (simplified)
                        signal_strength = row["close"] / 10000.0
                    
                    candidate = SignalCandidateV1(
                        strategy_id=strategy_id,
                        instrument_id=instrument_id,
                        bar_ts=row["ts"],
                        bar_index=int(row.name) if "index" in row else 0,
                        signal_strength=float(signal_strength),
                        candidate_score=float(candidate_score),  # v1: default 0.0
                        required_margin_base=float(required_margin),
                        required_slot=1,  # v1 fixed
                    )
                    candidates.append(candidate)
    
    # Sort by bar_ts for chronological processing
    candidates.sort(key=lambda c: c.bar_ts)
    
    logger.info(f"Assembled {len(candidates)} candidates from {len(spec.seasons)} seasons")
    return candidates


def run_portfolio_admission(
    policy: PortfolioPolicyV1,
    spec: PortfolioSpecV1,
    equity_base: float,
    outputs_root: Path,
    replay_mode: bool = False,
) -> Tuple[List[SignalCandidateV1], List[OpenPositionV1], Dict]:
    """
    Run portfolio admission process.
    
    Args:
        policy: Portfolio policy
        spec: Portfolio specification
        equity_base: Initial equity in base currency
        outputs_root: Root outputs directory
        replay_mode: If True, read-only mode (no writes)
        
    Returns:
        Tuple of (candidates, final_open_positions, results_dict)
    """
    logger.info(f"Starting portfolio admission (replay={replay_mode})")
    
    # Assemble candidates
    candidates = assemble_candidates(spec, outputs_root)
    
    if not candidates:
        logger.warning("No candidates found")
        return [], [], {}
    
    # Group candidates by bar for sequential processing
    candidates_by_bar: Dict[Tuple, List[SignalCandidateV1]] = {}
    for candidate in candidates:
        key = (candidate.bar_index, candidate.bar_ts)
        candidates_by_bar.setdefault(key, []).append(candidate)
    
    # Initialize engine
    engine = PortfolioEngineV1(policy, equity_base)
    
    # Process bars in chronological order
    for (bar_index, bar_ts), bar_candidates in sorted(candidates_by_bar.items()):
        engine.admit_candidates(bar_candidates)
    
    # Get results
    decisions = engine.decisions
    final_positions = engine.open_positions
    summary = engine.get_summary()
    
    logger.info(
        f"Portfolio admission completed: "
        f"{summary.accepted_count} accepted, "
        f"{summary.rejected_count} rejected, "
        f"final slots={summary.final_slots_used}, "
        f"margin ratio={summary.final_margin_ratio:.2%}"
    )
    
    results = {
        "decisions": decisions,
        "summary": summary,
        "bar_states": engine.bar_states,
    }
    
    return candidates, final_positions, results


def validate_portfolio_spec(spec: PortfolioSpecV1, outputs_root: Path) -> List[str]:
    """
    Validate portfolio specification.
    
    Returns:
        List of validation errors (empty if valid)
    """
    errors = []
    
    # Check seasons exist
    for season in spec.seasons:
        season_dir = outputs_root / season
        if not season_dir.exists():
            errors.append(f"Season directory not found: {season_dir}")
    
    # Check instruments config SHA256
    # This would need to be implemented based on actual config loading
    
    # Check resource estimate (simplified)
    total_candidates_estimate = len(spec.seasons) * len(spec.strategy_ids) * len(spec.instrument_ids) * 1000
    if total_candidates_estimate > 100000:
        errors.append(f"Large resource estimate: ~{total_candidates_estimate} candidates")
    
    return errors