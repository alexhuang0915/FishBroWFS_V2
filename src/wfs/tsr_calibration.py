"""
TSR Calibration for WFS Mode B (Section 5.2)

Implements Target Signal Rate (TSR) calibration for Mode B anchors.
Maps parameter values to target signal rates for entry intensity fixing.
"""

from __future__ import annotations

import math
import numpy as np
from typing import Dict, List, Tuple, Optional, TypedDict
from dataclasses import dataclass
from enum import Enum


class CalibrationMethod(Enum):
    """TSR calibration methods."""
    LINEAR = "linear"
    LOGARITHMIC = "logarithmic"
    POWER_LAW = "power_law"
    PIECEWISE = "piecewise"


@dataclass
class TSRCalibrationConfig:
    """Configuration for TSR calibration."""
    # Target signal rate range
    tsr_min: float = 0.01  # 1% minimum signal rate
    tsr_max: float = 0.20  # 20% maximum signal rate
    
    # Calibration method
    method: CalibrationMethod = CalibrationMethod.LINEAR
    
    # Method-specific parameters
    power_exponent: float = 0.5  # For power law method
    piecewise_breakpoints: Optional[List[float]] = None  # For piecewise method
    piecewise_slopes: Optional[List[float]] = None  # For piecewise method
    
    # Anchor matching tolerance
    anchor_tolerance: float = 0.05  # 5% tolerance for anchor matching
    
    # Signal rate calculation window
    signal_window_bars: int = 100  # Window for calculating actual signal rate


@dataclass
class AnchorPoint:
    """A calibrated anchor point for Mode B."""
    param_value: float  # Parameter value (e.g., channel length, threshold)
    target_tsr: float   # Target signal rate for this parameter
    calibrated_tsr: float  # Actual calibrated signal rate
    calibration_error: float  # Difference between target and calibrated
    is_valid: bool  # Whether this anchor passes calibration tolerance


def calibrate_anchor_params(
    param_values: List[float],
    actual_signal_rates: List[float],
    config: TSRCalibrationConfig
) -> List[AnchorPoint]:
    """
    Calibrate parameter values to target signal rates.
    
    Args:
        param_values: List of parameter values tested
        actual_signal_rates: Corresponding actual signal rates observed
        config: TSR calibration configuration
        
    Returns:
        List of calibrated anchor points
    """
    if len(param_values) != len(actual_signal_rates):
        raise ValueError("param_values and actual_signal_rates must have same length")
    
    if len(param_values) == 0:
        return []
    
    # Sort by parameter value
    sorted_indices = np.argsort(param_values)
    sorted_params = [param_values[i] for i in sorted_indices]
    sorted_rates = [actual_signal_rates[i] for i in sorted_indices]
    
    # Map parameter range to TSR range
    param_min = min(sorted_params)
    param_max = max(sorted_params)
    param_range = param_max - param_min
    
    anchors = []
    
    for i, (param, actual_rate) in enumerate(zip(sorted_params, sorted_rates)):
        # Calculate target TSR based on parameter position
        if param_range == 0:
            # All parameters same value, use middle of TSR range
            target_tsr = (config.tsr_min + config.tsr_max) / 2
        else:
            # Normalize parameter position (0 to 1)
            param_norm = (param - param_min) / param_range
            
            # Apply calibration method
            target_tsr = _apply_calibration_method(param_norm, config)
        
        # Calculate calibration error
        calibration_error = abs(target_tsr - actual_rate)
        
        # Check if within tolerance
        is_valid = calibration_error <= config.anchor_tolerance
        
        anchor = AnchorPoint(
            param_value=param,
            target_tsr=target_tsr,
            calibrated_tsr=actual_rate,
            calibration_error=calibration_error,
            is_valid=is_valid
        )
        anchors.append(anchor)
    
    return anchors


def _apply_calibration_method(param_norm: float, config: TSRCalibrationConfig) -> float:
    """
    Apply calibration method to normalized parameter.
    
    Args:
        param_norm: Normalized parameter value (0 to 1)
        config: TSR calibration configuration
        
    Returns:
        Target TSR value
    """
    tsr_range = config.tsr_max - config.tsr_min
    
    if config.method == CalibrationMethod.LINEAR:
        # Linear mapping: TSR = TSR_min + param_norm * (TSR_max - TSR_min)
        return config.tsr_min + param_norm * tsr_range
    
    elif config.method == CalibrationMethod.LOGARITHMIC:
        # Logarithmic mapping: more sensitive at low parameter values
        # TSR = TSR_min + log10(1 + 9*param_norm) * tsr_range
        if param_norm <= 0:
            return config.tsr_min
        return config.tsr_min + math.log10(1 + 9 * param_norm) * tsr_range
    
    elif config.method == CalibrationMethod.POWER_LAW:
        # Power law mapping: TSR = TSR_min + (param_norm^exponent) * tsr_range
        if param_norm <= 0:
            return config.tsr_min
        return config.tsr_min + math.pow(param_norm, config.power_exponent) * tsr_range
    
    elif config.method == CalibrationMethod.PIECEWISE:
        # Piecewise linear mapping
        if config.piecewise_breakpoints is None or config.piecewise_slopes is None:
            # Fall back to linear if piecewise not configured
            return config.tsr_min + param_norm * tsr_range
        
        # Find which segment param_norm falls into
        for i, breakpoint in enumerate(config.piecewise_breakpoints):
            if i == 0 and param_norm < breakpoint:
                # Before first breakpoint
                return config.tsr_min + param_norm * config.piecewise_slopes[0]
            elif i < len(config.piecewise_breakpoints) - 1:
                if breakpoint <= param_norm < config.piecewise_breakpoints[i + 1]:
                    # In segment i
                    segment_start = breakpoint
                    segment_slope = config.piecewise_slopes[i]
                    segment_tsr_at_start = _apply_piecewise_at_breakpoint(
                        segment_start, config
                    )
                    return segment_tsr_at_start + (param_norm - segment_start) * segment_slope
        
        # After last breakpoint
        last_breakpoint = config.piecewise_breakpoints[-1]
        last_slope = config.piecewise_slopes[-1]
        last_tsr_at_breakpoint = _apply_piecewise_at_breakpoint(last_breakpoint, config)
        return last_tsr_at_breakpoint + (param_norm - last_breakpoint) * last_slope
    
    else:
        # Default to linear
        return config.tsr_min + param_norm * tsr_range


