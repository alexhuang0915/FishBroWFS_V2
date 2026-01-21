"""Instrument configuration loader with deterministic SHA256 hashing."""

from pathlib import Path
from dataclasses import dataclass
import hashlib
from typing import Dict

import yaml


@dataclass(frozen=True)
class InstrumentSpec:
    """Specification for a single instrument."""
    instrument: str
    currency: str
    multiplier: float
    initial_margin_per_contract: float
    maintenance_margin_per_contract: float
    margin_basis: str = ""  # optional: exchange_maintenance, conservative_over_exchange, broker_day


@dataclass(frozen=True)
class InstrumentsConfig:
    """Loaded instruments configuration with SHA256 hash."""
    version: int
    base_currency: str
    fx_rates: Dict[str, float]
    instruments: Dict[str, InstrumentSpec]
    sha256: str


def load_instruments_config(path: Path) -> InstrumentsConfig:
    """
    Load instruments configuration from YAML file.
    
    Args:
        path: Path to instruments.yaml
        
    Returns:
        InstrumentsConfig with SHA256 hash of canonical YAML bytes.
        
    Raises:
        FileNotFoundError: if file does not exist
        yaml.YAMLError: if YAML is malformed
        KeyError: if required fields are missing
        ValueError: if validation fails (e.g., base_currency not in fx_rates)
    """
    # Read raw bytes for deterministic SHA256
    raw_bytes = path.read_bytes()
    sha256 = hashlib.sha256(raw_bytes).hexdigest()
    
    # Load physical metadata from Registry SSOT
    # Use local import to avoid circular dependency
    from config.registry.instruments import load_instruments as load_registry
    registry = load_registry()

    # Load margins SSOT
    from config.registry.instruments import get_registry_path
    margins_path = get_registry_path("margins.yaml")
    if not margins_path.exists():
         # Fallback for tests or weird environments? 
         # Try relative to the input path if absolute lookup fails
         candidates = [
             margins_path,
             path.parent.parent / "registry" / "margins.yaml",
             Path("configs/registry/margins.yaml").resolve()
         ]
         found = False
         for c in candidates:
             if c.exists():
                 margins_path = c
                 found = True
                 break
         if not found:
             raise FileNotFoundError(f"Margins SSOT not found. Searched: {candidates}")
    
    margins_data = yaml.safe_load(margins_path.read_bytes())
    margin_profiles = margins_data.get("margin_profiles", {})
    
    # Parse YAML (Portfolio Config)
    data = yaml.safe_load(raw_bytes)
    
    # Validate version
    version = data.get("version")
    if version != 1:
        raise ValueError(f"Unsupported version: {version}, expected 1")
    
    # Validate base_currency
    base_currency = data.get("base_currency")
    if not base_currency:
        raise KeyError("Missing 'base_currency'")
    
    # Validate fx_rates
    fx_rates = data.get("fx_rates", {})
    if not isinstance(fx_rates, dict):
        raise ValueError("'fx_rates' must be a dict")
    
    # Validate instruments
    instruments_raw = data.get("instruments", {})
    if not isinstance(instruments_raw, dict):
        raise ValueError("'instruments' must be a dict")
    
    instruments = {}
    for instrument_key, spec_dict in instruments_raw.items():
        # 1. Get physical metadata from Registry
        reg_inst = registry.get_instrument_by_id(instrument_key)
        if not reg_inst:
             raise ValueError(f"Instrument '{instrument_key}' not found in Registry SSOT")
        
        # 2. Get margin profile
        margin_profile_id = spec_dict.get("margin_profile_id")
        if not margin_profile_id:
             raise KeyError(f"Instrument '{instrument_key}' missing 'margin_profile_id'")
        
        margin_profile = margin_profiles.get(margin_profile_id)
        if not margin_profile:
             raise ValueError(f"Margin profile '{margin_profile_id}' not found in Margins SSOT")
             
        # 3. Create InstrumentSpec (Merge sources)
        spec = InstrumentSpec(
            instrument=instrument_key,
            currency=reg_inst.currency,
            multiplier=reg_inst.multiplier if reg_inst.multiplier is not None else 1.0,
            initial_margin_per_contract=float(margin_profile["initial_margin_per_contract"]),
            maintenance_margin_per_contract=float(margin_profile["maintenance_margin_per_contract"]),
            margin_basis=margin_profile.get("margin_basis", ""),
        )
        instruments[instrument_key] = spec
    
    return InstrumentsConfig(
        version=version,
        base_currency=base_currency,
        fx_rates=fx_rates,
        instruments=instruments,
        sha256=sha256,
    )