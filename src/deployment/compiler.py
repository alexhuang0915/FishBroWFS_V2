#!/usr/bin/env python3
"""
Portfolio Compilation – Phase 3C.

Compile a frozen Season Manifest into deployment TXT files for MultiCharts.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Dict, List, Any, Optional

from governance.models import SeasonManifest
from portfolio.spec import PortfolioSpec, PortfolioLeg
from control.deploy_txt import write_deployment_txt


def parse_timeframe_to_minutes(timeframe_str: str) -> int:
    """
    Convert timeframe string (e.g., '60m', '15m', '1D') to minutes.

    Supports:
    - 'Nm' where N is integer minutes.
    - 'ND' where N is integer days (converted to minutes: N * 24 * 60).
    - 'NH' where N is integer hours (converted to minutes: N * 60).

    Raises ValueError if format unrecognized.
    """
    timeframe_str = timeframe_str.strip()
    # Pattern: integer followed by unit
    match = re.match(r"^(\d+)([mDhH])$", timeframe_str)
    if not match:
        raise ValueError(f"Unsupported timeframe format: {timeframe_str}")

    value = int(match.group(1))
    unit = match.group(2).lower()

    if unit == "m":
        return value
    elif unit == "h":
        return value * 60
    elif unit == "d":
        return value * 24 * 60
    else:
        raise ValueError(f"Unknown timeframe unit: {unit}")


def load_universe_spec(universe_path: Path) -> Dict[str, Dict[str, Any]]:
    """
    Load universe YAML and convert to deploy_txt compatible format.

    Expected YAML structure (from configs/portfolio/instruments.yaml):
        instruments:
          SYMBOL:
            tick_size: float
            multiplier: float
            ...

    Returns dict mapping symbol to dict with keys:
        tick_size, multiplier, commission_per_side_usd, session_profile
    """
    import yaml

    with open(universe_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    instruments = data.get("instruments", {})
    universe_spec = {}

    for symbol, spec in instruments.items():
        # Extract tick_size and multiplier (required)
        tick_size = spec.get("tick_size", 0.25)
        multiplier = spec.get("multiplier", 1.0)

        # Commission per side not defined in instruments.yaml; default 0.0
        commission_per_side_usd = spec.get("commission_per_side_usd", 0.0)

        # Session profile: infer from exchange field or default to symbol's exchange part
        session_profile = spec.get("session_profile", None)
        if session_profile is None:
            # Try to extract exchange from symbol (e.g., "CME.MNQ" -> "CME")
            exchange = symbol.split(".")[0] if "." in symbol else symbol
            session_profile = exchange

        universe_spec[symbol] = {
            "tick_size": tick_size,
            "multiplier": multiplier,
            "commission_per_side_usd": commission_per_side_usd,
            "session_profile": session_profile,
        }

    return universe_spec


def candidate_to_leg(candidate: Dict[str, Any]) -> PortfolioLeg:
    """Convert a candidate from chosen_params snapshot to a PortfolioLeg."""
    candidate_id = candidate["candidate_id"]
    strategy_id = candidate["strategy_id"]
    symbol = candidate["symbol"]
    timeframe_str = candidate["timeframe"]
    params = candidate["params"]

    # Convert timeframe to minutes
    timeframe_min = parse_timeframe_to_minutes(timeframe_str)

    # Determine session profile from symbol exchange (will be overridden later)
    # Use placeholder; will be replaced by universe spec mapping.
    session_profile = symbol.split(".")[0] if "." in symbol else symbol

    # Strategy version: not present in candidate; default to "v1"
    strategy_version = "v1"

    # Ensure params values are float (they may be int)
    float_params = {k: float(v) for k, v in params.items()}

    return PortfolioLeg(
        leg_id=candidate_id,
        symbol=symbol,
        timeframe_min=timeframe_min,
        session_profile=session_profile,
        strategy_id=strategy_id,
        strategy_version=strategy_version,
        params=float_params,
        enabled=True,
    )


def compile_season(manifest_path: Path, output_dir: Path) -> None:
    """
    Compile a frozen season manifest into deployment TXT files.

    Steps:
    1. Load SeasonManifest from manifest_path.
    2. Extract chosen_params_snapshot (main + backups).
    3. Build PortfolioSpec from candidates.
    4. Load universe spec from referenced universe.yaml (must exist in season references).
    5. Write deployment TXT files using write_deployment_txt.

    Constraints:
    - All information must come from the manifest and its referenced files.
    - No direct reading of data/ or strategies/ directories.

    Raises:
        FileNotFoundError: If manifest or referenced universe file missing.
        ValueError: If any required data is missing or malformed.
    """
    # 1. Load manifest
    manifest = SeasonManifest.load(manifest_path)
    season_id = manifest.season_id

    # 2. Extract candidates
    chosen = manifest.chosen_params_snapshot
    main = chosen.get("main")
    backups = chosen.get("backups", [])

    if not main:
        raise ValueError("Chosen params snapshot missing 'main' candidate")

    candidates = [main] + backups

    # 3. Build portfolio legs
    legs: List[PortfolioLeg] = []
    for cand in candidates:
        legs.append(candidate_to_leg(cand))

    # 4. Build portfolio spec
    portfolio_spec = PortfolioSpec(
        portfolio_id=f"season_{season_id}",
        version=season_id,
        legs=legs,
    )

    # 5. Locate universe file (should be in season references)
    season_dir = manifest_path.parent.parent  # outputs/seasons/{season_id}
    universe_path = season_dir / "references" / "universe.yaml"
    if not universe_path.exists():
        # Fallback to configs/portfolio/instruments.yaml (should have been referenced)
        universe_path = Path("configs/portfolio/instruments.yaml")
        if not universe_path.exists():
            raise FileNotFoundError(
                f"Universe file not found in season references or configs: {universe_path}"
            )

    universe_spec = load_universe_spec(universe_path)

    # Ensure all symbols in portfolio have a universe entry
    missing_symbols = set(leg.symbol for leg in legs) - set(universe_spec.keys())
    if missing_symbols:
        raise ValueError(
            f"Universe spec missing entries for symbols: {missing_symbols}"
        )

    # 6. Write deployment TXT files
    output_dir.mkdir(parents=True, exist_ok=True)
    write_deployment_txt(portfolio_spec, universe_spec, output_dir)

    # 7. Validate non‑empty output files
    required_files = ["universe.txt", "strategy_params.txt", "portfolio.txt"]
    for fname in required_files:
        fpath = output_dir / fname
        if not fpath.exists():
            raise RuntimeError(f"Deployment file not created: {fpath}")
        if fpath.stat().st_size == 0:
            raise RuntimeError(f"Deployment file is empty: {fpath}")

    print(f"Deployment Pack ready at: {output_dir}")


def main_cli() -> None:
    """CLI entry point."""
    import argparse
    import sys

    parser = argparse.ArgumentParser(
        description="Compile a frozen Season Manifest into deployment TXT files"
    )
    parser.add_argument(
        "manifest",
        type=Path,
        help="Path to season_manifest.json",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Output directory (default: outputs/deployment/{season_id})",
    )

    args = parser.parse_args()

    if not args.manifest.exists():
        print(f"Error: Manifest file not found: {args.manifest}", file=sys.stderr)
        sys.exit(1)

    # Determine output directory
    if args.output_dir is None:
        manifest = SeasonManifest.load(args.manifest)
        output_dir = Path("outputs") / "deployment" / manifest.season_id
    else:
        output_dir = args.output_dir

    try:
        compile_season(args.manifest, output_dir)
    except Exception as e:
        print(f"Compilation failed: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main_cli()