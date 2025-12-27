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
    
    # Parse YAML
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
    if base_currency not in fx_rates:
        raise ValueError(f"base_currency '{base_currency}' must be present in fx_rates")
    if fx_rates.get(base_currency) != 1.0:
        raise ValueError(f"fx_rates[{base_currency}] must be 1.0")
    
    # Validate instruments
    instruments_raw = data.get("instruments", {})
    if not isinstance(instruments_raw, dict):
        raise ValueError("'instruments' must be a dict")
    
    instruments = {}
    for instrument_key, spec_dict in instruments_raw.items():
        # Validate required fields
        required = ["currency", "multiplier", "initial_margin_per_contract", "maintenance_margin_per_contract"]
        for field in required:
            if field not in spec_dict:
                raise KeyError(f"Instrument '{instrument_key}' missing field '{field}'")
        
        # Validate currency exists in fx_rates
        currency = spec_dict["currency"]
        if currency not in fx_rates:
            raise ValueError(f"Instrument '{instrument_key}' currency '{currency}' not in fx_rates")
        
        # Create InstrumentSpec
        spec = InstrumentSpec(
            instrument=instrument_key,
            currency=currency,
            multiplier=float(spec_dict["multiplier"]),
            initial_margin_per_contract=float(spec_dict["initial_margin_per_contract"]),
            maintenance_margin_per_contract=float(spec_dict["maintenance_margin_per_contract"]),
            margin_basis=spec_dict.get("margin_basis", ""),
        )
        instruments[instrument_key] = spec
    
    return InstrumentsConfig(
        version=version,
        base_currency=base_currency,
        fx_rates=fx_rates,
        instruments=instruments,
        sha256=sha256,
    )