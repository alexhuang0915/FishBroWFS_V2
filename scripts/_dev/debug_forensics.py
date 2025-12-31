#!/usr/bin/env python3
"""
Debug the dynamic probe bucket dict issue.
"""
import sys
sys.path.insert(0, 'src')

from gui.nicegui.ui_compat import UI_REGISTRY, _UI_REGISTRY_SCOPED, _increment_count, registry_start_scope, registry_end_scope, _get_current_scope
from gui.nicegui.pages.dashboard import render as dashboard_render

def debug_dynamic_probe():
    print("=== DYNAMIC PROBE DEBUG ===")
    # Clear any existing state
    _UI_REGISTRY_SCOPED["by_page"].clear()
    # Start scope for dashboard
    registry_start_scope("dashboard")
    bucket = _UI_REGISTRY_SCOPED["by_page"].get("dashboard")
    print(f"Initial bucket id: {id(bucket)}")
    print(f"Initial bucket: {bucket}")
    # Monkey-patch _increment_count to log
    original_increment = _increment_count
    def logged_increment(element_type):
        print(f"  increment {element_type}")
        original_increment(element_type)
        bucket2 = _UI_REGISTRY_SCOPED["by_page"].get("dashboard")
        print(f"    bucket after: {bucket2}")
        print(f"    bucket id: {id(bucket2)}")
    # Temporarily replace
    import gui.nicegui.ui_compat as ui_compat
    ui_compat._increment_count = logged_increment
    
    # Render dashboard (but we need to simulate UI creation)
    # We'll call dashboard_render directly, but need ui context.
    # Instead we'll manually simulate the ui_compat wrappers.
    # Let's just test the increment logic by calling ui_compat.button, etc.
    from nicegui import ui
    from gui.nicegui.ui_compat import button, card, table, log_viewer, select, checkbox, input, number
    
    # We'll create a dummy container
    with ui.row():
        # Call each wrapper to trigger increments
        button("Test")
        card("Test")
        # table requires data; skip
        # log_viewer requires logs; skip
        select([1,2,3])
        checkbox("Check")
        input("input")
        number("num", value=1)
    
    # Restore
    ui_compat._increment_count = original_increment
    
    # After render
    bucket_final = _UI_REGISTRY_SCOPED["by_page"].get("dashboard")
    print(f"Final bucket id: {id(bucket_final)}")
    print(f"Final bucket: {bucket_final}")
    
    registry_end_scope("dashboard")
    
if __name__ == "__main__":
    debug_dynamic_probe()