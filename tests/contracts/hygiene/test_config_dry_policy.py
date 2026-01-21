"""
Config DRY Policy Tests (Config Constitution Part 2)

Enforces CONFIG_DRY_CONTRACT_V1.md:
1. Registry is the SSOT for instrument physical metadata.
2. Profiles MUST NOT redefine physical metadata.
3. Portfolio specs MUST NOT define instruments/profiles or physical metadata.
"""

import pytest
from pathlib import Path
import yaml

# Defines what makes an instrument an instrument (Physical Metadata)
# These fields belong ONLY in Registry.
PHYSICAL_METADATA_FIELDS = {
    "multiplier",
    "tick_size",
    "tick_value",
    "currency",
    "exchange",
    "type",  # e.g., future
    "display_name",
}

def load_yaml(path: Path):
    if not path.exists():
        pytest.fail(f"Config file not found: {path}")
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def test_profiles_do_not_redefine_physical_metadata():
    """Profiles cannot redefine physical instrument traits (currency, tick_size, etc.)."""
    repo_root = Path(__file__).resolve().parents[3]
    profiles_dir = repo_root / "configs" / "profiles"
    
    if not profiles_dir.exists():
        return

    # Scan all profile yamls
    profiles = list(profiles_dir.glob("*.yaml")) + list(profiles_dir.glob("*.yml"))
    
    violations = []
    
    for p in profiles:
        data = load_yaml(p)
        if not data:
            continue
            
        # Check top-level keys for forbidden metadata
        found_forbidden = []
        for key in data.keys():
            if key in PHYSICAL_METADATA_FIELDS:
                found_forbidden.append(key)
        
        if found_forbidden:
            violations.append(f"{p.name} defines forbidden fields: {found_forbidden}")

    assert not violations, (
        "Profiles violate CONFIG_DRY_CONTRACT_V1 by redefining physical metadata:\n" +
        "\n".join(violations)
    )


def test_portfolio_specs_are_dry():
    """Portfolio specs cannot define instruments or profiles inline."""
    repo_root = Path(__file__).resolve().parents[3]
    portfolio_dir = repo_root / "configs" / "portfolio"
    
    if not portfolio_dir.exists():
        return

    # Scan all portfolio yamls
    portfolios = list(portfolio_dir.glob("*.yaml")) + list(portfolio_dir.glob("*.yml"))
    
    forbidden_blocks = {"instruments", "profiles", "instrument_definitions"}
    
    violations = []
    
    for p in portfolios:
        data = load_yaml(p)
        if not data:
            continue
            
        # SPECIAL CASE: instruments.yaml/instruments.yml in portfolio/
        # This is a legacy Margin/Risk config.
        # It IS allowed to have 'instruments' block.
        # It IS allowed to have 'multiplier' and 'currency' (for now).
        # It MUST NOT have 'tick_size', 'tick_value', 'display_name', 'type', 'exchange'.
        is_legacy_margin = p.name in ("instruments.yaml", "instruments.yml")
        
        # Check for forbidden blocks
        found_blocks = []
        for key in data.keys():
            if is_legacy_margin and key == "instruments":
                continue # Allowed for legacy file
            if key in forbidden_blocks:
                found_blocks.append(key)
        
        if found_blocks:
            violations.append(f"{p.name} contains forbidden definition blocks: {found_blocks}")

        # Check for inline keys in top level
        # For legacy margin file, we strictly check the content of 'instruments' block if it exists
        if is_legacy_margin and "instruments" in data:
            # Check inside the instruments block
            for inst_id, spec in data["instruments"].items():
                if not isinstance(spec, dict): continue
                for key in spec.keys():
                    # Forbidden physical metadata in legacy file
                    # We NO LONGER allow multiplier/currency (Stage B)
                    forbidden_legacy = {
                        "tick_size", "tick_value", "display_name", "type", "exchange",
                        "multiplier", "currency",
                        "initial_margin_per_contract", "maintenance_margin_per_contract",
                        "margin_basis"
                    }
                    if key in forbidden_legacy:
                        violations.append(f"{p.name} instrument '{inst_id}' defines forbidden field: {key}")
                    
                    # Must have margin_profile_id
                    if "margin_profile_id" not in spec:
                         violations.append(f"{p.name} instrument '{inst_id}' missing 'margin_profile_id'")
        
        # For non-legacy files, or top level of legacy file
        found_metadata = []
        for key in data.keys():
            if key in PHYSICAL_METADATA_FIELDS:
                 # Legacy file allowed top-level metadata? No, it uses 'instruments' block.
                 found_metadata.append(key)

        if found_metadata:
            violations.append(f"{p.name} contains forbidden metadata fields: {found_metadata}")

    assert not violations, (
        "Portfolio specs violate CONFIG_DRY_CONTRACT_V1:\n" +
        "\n".join(violations)
    )

def test_all_profile_symbols_exist_in_registry():
    """Profiles must reference valid Registry IDs (SSOT)."""
    repo_root = Path(__file__).resolve().parents[3]
    registry_path = repo_root / "configs" / "registry" / "instruments.yaml"
    profiles_dir = repo_root / "configs" / "profiles"
    
    if not registry_path.exists() or not profiles_dir.exists():
        return # Skip if incomplete env
        
    registry_data = load_yaml(registry_path)
    registry_ids = set()
    if registry_data and "instruments" in registry_data:
        for inst in registry_data["instruments"]:
            if "id" in inst:
                registry_ids.add(inst["id"])
    
    violations = []
    
    profiles = list(profiles_dir.glob("*.yaml")) + list(profiles_dir.glob("*.yml"))
    for p in profiles:
        data = load_yaml(p)
        if not data:
            continue
            
        symbol = data.get("symbol")
        if not symbol:
            violations.append(f"{p.name} missing 'symbol' field")
            continue
            
        if symbol not in registry_ids:
            violations.append(f"{p.name} references unknown symbol '{symbol}' (not in Registry)")
            
    assert not violations, (
        "Profiles reference unknown symbols (must exist in configs/registry/instruments.yaml):\n" +
        "\n".join(violations)
    )
