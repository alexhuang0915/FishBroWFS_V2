#!/usr/bin/env python3
"""
Generate deterministic feature universe manifest v1.

Outputs JSON with window_sets, feature families G1–G10, variants per family,
window applicability per variant, and implementation source.

This script must be deterministic (byte-identical on rerun) and read-only.
"""

import json
import sys
import inspect
from pathlib import Path
from typing import Dict, List, Any, Set
import numpy as np

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from features.registry import get_default_registry
from features.models import FeatureSpec


def get_module_symbol(func) -> str:
    """Return module.symbol for a function, or None if not a function."""
    if func is None:
        return None
    module = inspect.getmodule(func)
    if module is None:
        return None
    module_name = module.__name__
    # Get function name
    if hasattr(func, '__name__'):
        symbol = func.__name__
    else:
        # fallback
        symbol = str(func)
    return f"{module_name}.{symbol}"


def collect_window_sets(specs: List[FeatureSpec]) -> Dict[str, List[int]]:
    """Return canonical window sets per Config Constitution v1."""
    # Fixed window sets as defined in Constitution
    general = [5, 10, 20, 40, 80, 160, 252]
    stats = [63, 126, 252]
    return {
        "general": general,
        "stats": stats,
    }


def map_family_to_g(family: str) -> str:
    """Map family string to G number (G1–G10)."""
    # Define mapping based on existing families and spec requirements.
    # We merge some families to keep exactly 10 families (including placeholders).
    mapping = {
        "ma": "G1",          # includes ema (merged)
        "ema": "G1",         # merged into ma
        "channel": "G2",     # includes donchian, distance (merged)
        "donchian": "G2",    # merged into channel
        "distance": "G2",    # merged into channel
        "volatility": "G3",
        "percentile": "G4",
        "momentum": "G5",
        "structural": "G6",
        "bb": "G7",
        "atr_channel": "G8",
        "volume": "G9",
        "correlation": "G10",
    }
    # If family not in mapping, assign a placeholder G? but should not happen.
    return mapping.get(family, f"G? ({family})")


def gid_to_canonical_family(g_id: str) -> str:
    """Return canonical family name for a given G ID."""
    mapping = {
        "G1": "ma",
        "G2": "channel",
        "G3": "volatility",
        "G4": "percentile",
        "G5": "momentum",
        "G6": "structural",
        "G7": "bb",
        "G8": "atr_channel",
        "G9": "volume",
        "G10": "correlation",
    }
    return mapping.get(g_id, "unknown")


def generate_manifest() -> Dict[str, Any]:
    """Generate the feature universe manifest."""
    registry = get_default_registry()
    specs = registry.specs
    # Sort specs deterministically by (family, name, timeframe_min)
    specs_sorted = sorted(specs, key=lambda s: (s.family or "", s.name, s.timeframe_min))
    
    window_sets = collect_window_sets(specs)
    
    # Group specs by family first (to preserve original family grouping)
    families: Dict[str, List[FeatureSpec]] = {}
    for spec in specs_sorted:
        family = spec.family or "unknown"
        families.setdefault(family, []).append(spec)
    
    # Now group by G ID, merging families that map to same G ID
    groups_by_gid: Dict[str, Dict[str, Any]] = {}
    for family, family_specs in families.items():
        g_id = map_family_to_g(family)
        if g_id not in groups_by_gid:
            # Determine canonical family name for this G ID
            canonical_family = gid_to_canonical_family(g_id)
            groups_by_gid[g_id] = {
                "id": g_id,
                "family": canonical_family,
                "variants": [],
            }
        # Add variants from this family
        for spec in family_specs:
            variant = {
                "name": spec.name,
                "timeframe_min": spec.timeframe_min,
                "window": spec.window,
                "lookback_bars": spec.lookback_bars,
                "params": spec.params,
                "window_applicability": {
                    "general": spec.window in window_sets["general"],
                    "stats": spec.window in window_sets["stats"],
                },
                "implementation_source": get_module_symbol(spec.compute_func),
            }
            groups_by_gid[g_id]["variants"].append(variant)
    
    # Convert to list
    families_list = list(groups_by_gid.values())
    
    # Sort variants within each group by name, timeframe_min for determinism
    for group in families_list:
        group["variants"].sort(key=lambda v: (v["name"], v["timeframe_min"]))
    
    # Add placeholder families for G6, G9, G10 if not present
    existing_g_ids = {f["id"] for f in families_list}
    if "G6" not in existing_g_ids:
        families_list.append({
            "id": "G6",
            "family": "structural",
            "variants": [],
            "note": "Placeholder for daily_pivot, swing_high(N), swing_low(N) (to be implemented)",
        })
    if "G9" not in existing_g_ids:
        families_list.append({
            "id": "G9",
            "family": "volume",
            "variants": [],
            "note": "Placeholder for vol_sma_ratio, obv_slope (to be implemented)",
        })
    if "G10" not in existing_g_ids:
        families_list.append({
            "id": "G10",
            "family": "correlation",
            "variants": [],
            "note": "Placeholder for cross-series correlation (to be implemented)",
        })
    
    # Sort families by G id
    families_list.sort(key=lambda f: f["id"])
    
    manifest = {
        "version": "v1",
        "window_sets": window_sets,
        "families": families_list,
        "metadata": {
            "total_features": len(specs),
            "total_families": len(families_list),
            "generated_at": None,  # we'll add timestamp but ensure deterministic? maybe omit
        }
    }
    return manifest


def main():
    output_dir = Path(__file__).parent.parent / "outputs" / "_dp_evidence" / "feature_universe_manifest_v1"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "feature_universe_manifest_v1.json"
    
    manifest = generate_manifest()
    
    # Ensure deterministic JSON output (sorted keys, no extra whitespace)
    json_str = json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False)
    # Add newline at end
    json_str += "\n"
    
    output_path.write_text(json_str, encoding="utf-8")
    print(f"Manifest written to {output_path}")
    print(f"Total features: {manifest['metadata']['total_features']}")
    print(f"Total families: {manifest['metadata']['total_families']}")


if __name__ == "__main__":
    main()