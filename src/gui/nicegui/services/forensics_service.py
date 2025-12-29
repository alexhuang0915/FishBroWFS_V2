"""
UI Forensic Dump Service.

Generates a deterministic snapshot of the NiceGUI UI subsystem without manual
clicking/testing. Works when backend is offline.
"""
import json
import logging
import os
import sys
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

from ..services.status_service import get_state, get_summary, get_status, get_forensics_snapshot
from ..state.wizard_state import WizardState
from ..state.portfolio_state import PortfolioState
from ..state.app_state import AppState
from ..ui_compat import UI_REGISTRY, UI_CONTRACT, PAGE_IDS, PAGE_MODULES

logger = logging.getLogger(__name__)

# -----------------------------------------------------------------------------
# Constants
# -----------------------------------------------------------------------------

TABS_EXPECTED = UI_CONTRACT["tabs_expected"]

# Canonical import paths for UI pages (do NOT use src.*)
PAGES = PAGE_MODULES

# -----------------------------------------------------------------------------
# Core forensic generation
# -----------------------------------------------------------------------------


def generate_ui_forensics(outputs_dir: str = "outputs/forensics") -> Dict[str, Any]:
    """Generate a complete UI forensic snapshot.
    
    Returns a dict that can be serialized to JSON. The dict structure follows
    the UI Forensic Dump specification.
    
    Args:
        outputs_dir: Base directory where forensics files will be saved.
                     The function does NOT write files; the caller must do so.
    
    Returns:
        Forensic snapshot dictionary.
    """
    now = time.time()
    
    # 1. Meta
    meta = {
        "timestamp_iso": datetime.utcfromtimestamp(now).isoformat() + "Z",
        "pid": os.getpid(),
        "cwd": os.getcwd(),
        "python_version": sys.version,
        "nicegui_version": _get_nicegui_version(),
    }
    
    # 2. Status
    status = get_forensics_snapshot()
    # Add extra fields for backward compatibility
    status_snapshot = get_status()
    status["backend_last_ok_ts"] = status_snapshot.backend_last_ok_ts
    status["worker_last_ok_ts"] = status_snapshot.worker_last_ok_ts
    # Ensure last_check_ts is present (snapshot uses last_checked_ts)
    if "last_check_ts" not in status:
        status["last_check_ts"] = status_snapshot.last_check_ts
    
    # 3. Static page diagnostics (CLI‑safe)
    pages_static = _collect_pages_static()
    
    # 4. Dynamic page diagnostics (UI‑only, may be empty)
    pages_dynamic = _collect_pages_dynamic()
    
    # 5. UI registry (populated from UI_REGISTRY)
    ui_registry = _collect_ui_registry()
    
    # 6. UI contract (legacy, kept for compatibility)
    ui_contract = {
        "tabs_expected": TABS_EXPECTED,
        "tabs_detected": TABS_EXPECTED,
        "tabs_ok": True,
        "pages": {},  # deprecated
    }
    
    # 7. State snapshots
    state_snapshot = {
        "wizard_state": _serialize_wizard_state(),
        "portfolio_state": _serialize_portfolio_state(),
        "deploy_state": _serialize_deploy_state(),
    }
    
    # 8. Logs
    logs = {
        "log_tail": _read_ui_log_tail(lines=200),
        "warnings_seen": [],  # TODO: collect from logging capture
    }
    
    # 9. Elements (legacy, will be removed after ui_registry is populated)
    elements = {
        "buttons": _collect_registered_buttons(),
        "inputs": [],
        "selects": [],
        "checkboxes": [],
    }
    
    # 10. Errors (collect import errors from static diagnostics)
    errors = []
    for page, info in pages_static.items():
        if not info["import_ok"]:
            errors.append(f"Page {page}: {info['import_error']}")
    
    # 11. Summary
    total_pages = len(PAGES)
    ok_pages = sum(1 for info in pages_static.values() if info["import_ok"])
    summary = (
        f"Static imports: {ok_pages}/{total_pages} OK. "
        f"System state: {status['state']}. "
        f"Backend up: {status['backend_up']}, Worker up: {status['worker_up']}."
    )
    
    return {
        "meta": meta,
        "system_status": status,
        "pages_static": pages_static,
        "pages_dynamic": pages_dynamic,
        "ui_registry": ui_registry,
        "ui_contract": ui_contract,
        "errors": errors,
        "summary": summary,
        "state_snapshot": state_snapshot,
        "logs": logs,
        "elements": elements,  # deprecated
    }


