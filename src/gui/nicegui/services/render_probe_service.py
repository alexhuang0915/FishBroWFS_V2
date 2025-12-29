"""
Render probe service – dynamic UI render anomaly capture.

This module provides functions to probe each UI page's render function,
collect element counts, detect missing sections, and compare against
minimal expectations.

All probes must be deterministic, work with backend offline, and never raise.
"""

import importlib
import logging
import os
import sys
import traceback
from typing import Dict, Any, List, Optional

from ..contract.ui_contract import PAGE_IDS, PAGE_MODULES
from ..ui_compat import registry_begin_scope, registry_end_scope, registry_snapshot, registry_reset
from ..contract.render_expectations import RENDER_EXPECTATIONS

logger = logging.getLogger(__name__)

# -----------------------------------------------------------------------------
# Environment configuration
# -----------------------------------------------------------------------------

def _configure_probe_environment():
    """Set environment variables to enforce offline/deterministic behavior."""
    os.environ["FORENSICS_MODE"] = "1"
    os.environ["AUTOPASS_MODE"] = "1"
    os.environ["FISHBRO_UI_RELOAD"] = "0"
    # Disable polling and background timers
    os.environ["FISHBRO_UI_POLLING"] = "0"
    # Ensure UI does not attempt network calls (they will fail gracefully)
    os.environ["BACKEND_OFFLINE"] = "1"


def _collect_counts_from_all_registries(page_id: str) -> Dict[str, int]:
    """Collect element counts from all loaded shared_registry modules."""
    import sys
    counts = {}
    for mod_name, mod in sys.modules.items():
        if mod_name.endswith('shared_registry') and hasattr(mod, 'registry_counts_for_scope'):
            try:
                sub_counts = mod.registry_counts_for_scope(page_id)
                # sum counts
                for elem_type, cnt in sub_counts.items():
                    counts[elem_type] = counts.get(elem_type, 0) + cnt
            except Exception:
                continue
    return counts


# -----------------------------------------------------------------------------
# Page render probe
# -----------------------------------------------------------------------------

def probe_page(page_id: str, *, mode: str = "probe") -> Dict[str, Any]:
    """
    Probe a single page. Never raises; returns {render_ok, errors, counts, markers,...}.
    
    Args:
        page_id: one of PAGE_IDS
        mode: currently only "probe" (reserved for future extensions)
    
    Returns:
        Dictionary with keys:
          - page_id
          - module
          - render_ok (bool)
          - errors (list of strings)
          - traceback (str or None)
          - counts (dict of element type -> int)
          - markers (list of strings)
    """
    errors: List[str] = []
    tb_text = None
    counts = {}
    
    # Ensure environment is configured
    _configure_probe_environment()
    
    module_path = PAGE_MODULES.get(page_id)
    if not module_path:
        errors.append(f"No module mapping for page_id {page_id}")
        return {
            "page_id": page_id,
            "module": None,
            "render_ok": False,
            "errors": errors,
            "traceback": tb_text,
            "counts": {},
            "markers": [],
        }
    
    # Reset registry before each page probe (optional, but ensures clean counts)
    registry_reset()
    
    try:
        # Import the module
        module = importlib.import_module(module_path)
    except ImportError as e:
        errors.append(f"Could not import module {module_path}: {e}")
        tb_text = traceback.format_exc()
        return {
            "page_id": page_id,
            "module": module_path,
            "render_ok": False,
            "errors": errors,
            "traceback": tb_text,
            "counts": {},
            "markers": [],
        }
    
    # Determine render entrypoint (assumes a function named 'render')
    render_func = getattr(module, "render", None)
    if not render_func:
        errors.append(f"Module {module_path} has no 'render' function")
        return {
            "page_id": page_id,
            "module": module_path,
            "render_ok": False,
            "errors": errors,
            "traceback": None,
            "counts": {},
            "markers": [],
        }
    
    # Start registry scope for this page
    registry_begin_scope(page_id)
    try:
        # Call render
        render_func()
        render_ok = True
    except Exception as e:
        render_ok = False
        errors.append(f"Render raised exception: {e}")
        tb_text = traceback.format_exc()
    finally:
        # End scope and collect counts from all registry copies
        registry_end_scope()
        counts = _collect_counts_from_all_registries(page_id)
        # Ensure all element types are present with zero counts
        for key in ["buttons", "inputs", "selects", "checkboxes", "cards", "tables", "logs"]:
            counts.setdefault(key, 0)
    
    # Determine markers (placeholder – implement heuristic detection later)
    markers = []
    # For now, we can inspect counts or other page-specific attributes.
    # Example: if page_id == "dashboard" and counts.get("cards", 0) >= 4:
    #     markers.append("has_status_cards")
    # We'll implement marker detection as a separate function.
    
    return {
        "page_id": page_id,
        "module": module_path,
        "render_ok": render_ok,
        "errors": errors,
        "traceback": tb_text,
        "counts": counts,
        "markers": markers,
    }


