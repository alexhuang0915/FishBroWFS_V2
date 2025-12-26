#!/usr/bin/env python3
"""Update test mocks to patch true function owners instead of service wrappers."""

import re

# Mapping of service wrapper patches to true function owner patches
PATCH_MAPPINGS = {
    # invalidate_feature_cache
    r"patch\('FishBroWFS_V2\.gui\.services\.reload_service\.invalidate_feature_cache'": 
        "patch('FishBroWFS_V2.control.feature_resolver.invalidate_feature_cache'",
    
    # get_dataset_catalog
    r"patch\('FishBroWFS_V2\.gui\.services\.reload_service\.get_dataset_catalog'": 
        "patch('FishBroWFS_V2.control.dataset_catalog.get_dataset_catalog'",
    
    # get_strategy_catalog
    r"patch\('FishBroWFS_V2\.gui\.services\.reload_service\.get_strategy_catalog'": 
        "patch('FishBroWFS_V2.control.strategy_catalog.get_strategy_catalog'",
    
    # get_descriptor
    r"patch\('FishBroWFS_V2\.gui\.services\.reload_service\.get_descriptor'": 
        "patch('FishBroWFS_V2.control.dataset_descriptor.get_descriptor'",
    
    # list_descriptors
    r"patch\('FishBroWFS_V2\.gui\.services\.reload_service\.list_descriptors'": 
        "patch('FishBroWFS_V2.control.dataset_descriptor.list_descriptors'",
    
    # build_parquet_from_txt
    r"patch\('FishBroWFS_V2\.gui\.services\.reload_service\.build_parquet_from_txt'": 
        "patch('FishBroWFS_V2.control.data_build.build_parquet_from_txt'",
}

def update_test_file():
    """Update the test file with correct patches."""
    test_file = "tests/gui/test_reload_service.py"
    
    with open(test_file, 'r') as f:
        content = f.read()
    
    # Apply all replacements
    updated_content = content
    for old_pattern, new_replacement in PATCH_MAPPINGS.items():
        updated_content = re.sub(old_pattern, new_replacement, updated_content)
    
    # Write back
    with open(test_file, 'w') as f:
        f.write(updated_content)
    
    print(f"Updated {test_file}")
    print("Changes made:")
    for old, new in PATCH_MAPPINGS.items():
        old_count = len(re.findall(old, content))
        if old_count > 0:
            print(f"  - {old_count} instances of {old[7:-1]} -> {new[7:-1]}")

if __name__ == "__main__":
    update_test_file()