def _get_nicegui_version() -> Optional[str]:
    """Return NiceGUI version if importable."""
    try:
        import nicegui
        return nicegui.__version__
    except (ImportError, AttributeError):
        return None


def _collect_pages_static() -> Dict[str, Any]:
    """Collect static import information for each UI page (CLI‑safe)."""
    import importlib.util
    import hashlib
    from pathlib import Path
    
    static = {}
    for tab, import_path in PAGES.items():
        try:
            spec = importlib.util.find_spec(import_path)
            if spec is None or spec.origin is None:
                raise ImportError(f"Module {import_path} not found")
            module_file = Path(spec.origin).resolve()
            source_hash = ""
            if module_file.is_file():
                source = module_file.read_bytes()
                source_hash = hashlib.sha256(source).hexdigest()
            
            # Import the module (but do NOT call render)
            module = __import__(import_path, fromlist=["render"])
            has_render_fn = callable(getattr(module, "render", None))
            has_page_decorator = hasattr(module, "render") and hasattr(module.render, "__page__")
            
            static[tab] = {
                "import_ok": True,
                "import_error": None,
                "has_render_fn": has_render_fn,
                "has_page_decorator": has_page_decorator,
                "module_file": str(module_file),
                "source_hash": source_hash,
            }
        except Exception as e:
            static[tab] = {
                "import_ok": False,
                "import_error": str(e),
                "has_render_fn": False,
                "has_page_decorator": False,
                "module_file": None,
                "source_hash": None,
            }
    return static


def _collect_pages_dynamic() -> Dict[str, Any]:
    """Collect runtime UI page diagnostics (UI‑only)."""
    from .. import ui_compat
    from ..ui_compat import registry_reset, registry_begin_scope, registry_end_scope, ui
    import os
    
    # Temporarily set environment flag to suppress side effects (e.g., polling)
    old_env = os.environ.get("FISHBRO_UI_FORENSICS")
    os.environ["FISHBRO_UI_FORENSICS"] = "1"
    registry_reset()
    
    dynamic = {}
    for page_id in PAGE_IDS:
        # Begin a new scope for this page
        registry_begin_scope(page_id)
        
        try:
            # Import and call render function
            import_path = PAGE_MODULES[page_id]
            module = __import__(import_path, fromlist=["render"])
            render_func = getattr(module, "render", None)
            if callable(render_func):
                # Create a dummy UI container to hold rendered elements
                with ui.row().classes("hidden"):
                    render_func()
                    import sys
                    sys.stderr.write(f"DEBUG by_page dict after render: {ui_compat.snapshot_by_page()}\n")
                    # Capture bucket BEFORE exiting the UI container
                    bucket_after = ui_compat.snapshot_by_page().get(page_id, {})
                    sys.stderr.write(f"DEBUG after render bucket for {page_id}: {bucket_after}\n")
                    # Print specific keys we expect to have been incremented
                    for key in ["cards", "buttons", "tables", "logs", "inputs", "selects", "checkboxes"]:
                        val = bucket_after.get(key, 0)
                        if val > 0:
                            sys.stderr.write(f"DEBUG bucket[{key}] = {val}\n")
                render_attempted = True
            else:
                render_attempted = False
        except Exception as e:
            logger.warning(f"Page {page_id} render probe failed: {e}")
            render_attempted = False
        
        # Capture snapshot BEFORE ending scope
        import sys
        sys.stderr.write(f"DEBUG by_page keys: {list(ui_compat.snapshot_by_page().keys())}\n")
        bucket = ui_compat.snapshot_by_page().get(page_id, {})
        sys.stderr.write(f"DEBUG bucket for {page_id}: {bucket}\n")
        sys.stderr.write(f"DEBUG bucket id: {id(bucket)} stored dict id: {id(ui_compat.snapshot_by_page()[page_id]) if page_id in ui_compat.snapshot_by_page() else None}\n")
        snapshot = {
            "buttons": bucket.get("buttons", 0),
            "inputs": bucket.get("inputs", 0),
            "cards": bucket.get("cards", 0),
            "selects": bucket.get("selects", 0),
            "checkboxes": bucket.get("checkboxes", 0),
            "tables": bucket.get("tables", 0),
            "logs": bucket.get("logs", 0),
        }
        
        dynamic[page_id] = {
            "render_attempted": render_attempted,
            "registry_snapshot": snapshot,
        }
        
        # End scope after capturing snapshot
        registry_end_scope()
    
    # Restore environment
    if old_env is None:
        os.environ.pop("FISHBRO_UI_FORENSICS", None)
    else:
        os.environ["FISHBRO_UI_FORENSICS"] = old_env
    
    return dynamic


