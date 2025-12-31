#!/usr/bin/env python3
"""
Validate that the baseline YAML files parse correctly.
"""
import yaml
import sys
from pathlib import Path

def validate_yaml_file(filepath):
    """Validate a YAML file can be parsed."""
    try:
        with open(filepath, 'r') as f:
            data = yaml.safe_load(f)
        print(f"✓ {filepath}: Parsed successfully")
        
        # Check required fields
        required_fields = ['version', 'strategy_id', 'dataset_id', 'timeframe', 'features', 'params']
        for field in required_fields:
            if field not in data:
                print(f"  ✗ Missing required field: {field}")
                return False
            else:
                print(f"  ✓ Has field: {field}")
        
        # Check features structure
        features = data['features']
        if 'required' not in features:
            print(f"  ✗ Missing 'required' in features")
            return False
        if 'optional' not in features:
            print(f"  ✗ Missing 'optional' in features")
            return False
            
        print(f"  ✓ Features: {len(features.get('required', []))} required, {len(features.get('optional', []))} optional")
        
        return True
    except yaml.YAMLError as e:
        print(f"✗ {filepath}: YAML parsing error: {e}")
        return False
    except Exception as e:
        print(f"✗ {filepath}: Error: {e}")
        return False

def main():
    """Validate all three baseline YAML files."""
    files = [
        Path("configs/strategies/S1/baseline.yaml"),
        Path("configs/strategies/S2/baseline.yaml"),
        Path("configs/strategies/S3/baseline.yaml"),
    ]
    
    all_valid = True
    for filepath in files:
        if not filepath.exists():
            print(f"✗ {filepath}: File does not exist")
            all_valid = False
            continue
        
        if not validate_yaml_file(filepath):
            all_valid = False
    
    if all_valid:
        print("\nAll YAML files parsed successfully.")
        sys.exit(0)
    else:
        print("\nSome YAML files failed validation.")
        sys.exit(1)

if __name__ == "__main__":
    main()