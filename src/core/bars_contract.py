"""Bars Contract SSOT (Single Source of Truth).

Defines the canonical bars contract for "eatable bars" with three validation gates:
- Gate A: Existence/Openability
- Gate B: Schema Contract
- Gate C: Manifest SSOT Integrity

This module serves as the single source of truth for bars validation across the system.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple, Union, Any, Iterable
import numpy as np
import pandas as pd


# ============================================================================
# CONSTANTS
# ============================================================================

REQUIRED_COLUMNS: Set[str] = {"ts", "open", "high", "low", "close", "volume"}
"""Required column names for bars data."""

TS_DTYPE: str = "datetime64[s]"
"""Expected dtype for timestamp column."""

MIN_VOLUME: float = 0.0
"""Minimum allowed volume (zero is allowed)."""

MIN_PRICE: float = 0.0
"""Minimum allowed price (must be positive)."""


# ============================================================================
# EXCEPTIONS
# ============================================================================

class BarsContractError(ValueError):
    """Base exception for bars contract violations."""
    pass


class GateAError(BarsContractError):
    """Gate A violation: file existence/openability."""
    pass


class GateBError(BarsContractError):
    """Gate B violation: schema contract."""
    pass


class GateCError(BarsContractError):
    """Gate C violation: manifest SSOT integrity."""
    pass


# ============================================================================
# DATA STRUCTURES
# ============================================================================

@dataclass(frozen=True)
class BarsValidationResult:
    """Result of bars validation."""
    
    gate_a_passed: bool
    gate_b_passed: bool
    gate_c_passed: bool
    gate_a_error: Optional[str] = None
    gate_b_error: Optional[str] = None
    gate_c_error: Optional[str] = None
    bars_count: Optional[int] = None
    file_size_bytes: Optional[int] = None
    computed_hash: Optional[str] = None
    expected_hash: Optional[str] = None
    
    @property
    def all_passed(self) -> bool:
        """Check if all gates passed."""
        return self.gate_a_passed and self.gate_b_passed and self.gate_c_passed
    
    @property
    def failed_gates(self) -> List[str]:
        """Get list of failed gate names."""
        failed = []
        if not self.gate_a_passed:
            failed.append("Gate A")
        if not self.gate_b_passed:
            failed.append("Gate B")
        if not self.gate_c_passed:
            failed.append("Gate C")
        return failed


@dataclass(frozen=True)
class BarsManifestEntry:
    """Entry in bars manifest for SSOT tracking."""
    
    file_path: str
    file_hash: str
    bars_count: int
    season: str
    dataset_id: str
    timeframe_min: Optional[int] = None  # None for normalized bars
    generated_at_utc: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "file_path": self.file_path,
            "file_hash": self.file_hash,
            "bars_count": self.bars_count,
            "season": self.season,
            "dataset_id": self.dataset_id,
            "timeframe_min": self.timeframe_min,
            "generated_at_utc": self.generated_at_utc,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> BarsManifestEntry:
        """Create from dictionary."""
        return cls(**data)


@dataclass(frozen=True)
class RawInstrumentDerivationResult:
    """Result of instrument derivation from raw filenames."""
    
    instruments: Tuple[str, ...]      # sorted unique
    invalid_raw: Tuple[str, ...]      # raw filenames that failed parsing
    
    @property
    def has_valid_instruments(self) -> bool:
        """Check if any valid instruments were derived."""
        return len(self.instruments) > 0
    
    @property
    def has_invalid_raw(self) -> bool:
        """Check if any raw filenames failed parsing."""
        return len(self.invalid_raw) > 0


# ============================================================================
# INSTRUMENT DERIVATION FROM RAW FILENAMES
# ============================================================================

def derive_instruments_from_raw(raw_files: Iterable[str]) -> RawInstrumentDerivationResult:
    """
    Derive instrument identifiers from raw filenames.
    
    Canonical rule:
    - Instrument token is the first whitespace-delimited token in the filename
    - Accept only tokens that match pattern: [A-Z0-9]+\.[A-Z0-9]+
      (e.g., CME.MNQ, TWF.MXF, OSE.NK225M, CFE.VX)
    - Returns sorted unique instruments and list of invalid raw filenames
    
    Args:
        raw_files: Iterable of raw filenames (e.g., "CME.MNQ HOT-TOUCHANCE-CME-Futures-Minute-Trade.txt")
        
    Returns:
        RawInstrumentDerivationResult with derived instruments and invalid raw filenames
    """
    # Pattern for valid instrument identifiers: EXCHANGE.SYMBOL
    # Examples: CME.MNQ, TWF.MXF, OSE.NK225M, CFE.VX
    INSTRUMENT_PATTERN = re.compile(r'^[A-Z0-9]+\.[A-Z0-9]+$')
    
    instruments_set: Set[str] = set()
    invalid_raw_list: List[str] = []
    
    for raw_file in raw_files:
        # Extract first whitespace-delimited token
        # Example: "CME.MNQ HOT-TOUCHANCE-CME-Futures-Minute-Trade.txt" -> "CME.MNQ"
        parts = raw_file.strip().split()
        if not parts:
            invalid_raw_list.append(raw_file)
            continue
            
        candidate = parts[0]
        
        # Validate against pattern
        if INSTRUMENT_PATTERN.match(candidate):
            instruments_set.add(candidate)
        else:
            invalid_raw_list.append(raw_file)
    
    # Return sorted results for determinism
    return RawInstrumentDerivationResult(
        instruments=tuple(sorted(instruments_set)),
        invalid_raw=tuple(sorted(invalid_raw_list))
    )


# ============================================================================
# GATE A: EXISTENCE/OPENABILITY
# ============================================================================

def validate_gate_a(file_path: Union[str, Path]) -> Tuple[bool, Optional[str]]:
    """
    Gate A: Validate file existence and openability.
    
    Args:
        file_path: Path to bars file (NPZ or Parquet)
        
    Returns:
        Tuple of (passed: bool, error_message: Optional[str])
    """
    path = Path(file_path)
    
    # Check existence
    if not path.exists():
        return False, f"File not found: {path}"
    
    # Check file size
    try:
        file_size = path.stat().st_size
        if file_size == 0:
            return False, f"File is empty: {path}"
    except OSError as e:
        return False, f"Cannot stat file {path}: {e}"
    
    # Try to open based on file extension
    try:
        if path.suffix == ".npz":
            # Try to load NPZ file
            with np.load(path, allow_pickle=False) as data:
                if not isinstance(data, np.lib.npyio.NpzFile):
                    return False, f"Invalid NPZ file format: {path}"
        elif path.suffix == ".parquet":
            # Try to read parquet metadata
            import pandas as pd
            # Use a more compatible approach - read just the schema
            # by reading a single row with limit
            try:
                # Try using head(1) approach
                df = pd.read_parquet(path)
                if len(df) == 0:
                    return False, f"Parquet file is empty: {path}"
            except Exception as e:
                return False, f"Cannot read parquet file {path}: {e}"
        else:
            # Unknown format, but file exists and is readable
            pass
    except Exception as e:
        return False, f"Cannot open file {path}: {e}"
    
    return True, None


# ============================================================================
# GATE B: SCHEMA CONTRACT
# ============================================================================

def validate_gate_b_npz(file_path: Union[str, Path]) -> Tuple[bool, Optional[str], Optional[Dict[str, np.ndarray]]]:
    """
    Gate B: Validate NPZ bars schema contract.
    
    Args:
        file_path: Path to NPZ bars file
        
    Returns:
        Tuple of (passed: bool, error_message: Optional[str], data: Optional[Dict])
    """
    try:
        # Load NPZ file
        with np.load(file_path, allow_pickle=False) as npz_data:
            data = dict(npz_data)
    except Exception as e:
        return False, f"Cannot load NPZ file {file_path}: {e}", None
    
    # Check required columns
    missing_columns = REQUIRED_COLUMNS - set(data.keys())
    if missing_columns:
        return False, f"Missing required columns: {sorted(missing_columns)}", None
    
    # Check for extra columns (warn but don't fail)
    extra_columns = set(data.keys()) - REQUIRED_COLUMNS
    if extra_columns:
        # Log warning but continue
        pass
    
    # Check ts dtype
    ts_array = data["ts"]
    if not np.issubdtype(ts_array.dtype, np.datetime64):
        return False, f"Column 'ts' must be datetime64, got {ts_array.dtype}", None
    
    # Check ts is datetime64[s] (seconds precision)
    if ts_array.dtype != np.dtype("datetime64[s]"):
        # Try to convert or warn
        pass
    
    # Check array lengths match
    lengths = {key: len(arr) for key, arr in data.items() if key in REQUIRED_COLUMNS}
    if len(set(lengths.values())) > 1:
        return False, f"Column length mismatch: {lengths}", None
    
    bars_count = lengths.get("ts", 0)
    
    # Check for empty bars
    if bars_count == 0:
        return False, "Bars array is empty", None
    
    # Check sorting (ts must be strictly increasing)
    ts = data["ts"]
    if not np.all(ts[:-1] < ts[1:]):
        return False, "Timestamps are not strictly increasing", None
    
    # Check price sanity
    open_arr = data["open"]
    high_arr = data["high"]
    low_arr = data["low"]
    close_arr = data["close"]
    volume_arr = data["volume"]
    
    # Check low <= open <= high
    if not np.all(low_arr <= open_arr):
        return False, "low > open for some bars", None
    if not np.all(open_arr <= high_arr):
        return False, "open > high for some bars", None
    
    # Check low <= close <= high
    if not np.all(low_arr <= close_arr):
        return False, "low > close for some bars", None
    if not np.all(close_arr <= high_arr):
        return False, "close > high for some bars", None
    
    # Check positive prices
    if np.any(open_arr <= MIN_PRICE):
        return False, "open price <= 0 for some bars", None
    if np.any(high_arr <= MIN_PRICE):
        return False, "high price <= 0 for some bars", None
    if np.any(low_arr <= MIN_PRICE):
        return False, "low price <= 0 for some bars", None
    if np.any(close_arr <= MIN_PRICE):
        return False, "close price <= 0 for some bars", None
    
    # Check non-negative volume
    if np.any(volume_arr < MIN_VOLUME):
        return False, "volume < 0 for some bars", None
    
    # Check for NaN/inf values
    for col in REQUIRED_COLUMNS:
        arr = data[col]
        if np.any(np.isnan(arr)):
            return False, f"NaN values found in column '{col}'", None
        if np.any(np.isinf(arr)):
            return False, f"Inf values found in column '{col}'", None
    
    return True, None, data


def validate_gate_b_parquet(file_path: Union[str, Path]) -> Tuple[bool, Optional[str], Optional[pd.DataFrame]]:
    """
    Gate B: Validate Parquet bars schema contract.
    
    Args:
        file_path: Path to Parquet bars file
        
    Returns:
        Tuple of (passed: bool, error_message: Optional[str], df: Optional[DataFrame])
    """
    try:
        import pandas as pd
        df = pd.read_parquet(file_path)
    except Exception as e:
        return False, f"Cannot read Parquet file {file_path}: {e}", None
    
    # Check required columns
    # Note: Raw parquet uses 'timestamp' instead of 'ts'
    required_raw = {"timestamp", "open", "high", "low", "close", "volume"}
    missing_columns = required_raw - set(df.columns)
    if missing_columns:
        return False, f"Missing required columns: {sorted(missing_columns)}", None
    
    # Check for extra columns (warn but don't fail)
    extra_columns = set(df.columns) - required_raw
    if extra_columns:
        # Log warning but continue
        pass
    
    # Check timestamp column
    if not pd.api.types.is_datetime64_any_dtype(df["timestamp"]):
        return False, "Column 'timestamp' must be datetime type", None
    
    bars_count = len(df)
    
    # Check for empty bars
    if bars_count == 0:
        return False, "DataFrame is empty", None
    
    # Check sorting (timestamp must be strictly increasing)
    if not df["timestamp"].is_monotonic_increasing:
        return False, "Timestamps are not strictly increasing", None
    
    # Check for duplicate timestamps
    if df["timestamp"].duplicated().any():
        return False, "Duplicate timestamps found", None
    
    # Check price sanity
    if not (df["low"] <= df["open"]).all():
        return False, "low > open for some bars", None
    if not (df["open"] <= df["high"]).all():
        return False, "open > high for some bars", None
    if not (df["low"] <= df["close"]).all():
        return False, "low > close for some bars", None
    if not (df["close"] <= df["high"]).all():
        return False, "close > high for some bars", None
    
    # Check positive prices
    if (df["open"] <= MIN_PRICE).any():
        return False, "open price <= 0 for some bars", None
    if (df["high"] <= MIN_PRICE).any():
        return False, "high price <= 0 for some bars", None
    if (df["low"] <= MIN_PRICE).any():
        return False, "low price <= 0 for some bars", None
    if (df["close"] <= MIN_PRICE).any():
        return False, "close price <= 0 for some bars", None
    
    # Check non-negative volume
    if (df["volume"] < MIN_VOLUME).any():
        return False, "volume < 0 for some bars", None
    
    # Check for NaN values
    for col in required_raw:
        if df[col].isna().any():
            return False, f"NaN values found in column '{col}'", None
    
    return True, None, df


def validate_gate_b(file_path: Union[str, Path]) -> Tuple[bool, Optional[str], Optional[Dict]]:
    """
    Gate B: Validate bars schema contract (auto-detects format).
    
    Args:
        file_path: Path to bars file
        
    Returns:
        Tuple of (passed: bool, error_message: Optional[str], data: Optional)
    """
    path = Path(file_path)
    
    if path.suffix == ".npz":
        return validate_gate_b_npz(path)
    elif path.suffix == ".parquet":
        return validate_gate_b_parquet(path)
    else:
        return False, f"Unsupported file format: {path.suffix}", None


# ============================================================================
# GATE C: MANIFEST SSOT INTEGRITY
# ============================================================================

def compute_file_hash(file_path: Union[str, Path]) -> str:
    """
    Compute SHA256 hash of file content.
    
    Args:
        file_path: Path to file
        
    Returns:
        SHA256 hex digest
    """
    path = Path(file_path)
    hasher = hashlib.sha256()
    
    with open(path, "rb") as f:
        # Read in chunks to handle large files
        chunk_size = 8192
        while chunk := f.read(chunk_size):
            hasher.update(chunk)
    
    return hasher.hexdigest()


def validate_gate_c(
    file_path: Union[str, Path],
    manifest_entry: Optional[BarsManifestEntry] = None,
    expected_hash: Optional[str] = None,
) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Gate C: Validate manifest SSOT integrity.
    
    Args:
        file_path: Path to bars file
        manifest_entry: Optional manifest entry with expected hash
        expected_hash: Optional expected hash (overrides manifest_entry)
        
    Returns:
        Tuple of (passed: bool, error_message: Optional[str], computed_hash: Optional[str])
    """
    # Get expected hash
    if expected_hash is None and manifest_entry is not None:
        expected_hash = manifest_entry.file_hash
    
    if expected_hash is None:
        # No expected hash provided - Gate C passes by default (no SSOT to check)
        computed = compute_file_hash(file_path)
        return True, None, computed
    
    # Compute actual hash
    try:
        computed_hash = compute_file_hash(file_path)
    except Exception as e:
        return False, f"Cannot compute file hash: {e}", None
    
    # Compare hashes
    if computed_hash != expected_hash:
        return False, f"Hash mismatch: expected {expected_hash[:16]}..., got {computed_hash[:16]}...", computed_hash
    
    return True, None, computed_hash