def probe_all_pages(*, mode: str = "probe") -> Dict[str, Any]:
    """
    Returns a deterministic dict with per-page render results and element footprints.
    
    Args:
        mode: currently only "probe"
    
    Returns:
        Dictionary keyed by page_id, each value is the result of probe_page.
    """
    _configure_probe_environment()
    # Reset registry once before probing all pages (optional)
    registry_reset()
    
    results = {}
    for page_id in PAGE_IDS:
        results[page_id] = probe_page(page_id, mode=mode)
    
    return results


# -----------------------------------------------------------------------------
# Diff report builder
# -----------------------------------------------------------------------------

def build_render_diff_report(results: Dict[str, Any]) -> Dict[str, Any]:
    """
    Compare probe results vs RENDER_EXPECTATIONS; produce anomalies list and per-page diff.
    
    Args:
        results: output from probe_all_pages (or a dict of page_id -> probe result)
    
    Returns:
        Dictionary with keys:
          - anomalies: list of anomaly records
          - per_page: dict page_id -> diff dict
          - summary: dict with counts of passed/failed pages
    """
    anomalies = []
    per_page = {}
    passed_pages = 0
    failed_pages = 0
    
    for page_id, result in results.items():
        # Basic validation
        if not isinstance(result, dict):
            anomalies.append({
                "page_id": page_id,
                "severity": "P0",
                "reason": f"probe result is not a dict: {type(result)}",
                "suggestion": "Check probe_page implementation.",
            })
            continue
        
        render_ok = result.get("render_ok", False)
        counts = result.get("counts", {})
        errors = result.get("errors", [])
        
        # Determine if page is empty (all counts zero)
        total_elements = sum(counts.values())
        if total_elements == 0:
            anomalies.append({
                "page_id": page_id,
                "severity": "P0",
                "reason": "total elements all zero",
                "suggestion": "Page render created zero UI elements. Ensure render_card wrapper is used and called inside render().",
            })
        
        # Compare with expectations
        expected = RENDER_EXPECTATIONS.get(page_id, {})
        expected_min = expected.get("min", {})
        expected_markers = expected.get("markers", [])
        
        diff = {}
        for elem_type, min_count in expected_min.items():
            actual = counts.get(elem_type, 0)
            if actual < min_count:
                diff[elem_type] = {"expected": min_count, "actual": actual}
                anomalies.append({
                    "page_id": page_id,
                    "severity": "P1",
                    "reason": f"min.{elem_type} expected >= {min_count}, got {actual}",
                    "suggestion": f"Page missing required {elem_type}. Check that the render function creates at least {min_count} {elem_type}.",
                })
        
        # Markers diff (optional)
        # For now, we skip marker validation.
        
        per_page[page_id] = {
            "render_ok": render_ok,
            "total_elements": total_elements,
            "errors": errors,
            "diff": diff,
        }
        
        if render_ok and not diff and total_elements > 0:
            passed_pages += 1
        else:
            failed_pages += 1
    
    summary = {
        "passed": passed_pages,
        "failed": failed_pages,
        "total": len(results),
    }
    
    return {
        "anomalies": anomalies,
        "per_page": per_page,
        "summary": summary,
    }