def _collect_ui_registry() -> Dict[str, Any]:
    """Return a structured snapshot of the UI registry."""
    from .. import ui_compat
    
    registry = ui_compat.UI_REGISTRY.copy()
    # Ensure all expected keys exist
    for key in ("buttons", "inputs", "cards", "pages", "selects", "checkboxes", "tables", "logs"):
        registry.setdefault(key, [])
    # Convert pages set to list for JSON serialization
    pages = registry["pages"]
    if isinstance(pages, set):
        pages = list(pages)
    
    # Build scoped snapshot
    scoped = {
        "global": {
            "buttons": len(registry["buttons"]),
            "inputs": len(registry["inputs"]),
            "cards": len(registry["cards"]),
            "selects": len(registry["selects"]),
            "checkboxes": len(registry["checkboxes"]),
            "tables": len(registry["tables"]),
            "logs": len(registry["logs"]),
        },
        "pages": pages,
        "by_page": ui_compat.snapshot_by_page(),
    }
    return scoped


def _collect_page_status() -> Dict[str, Any]:
    """Legacy function (deprecated)."""
    # Keep for compatibility; returns empty dict.
    return {}


def _serialize_wizard_state() -> Dict[str, Any]:
    """Extract serializable fields from WizardState."""
    state = WizardState()
    return {
        "current_step": state.current_step,
        "run_mode": state.run_mode,
        "instrument": state.instrument,
        "timeframe": state.timeframe,
        "regime_filters": state.regime_filters,
        "long_strategies": state.long_strategies,
        "short_strategies": state.short_strategies,
        "compute_level": state.compute_level,
        "max_combinations": state.max_combinations,
        "margin_model": state.margin_model,
        "contract_specs": state.contract_specs,
        "risk_budget": state.risk_budget,
    }


def _serialize_portfolio_state() -> Dict[str, Any]:
    """Extract serializable fields from PortfolioState."""
    state = PortfolioState()
    return {
        "candidates": [
            {
                "strategy_id": item.strategy_id,
                "side": item.side,
                "sharpe": item.sharpe,
                "weight": item.weight,
                "selected": item.selected,
            }
            for item in state.candidates
        ],
        "selected_items": list(state.selected_items.keys()),
        "total_weight": state.total_weight,
        "portfolio_sharpe": state.portfolio_sharpe,
        "expected_return": state.expected_return,
        "max_drawdown": state.max_drawdown,
        "correlation": state.correlation,
        "last_saved_id": state.last_saved_id,
    }


def _serialize_deploy_state() -> Dict[str, Any]:
    """Extract serializable fields from deploy‑related state."""
    # Deploy state is currently not modeled; return empty dict for now.
    return {}


def _read_ui_log_tail(lines: int = 200) -> List[str]:
    """Read the last `lines` from the UI log file."""
    log_path = "outputs/logs/ui.log"
    if not os.path.isfile(log_path):
        return []
    try:
        with open(log_path, "r", encoding="utf-8") as f:
            # Simple tail: read all lines and take last N
            all_lines = f.readlines()
            return [line.rstrip("\n") for line in all_lines[-lines:]]
    except Exception:
        return []


def _collect_registered_buttons() -> List[Dict[str, Any]]:
    """Collect button metadata from the UI registry."""
    from ..ui_compat import UI_REGISTRY, UI_CONTRACT, PAGE_IDS, PAGE_MODULES
    registry = UI_REGISTRY.get("buttons", [])
    # Return each button dict as is (already contains label, etc.)
    return registry


# -----------------------------------------------------------------------------
# File writing
# -----------------------------------------------------------------------------


