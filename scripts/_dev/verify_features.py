#!/usr/bin/env python3
"""
Verify that all features referenced in baseline YAML files exist in the shared cache.
"""
import yaml
import numpy as np
from pathlib import Path

def load_npz_keys(npz_path):
    """Load NPZ file and return list of keys."""
    try:
        data = np.load(npz_path)
        keys = list(data.files)
        data.close()
        return keys
    except Exception as e:
        print(f"Error loading NPZ file {npz_path}: {e}")
        return []

def check_features_in_yaml(yaml_path, npz_keys):
    """Check if features referenced in YAML exist in NPZ keys."""
    with open(yaml_path, 'r') as f:
        data = yaml.safe_load(f)
    
    missing = []
    
    # Check required features
    for feat in data['features'].get('required', []):
        name = feat.get('name')
        # For S2/S3, the feature names are placeholders (context_feature, value_feature)
        # The actual feature names are in params
        if name in ['context_feature', 'value_feature', 'filter_feature']:
            # Get actual feature name from params
            param_name = f"{name}_name"  # context_feature_name, etc.
            actual_name = data['params'].get(param_name, '')
            if actual_name and actual_name not in npz_keys:
                missing.append(f"{name} (param: {actual_name})")
        elif name not in npz_keys:
            missing.append(name)
    
    # Check optional features (same logic)
    for feat in data['features'].get('optional', []):
        name = feat.get('name')
        if name in ['context_feature', 'value_feature', 'filter_feature']:
            param_name = f"{name}_name"
            actual_name = data['params'].get(param_name, '')
            if actual_name and actual_name not in npz_keys:
                missing.append(f"{name} (param: {actual_name})")
        elif name and name not in npz_keys:
            missing.append(name)
    
    # Also check any feature names directly in params that might be used
    # For S2/S3, check context_feature_name, value_feature_name, filter_feature_name
    for param_key in ['context_feature_name', 'value_feature_name', 'filter_feature_name', 'A_feature_name', 'B_feature_name']:
        if param_key in data['params']:
            feat_name = data['params'][param_key]
            if feat_name and feat_name not in npz_keys:
                missing.append(f"{param_key}: {feat_name}")
    
    return missing

def main():
    """Verify feature availability for all three strategies."""
    npz_path = Path("outputs/shared/2026Q1/CME.MNQ/features/features_60m.npz")
    if not npz_path.exists():
        print(f"NPZ file not found: {npz_path}")
        return
    
    npz_keys = load_npz_keys(npz_path)
    print(f"Loaded {len(npz_keys)} features from shared cache")
    print("First 10 features:", npz_keys[:10])
    
    yaml_files = [
        Path("configs/strategies/S1/baseline.yaml"),
        Path("configs/strategies/S2/baseline.yaml"),
        Path("configs/strategies/S3/baseline.yaml"),
    ]
    
    all_good = True
    for yaml_path in yaml_files:
        print(f"\nChecking {yaml_path}:")
        missing = check_features_in_yaml(yaml_path, npz_keys)
        
        if missing:
            print(f"  ✗ Missing features: {missing}")
            all_good = False
        else:
            print(f"  ✓ All features available in shared cache")
    
    if all_good:
        print("\n✓ All features referenced in baseline YAML files exist in shared cache.")
    else:
        print("\n✗ Some features are missing from shared cache.")
    
    return all_good

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)