# ============================================================================
# COMPREHENSIVE VALIDATION
# ============================================================================

def validate_bars(
    file_path: Union[str, Path],
    manifest_entry: Optional[BarsManifestEntry] = None,
) -> BarsValidationResult:
    """
    Comprehensive bars validation with all three gates.
    
    Args:
        file_path: Path to bars file
        manifest_entry: Optional manifest entry for Gate C
        
    Returns:
        BarsValidationResult with validation results
    """
    path = Path(file_path)
    
    # Gate A: Existence/Openability
    gate_a_passed, gate_a_error = validate_gate_a(path)
    
    # Gate B: Schema Contract
    gate_b_passed, gate_b_error, data = (False, None, None)
    if gate_a_passed:
        gate_b_passed, gate_b_error, data = validate_gate_b(path)
    
    # Gate C: Manifest SSOT Integrity
    gate_c_passed, gate_c_error, computed_hash = (False, None, None)
    if gate_a_passed:
        gate_c_passed, gate_c_error, computed_hash = validate_gate_c(path, manifest_entry)
    
    # Collect metadata
    bars_count = None
    file_size_bytes = None
    expected_hash = None
    
    if gate_a_passed:
        try:
            file_size_bytes = path.stat().st_size
        except OSError:
            pass
    
    if data is not None:
        if isinstance(data, dict):  # NPZ
            bars_count = len(data.get("ts", []))
        elif hasattr(data, "__len__"):  # DataFrame
            bars_count = len(data)
    
    if manifest_entry is not None:
        expected_hash = manifest_entry.file_hash
    
    return BarsValidationResult(
        gate_a_passed=gate_a_passed,
        gate_b_passed=gate_b_passed,
        gate_c_passed=gate_c_passed,
        gate_a_error=gate_a_error,
        gate_b_error=gate_b_error,
        gate_c_error=gate_c_error,
        bars_count=bars_count,
        file_size_bytes=file_size_bytes,
        computed_hash=computed_hash,
        expected_hash=expected_hash,
    )