def write_forensics_files(
    snapshot: Dict[str, Any],
    outputs_dir: str = "outputs/forensics",
) -> Dict[str, str]:
    """Write JSON and text forensic files.
    
    Args:
        snapshot: The snapshot dict from `generate_ui_forensics`.
        outputs_dir: Directory where files will be created.
    
    Returns:
        Dict with keys "json_path", "txt_path" and absolute file paths.
    """
    os.makedirs(outputs_dir, exist_ok=True)
    
    json_path = os.path.join(outputs_dir, "ui_forensics.json")
    txt_path = os.path.join(outputs_dir, "ui_forensics.txt")
    
    # Write JSON
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, indent=2, sort_keys=True, default=str)
    
    # Write human‑readable text report
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(_format_text_report(snapshot))
    
    return {"json_path": json_path, "txt_path": txt_path}


def _format_text_report(snapshot: Dict[str, Any]) -> str:
    """Produce a condensed human‑readable text report."""
    lines = []
    lines.append("UI Forensic Dump")
    lines.append("=" * 60)
    lines.append(f"Timestamp: {snapshot['meta']['timestamp_iso']}")
    lines.append(f"PID: {snapshot['meta']['pid']}")
    lines.append("")
    
    # System status
    status = snapshot["system_status"]
    lines.append(f"System State: {status['state']}")
    lines.append(f"Summary: {status['summary']}")
    lines.append(f"Backend up: {status['backend_up']}")
    lines.append(f"Worker up: {status['worker_up']}")
    lines.append("")
    
    # Pages static import status
    pages_static = snapshot.get("pages_static", {})
    lines.append(f"Static page imports: {len(pages_static)} total")
    ok_count = sum(1 for info in pages_static.values() if info.get("import_ok", False))
    lines.append(f"  ✓ OK: {ok_count}")
    lines.append(f"  ✗ FAILED: {len(pages_static) - ok_count}")
    for page, info in pages_static.items():
        if not info.get("import_ok", True):
            lines.append(f"    {page}: {info.get('import_error', 'unknown error')}")
    lines.append("")
    
    # Errors
    errors = snapshot.get("errors", [])
    if errors:
        lines.append("Errors:")
        for err in errors:
            lines.append(f"  • {err}")
        lines.append("")
    
    # UI Registry (non‑empty guarantee)
    ui_registry = snapshot.get("ui_registry", {})
    lines.append("UI Registry:")
    global_counts = ui_registry.get("global", {})
    lines.append(f"  Buttons: {global_counts.get('buttons', 0)}")
    lines.append(f"  Inputs: {global_counts.get('inputs', 0)}")
    lines.append(f"  Cards: {global_counts.get('cards', 0)}")
    lines.append(f"  Selects: {global_counts.get('selects', 0)}")
    lines.append(f"  Checkboxes: {global_counts.get('checkboxes', 0)}")
    lines.append(f"  Tables: {global_counts.get('tables', 0)}")
    lines.append(f"  Logs: {global_counts.get('logs', 0)}")
    pages_list = ui_registry.get("pages", [])
    lines.append(f"  Pages registered: {len(pages_list)}")
    # Optionally list per‑page counts
    by_page = ui_registry.get("by_page", {})
    if by_page:
        lines.append("  Per‑page element counts:")
        for page_id, counts in sorted(by_page.items()):
            if any(counts.values()):
                lines.append(f"    {page_id}: " + ", ".join([f"{k}={v}" for k, v in counts.items() if v > 0]))
    lines.append("")
    
    # Dynamic page diagnostics (if any)
    pages_dynamic = snapshot.get("pages_dynamic", {})
    if pages_dynamic:
        lines.append("Dynamic page diagnostics:")
        for page, info in pages_dynamic.items():
            attempted = info.get("render_attempted", False)
            snapshot_counts = info.get("registry_snapshot", {})
            nonzero = {k: v for k, v in snapshot_counts.items() if v > 0}
            if attempted:
                if nonzero:
                    lines.append(f"  {page}: rendered with {len(nonzero)} element types")
                else:
                    lines.append(f"  {page}: rendered (no elements)")
            else:
                lines.append(f"  {page}: not rendered")
        lines.append("")
    
    # State summary
    lines.append("State snapshots:")
    lines.append(f"  Wizard step: {snapshot['state_snapshot']['wizard_state'].get('current_step', 'N/A')}")
    lines.append(f"  Portfolio selected items: {len(snapshot['state_snapshot']['portfolio_state'].get('selected_items', []))}")
    lines.append("")
    
    # Log tail preview
    log_lines = snapshot["logs"]["log_tail"]
    lines.append(f"Log tail (last {len(log_lines)} lines):")
    for line in log_lines[-5:]:  # show last 5 lines
        lines.append(f"  {line}")
    
    return "\n".join(lines)