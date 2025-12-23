"""Signal series writer for portfolio artifacts."""

import json
from pathlib import Path
from typing import Dict, Any
import pandas as pd

from FishBroWFS_V2.core.schemas.portfolio import SignalSeriesMetaV1
from FishBroWFS_V2.portfolio.instruments import load_instruments_config, InstrumentSpec
from FishBroWFS_V2.engine.signal_exporter import build_signal_series_v1


def write_signal_series_artifacts(
    *,
    run_dir: Path,
    instrument: str,
    bars_df: pd.DataFrame,
    fills_df: pd.DataFrame,
    timeframe: str,
    tz: str,
    source_run_id: str,
    source_spec_sha: str,
    instruments_config_path: Path = Path("configs/portfolio/instruments.yaml"),
) -> None:
    """
    Write signal series artifacts (signal_series.parquet and signal_series_meta.json).
    
    Args:
        run_dir: Run directory where artifacts will be written
        instrument: Instrument identifier (e.g., "CME.MNQ")
        bars_df: DataFrame with columns ['ts', 'close']; must be sorted ascending by ts
        fills_df: DataFrame with columns ['ts', 'qty']; qty is signed contracts
        timeframe: Bar timeframe (e.g., "5min")
        tz: Timezone string (e.g., "UTC")
        source_run_id: Source run ID for traceability
        source_spec_sha: Source spec SHA for traceability
        instruments_config_path: Path to instruments.yaml config
        
    Raises:
        FileNotFoundError: If instruments config not found
        KeyError: If instrument not found in config
        ValueError: If input validation fails
    """
    # Load instruments config
    cfg = load_instruments_config(instruments_config_path)
    spec = cfg.instruments.get(instrument)
    if spec is None:
        raise KeyError(f"Instrument '{instrument}' not found in instruments config")
    
    # Get FX rate
    fx_to_base = cfg.fx_rates[spec.currency]
    
    # Build signal series DataFrame
    df = build_signal_series_v1(
        instrument=instrument,
        bars_df=bars_df,
        fills_df=fills_df,
        timeframe=timeframe,
        tz=tz,
        base_currency=cfg.base_currency,
        instrument_currency=spec.currency,
        fx_to_base=fx_to_base,
        multiplier=spec.multiplier,
        initial_margin_per_contract=spec.initial_margin_per_contract,
        maintenance_margin_per_contract=spec.maintenance_margin_per_contract,
    )
    
    # Write signal_series.parquet
    parquet_path = run_dir / "signal_series.parquet"
    df.to_parquet(parquet_path, index=False)
    
    # Build metadata
    meta = SignalSeriesMetaV1(
        schema="SIGNAL_SERIES_V1",
        instrument=instrument,
        timeframe=timeframe,
        tz=tz,
        base_currency=cfg.base_currency,
        instrument_currency=spec.currency,
        fx_to_base=fx_to_base,
        multiplier=spec.multiplier,
        initial_margin_per_contract=spec.initial_margin_per_contract,
        maintenance_margin_per_contract=spec.maintenance_margin_per_contract,
        source_run_id=source_run_id,
        source_spec_sha=source_spec_sha,
        instruments_config_sha256=cfg.sha256,
    )
    
    # Write signal_series_meta.json
    meta_path = run_dir / "signal_series_meta.json"
    meta_dict = meta.dict()
    meta_path.write_text(
        json.dumps(meta_dict, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    
    # Update manifest to include signal series files
    manifest_path = run_dir / "manifest.json"
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            # Add signal series artifacts to manifest
            if "signal_series_artifacts" not in manifest:
                manifest["signal_series_artifacts"] = []
            manifest["signal_series_artifacts"].extend([
                {
                    "path": "signal_series.parquet",
                    "type": "parquet",
                    "schema": "SIGNAL_SERIES_V1",
                },
                {
                    "path": "signal_series_meta.json",
                    "type": "json",
                    "schema": "SIGNAL_SERIES_V1",
                }
            ])
            # Write updated manifest
            manifest_path.write_text(
                json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                encoding="utf-8",
            )
        except Exception as e:
            # Don't fail if manifest update fails, just log
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"Failed to update manifest with signal series artifacts: {e}")