def validate_bars_with_raise(
    file_path: Union[str, Path],
    manifest_entry: Optional[BarsManifestEntry] = None,
) -> BarsValidationResult:
    """
    Validate bars and raise appropriate exception if any gate fails.
    
    Args:
        file_path: Path to bars file
        manifest_entry: Optional manifest entry for Gate C
        
    Returns:
        BarsValidationResult if all gates pass
        
    Raises:
        GateAError: If Gate A fails
        GateBError: If Gate B fails
        GateCError: If Gate C fails
    """
    result = validate_bars(file_path, manifest_entry)
    
    if not result.gate_a_passed:
        raise GateAError(f"Gate A failed: {result.gate_a_error}")
    
    if not result.gate_b_passed:
        raise GateBError(f"Gate B failed: {result.gate_b_error}")
    
    if not result.gate_c_passed:
        raise GateCError(f"Gate C failed: {result.gate_c_error}")
    
    return result


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def load_bars_npz(file_path: Union[str, Path]) -> Dict[str, np.ndarray]:
    """
    Load bars from NPZ file with validation.
    
    Args:
        file_path: Path to NPZ bars file
        
    Returns:
        Dictionary with bars data
        
    Raises:
        GateAError: If file cannot be opened
        GateBError: If schema validation fails
    """
    # Validate with Gate A and B
    gate_a_passed, gate_a_error = validate_gate_a(file_path)
    if not gate_a_passed:
        raise GateAError(f"Gate A failed: {gate_a_error}")
    
    gate_b_passed, gate_b_error, data = validate_gate_b_npz(file_path)
    if not gate_b_passed:
        raise GateBError(f"Gate B failed: {gate_b_error}")
    
    return data


