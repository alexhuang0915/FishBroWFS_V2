#!/usr/bin/env python3
"""
Debug dynamic probe bucket dict issue.
"""
import sys
sys.path.insert(0, 'src')

from gui.nicegui.ui_compat import (
    UI_REGISTRY,
    _UI_REGISTRY_SCOPED,
    _increment_count,
    registry_begin_scope,
    registry_end_scope,
    registry_reset,
    register_element,
    registry_snapshot,
    register_page,
)
from gui.nicegui.contract.ui_contract import UI_CONTRACT, PAGE_IDS, PAGE_MODULES
import copy

def debug_dynamic_probe():
    print("=== DYNAMIC PROBE DEBUG ===")
    # Reset registry
    registry_reset()
    
    # Iterate over pages
    for page_id in PAGE_IDS:
        print(f"\n--- Page {page_id} ---")
        # Start scope
        registry_begin_scope(page_id)
        bucket_before = _UI_REGISTRY_SCOPED["by_page"].get(page_id)
        print(f"Bucket before render: {bucket_before}")
        # Get render function
        render_func = UI_CONTRACT.render_funcs.get(page_id)
        if not render_func:
            print(f"  No render func")
            continue
        # Call render_func
        import nicegui.ui as ui
        with ui.row():
            render_func()
        # After render, capture bucket
        bucket_after = _UI_REGISTRY_SCOPED["by_page"].get(page_id)
        print(f"Bucket after render: {bucket_after}")
        # Also print the bucket dict's id and values
        print(f"Bucket id: {id(bucket_after)}")
        # Print each element type count
        for elem in ["buttons", "inputs", "cards", "selects", "checkboxes", "tables", "logs"]:
            if bucket_after.get(elem, 0) > 0:
                print(f"  {elem}: {bucket_after.get(elem)}")
        # End scope
        registry_end_scope()
    
    # Final snapshot
    snapshot = registry_snapshot()
    print("\n=== Final snapshot ===")
    for page_id in PAGE_IDS:
        bucket = snapshot["by_page"].get(page_id)
        print(f"{page_id}: {bucket}")

if __name__ == "__main__":
    debug_dynamic_probe()