def _apply_piecewise_at_breakpoint(breakpoint: float, config: TSRCalibrationConfig) -> float:
    """Helper to compute TSR at a piecewise breakpoint using linear method."""
    tsr_range = config.tsr_max - config.tsr_min
    return config.tsr_min + breakpoint * tsr_range


def select_mode_b_anchors(
    anchors: List[AnchorPoint],
    min_valid_anchors: int = 3
) -> Tuple[List[AnchorPoint], List[AnchorPoint]]:
    """
    Select valid anchors for Mode B operation.
    
    Args:
        anchors: List of all anchor points
        min_valid_anchors: Minimum number of valid anchors required
        
    Returns:
        Tuple of (selected_anchors, rejected_anchors)
    """
    valid_anchors = [a for a in anchors if a.is_valid]
    rejected_anchors = [a for a in anchors if not a.is_valid]
    
    if len(valid_anchors) < min_valid_anchors:
        # Not enough valid anchors, return empty selection
        return [], anchors
    
    # Sort valid anchors by parameter value
    valid_anchors.sort(key=lambda a: a.param_value)
    
    # For now, select all valid anchors
    # In future, could implement spacing or diversity criteria
    return valid_anchors, rejected_anchors


def compute_signal_rate(
    entry_signals: List[bool],
    window_size: int = 100
) -> float:
    """
    Compute signal rate from entry signals.
    
    Args:
        entry_signals: List of boolean entry signals
        window_size: Rolling window size for calculation
        
    Returns:
        Signal rate (0 to 1)
    """
    if not entry_signals:
        return 0.0
    
    signals = np.array(entry_signals, dtype=bool)
    n_bars = len(signals)
    
    if n_bars <= window_size:
        # Use all bars if window larger than data
        signal_rate = np.mean(signals)
    else:
        # Use rolling window
        signal_rates = []
        for i in range(n_bars - window_size + 1):
            window = signals[i:i + window_size]
            signal_rates.append(np.mean(window))
        
        # Use median of rolling rates
        signal_rate = np.median(signal_rates)
    
    return float(signal_rate)


def create_mode_b_structure_filter(
    selected_anchors: List[AnchorPoint],
    param_name: str
) -> Dict[str, any]:
    """
    Create Mode B structure filter from selected anchors.
    
    Args:
        selected_anchors: Selected anchor points
        param_name: Name of the parameter being anchored
        
    Returns:
        Mode B structure filter configuration
    """
    if not selected_anchors:
        return {
            "mode_b_enabled": False,
            "reason": "No valid anchors selected"
        }
    
    # Extract anchor values and target TSRs
    anchor_values = [a.param_value for a in selected_anchors]
    target_tsrs = [a.target_tsr for a in selected_anchors]
    
    # Create interpolation function description
    param_min = min(anchor_values)
    param_max = max(anchor_values)
    
    return {
        "mode_b_enabled": True,
        "param_name": param_name,
        "anchor_count": len(selected_anchors),
        "anchor_values": anchor_values,
        "target_tsrs": target_tsrs,
        "param_range": [param_min, param_max],
        "interpolation": "piecewise_linear",
        "description": f"Mode B structure filter for {param_name} with {len(selected_anchors)} anchors"
    }


# Default configuration
DEFAULT_CALIBRATION_CONFIG = TSRCalibrationConfig()


# Test function
if __name__ == "__main__":
    print("=== Testing TSR Calibration ===")
    
    # Create test data
    param_values = [10, 20, 30, 40, 50, 60, 70, 80, 90, 100]
    actual_rates = [0.02, 0.05, 0.08, 0.10, 0.12, 0.14, 0.16, 0.17, 0.18, 0.19]
    
    # Test linear calibration
    config_linear = TSRCalibrationConfig(
        method=CalibrationMethod.LINEAR,
        tsr_min=0.01,
        tsr_max=0.20
    )
    
    anchors = calibrate_anchor_params(param_values, actual_rates, config_linear)
    
    print(f"Calibrated {len(anchors)} anchor points:")
    for i, anchor in enumerate(anchors):
        status = "VALID" if anchor.is_valid else "INVALID"
        print(f"  {i+1}: param={anchor.param_value}, "
              f"target={anchor.target_tsr:.3f}, "
              f"actual={anchor.calibrated_tsr:.3f}, "
              f"error={anchor.calibration_error:.3f} [{status}]")
    
    # Select valid anchors
    selected, rejected = select_mode_b_anchors(anchors)
    print(f"\nSelected {len(selected)} valid anchors, rejected {len(rejected)}")
    
    # Create Mode B filter
    if selected:
        filter_config = create_mode_b_structure_filter(selected, "channel_len")
        print(f"\nMode B Filter Config:")
        for key, value in filter_config.items():
            print(f"  {key}: {value}")
    
    print("\n=== Calibration test completed ===")