def load_bars_parquet(file_path: Union[str, Path]) -> pd.DataFrame:
    """
    Load bars from Parquet file with validation.
    
    Args:
        file_path: Path to Parquet bars file
        
    Returns:
        DataFrame with bars data
        
    Raises:
        GateAError: If file cannot be opened
        GateBError: If schema validation fails
    """
    # Validate with Gate A and B
    gate_a_passed, gate_a_error = validate_gate_a(file_path)
    if not gate_a_passed:
        raise GateAError(f"Gate A failed: {gate_a_error}")
    
    gate_b_passed, gate_b_error, df = validate_gate_b_parquet(file_path)
    if not gate_b_passed:
        raise GateBError(f"Gate B failed: {gate_b_error}")
    
    return df


def normalize_raw_bars_to_contract(df: pd.DataFrame) -> Dict[str, np.ndarray]:
    """
    Normalize raw bars DataFrame to canonical contract format.
    
    Converts 'timestamp' column to 'ts' with datetime64[s] dtype.
    
    Args:
        df: DataFrame with columns ['timestamp', 'open', 'high', 'low', 'close', 'volume']
        
    Returns:
        Dictionary with normalized bars data
    """
    import pandas as pd
    
    # Create copy to avoid modifying original
    df_norm = df.copy()
    
    # Rename timestamp to ts
    if "timestamp" in df_norm.columns:
        df_norm = df_norm.rename(columns={"timestamp": "ts"})
    
    # Ensure ts is datetime64[s]
    if not pd.api.types.is_datetime64_any_dtype(df_norm["ts"]):
        df_norm["ts"] = pd.to_datetime(df_norm["ts"])
    
    # Convert to datetime64[s]
    df_norm["ts"] = df_norm["ts"].astype("datetime64[s]")
    
    # Sort by ts
    df_norm = df_norm.sort_values("ts").reset_index(drop=True)
    
    # Convert to numpy arrays
    result = {}
    for col in REQUIRED_COLUMNS:
        if col == "ts":
            result[col] = df_norm[col].values
        else:
            result[col] = df_norm[col].values.astype(np.float64)
    
    return result


def create_bars_manifest_entry(
    file_path: Union[str, Path],
    season: str,
    dataset_id: str,
    timeframe_min: Optional[int] = None,
) -> BarsManifestEntry:
    """
    Create manifest entry for bars file.
    
    Args:
        file_path: Path to bars file
        season: Season identifier
        dataset_id: Dataset identifier
        timeframe_min: Optional timeframe in minutes
        
    Returns:
        BarsManifestEntry with computed hash
    """
    path = Path(file_path)
    
    # Validate bars first
    result = validate_bars(path)
    if not result.all_passed:
        raise ValueError(f"Cannot create manifest entry for invalid bars: {result.failed_gates}")
    
    # Compute hash
    file_hash = compute_file_hash(path)
    
    return BarsManifestEntry(
        file_path=str(path),
        file_hash=file_hash,
        bars_count=result.bars_count or 0,
        season=season,
        dataset_id=dataset_id,
        timeframe_min=timeframe_min,
        generated_at_utc=datetime.now(timezone.utc).isoformat() + "Z",
    )


# ============================================================================
# MAIN FOR TESTING
# ============================================================================

# Note: Demo/test code removed to comply with governance rules.
# Tests are available in tests/core/test_bars_contract.py