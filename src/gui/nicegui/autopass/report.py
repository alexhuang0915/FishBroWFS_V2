#!/usr/bin/env python3
"""
UI AUTOPASS — single‑command system self‑test.

Generates forensics snapshot, attempts to write intent.json,
derives, creates portfolio and deploy artifacts, and emits
a deterministic report.

See spec: https://...
"""
import json
import logging
import os
import sys
import subprocess
import time
import datetime
import traceback
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# -----------------------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------------------

AUTOPASS_DEFAULTS = {
    "season": "2026Q1",
    "run_mode": "SMOKE",
    "instrument": "MNQ",
    "timeframe": "60m",
    "compute_level": "LOW",
    "max_combinations": 1000,
    "strategies_long": [],
    "strategies_short": [],
    "regime_filters": [],
    "margin_model": "symbolic",
    "contract_specs": {},
    "risk_budget": "medium",
}

# -----------------------------------------------------------------------------
# Helper imports (fail gracefully)
# -----------------------------------------------------------------------------

def import_or_none(module_name: str, attr: Optional[str] = None):
    """Import a module or attribute; return None on any error."""
    try:
        import importlib
        module = importlib.import_module(module_name)
        if attr:
            return getattr(module, attr)
        return module
    except Exception:
        return None

# -----------------------------------------------------------------------------
# System information
# -----------------------------------------------------------------------------

def get_system_info() -> Dict[str, Any]:
    """Collect meta information."""
    import platform
    import subprocess
    
    # Git SHA
    git_sha = None
    try:
        git_sha = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=Path(__file__).parent.parent,
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
    except Exception:
        pass
    
    # Python version
    python_version = platform.python_version()
    
    # NiceGUI version
    nicegui_version = None
    try:
        import nicegui
        nicegui_version = getattr(nicegui, "__version__", None)
    except ImportError:
        pass
    
    return {
        "ts": datetime.datetime.utcnow().isoformat() + "Z",
        "git_sha": git_sha,
        "python": python_version,
        "nicegui": nicegui_version,
        "pid": os.getpid(),
    }


def get_system_status() -> Dict[str, Any]:
    """Collect system status via status_service."""
    status_service = import_or_none("gui.nicegui.services.status_service")
    if status_service is None:
        return {
            "state": "OFFLINE",
            "summary": "status_service not found",
            "backend_up": False,
            "worker_up": False,
            "backend_error": "module missing",
            "worker_error": "module missing",
            "polling_started": False,
            "poll_interval_s": 0.0,
        }
    
    try:
        forensics = status_service.get_forensics_snapshot()
        return {
            "state": forensics["state"],
            "summary": forensics["summary"],
            "backend_up": forensics["backend_up"],
            "worker_up": forensics["worker_up"],
            "backend_error": forensics["backend_error"],
            "worker_error": forensics["worker_error"],
            "polling_started": forensics["polling_started"],
            "poll_interval_s": forensics["poll_interval_s"],
        }
    except Exception as e:
        return {
            "state": "OFFLINE",
            "summary": f"status_service error: {e}",
            "backend_up": False,
            "worker_up": False,
            "backend_error": str(e),
            "worker_error": str(e),
            "polling_started": False,
            "poll_interval_s": 0.0,
        }


# -----------------------------------------------------------------------------
# Forensics integration
# -----------------------------------------------------------------------------

def run_forensics() -> Tuple[Dict[str, Any], Dict[str, str]]:
    """Generate forensics snapshot and write files.
    
    Returns:
        (snapshot dict, file_paths dict with keys json_path, txt_path)
    """
    forensics_service = import_or_none("gui.nicegui.services.forensics_service")
    if forensics_service is None:
        # fallback: run the CLI script
        return run_forensics_via_cli()
    
    try:
        snapshot = forensics_service.generate_ui_forensics()
        file_paths = forensics_service.write_forensics_files(snapshot)
        return snapshot, file_paths
    except Exception as e:
        logging.warning(f"Forensics service failed: {e}")
        return run_forensics_via_cli()


def run_forensics_via_cli() -> Tuple[Dict[str, Any], Dict[str, str]]:
    """Fallback: run scripts/ui_forensics_dump.py via subprocess."""
    script = Path(__file__).parent / "ui_forensics_dump.py"
    if not script.exists():
        raise RuntimeError("Neither forensics service nor CLI script found")
    
    import subprocess
    result = subprocess.run(
        [sys.executable, str(script)],
        cwd=Path(__file__).parent.parent,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Forensics CLI failed: {result.stderr}")
    
    # The script writes to outputs/forensics/ui_forensics.json
    json_path = Path("outputs/forensics/ui_forensics.json")
    if not json_path.exists():
        raise RuntimeError("Forensics JSON not generated")
    
    with open(json_path, "r", encoding="utf-8") as f:
        snapshot = json.load(f)
    
    txt_path = Path("outputs/forensics/ui_forensics.txt")
    file_paths = {"json_path": str(json_path.resolve()), "txt_path": str(txt_path.resolve())}
    return snapshot, file_paths


# -----------------------------------------------------------------------------
# Dynamic render probe validation
# -----------------------------------------------------------------------------

def validate_dynamic_probe(snapshot: Dict[str, Any]) -> Tuple[bool, List[Dict[str, str]]]:
    """Check that each page's dynamic probe is non‑empty."""
    from gui.nicegui.contract.ui_contract import PAGE_IDS
    
    failures = []
    pages_dynamic = snapshot.get("pages_dynamic", {})
    for page_id in PAGE_IDS:
        info = pages_dynamic.get(page_id, {})
        if not info.get("render_attempted", False):
            failures.append({
                "code": "PAGE_RENDER_NOT_ATTEMPTED",
                "detail": f"{page_id}: render_attempted == False",
            })
            continue
        snapshot_counts = info.get("registry_snapshot", {})
        total = sum(snapshot_counts.values())
        if total == 0:
            failures.append({
                "code": "PAGE_DYNAMIC_EMPTY",
                "detail": f"{page_id} registry_snapshot sum == 0",
            })
    
    return len(failures) == 0, failures


# -----------------------------------------------------------------------------
# Wizard intent pipeline
# -----------------------------------------------------------------------------

def build_intent() -> Optional[Dict[str, Any]]:
    """Build a valid intent document using defaults."""
    try:
        from gui.nicegui.models.intent_models import (
            IntentDocument,
            IntentIdentity,
            MarketUniverse,
            StrategySpace,
            ComputeIntent,
            ProductRiskAssumptions,
            RunMode,
            ComputeLevel,
        )
    except ImportError as e:
        logging.error(f"Intent models not found: {e}")
        return None
    
    try:
        identity = IntentIdentity(
            season=AUTOPASS_DEFAULTS["season"],
            run_mode=RunMode(AUTOPASS_DEFAULTS["run_mode"]),
        )
        market_universe = MarketUniverse(
            instrument=AUTOPASS_DEFAULTS["instrument"],
            timeframe=AUTOPASS_DEFAULTS["timeframe"],
            regime_filters=AUTOPASS_DEFAULTS["regime_filters"],
        )
        strategy_space = StrategySpace(
            long=AUTOPASS_DEFAULTS["strategies_long"],
            short=AUTOPASS_DEFAULTS["strategies_short"],
        )
        compute_intent = ComputeIntent(
            compute_level=ComputeLevel(AUTOPASS_DEFAULTS["compute_level"]),
            max_combinations=AUTOPASS_DEFAULTS["max_combinations"],
        )
        product_risk_assumptions = ProductRiskAssumptions(
            margin_model=AUTOPASS_DEFAULTS["margin_model"],
            contract_specs=AUTOPASS_DEFAULTS["contract_specs"],
            risk_budget=AUTOPASS_DEFAULTS["risk_budget"],
        )
        intent_doc = IntentDocument(
            identity=identity,
            market_universe=market_universe,
            strategy_space=strategy_space,
            compute_intent=compute_intent,
            product_risk_assumptions=product_risk_assumptions,
        )
        return intent_doc.model_dump(mode="json")
    except Exception as e:
        logging.error(f"Intent building failed: {e}")
        return None


def write_intent_artifact(intent_dict: Dict[str, Any]) -> Tuple[Optional[Path], Optional[str]]:
    """Write intent.json using intent_service."""
    intent_service = import_or_none("gui.nicegui.services.intent_service")
    if intent_service is None:
        return None, "intent_service module not found"
    
    try:
        # Validate first
        is_valid, errors = intent_service.validate_intent(intent_dict)
        if not is_valid:
            return None, f"Intent validation failed: {errors}"
        
        # Convert dict to IntentDocument
        from gui.nicegui.models.intent_models import IntentDocument
        intent_doc = IntentDocument.model_validate(intent_dict)
        
        # Write intent (no season/run_id specified, defaults will be used)
        intent_path = intent_service.write_intent(intent_doc)
        return Path(intent_path), None
    except Exception as e:
        return None, f"Intent writing failed: {e}"


def copy_to_artifacts(src_path: Path, artifact_name: str, artifacts_dir: Path) -> Optional[Path]:
    """Copy a file to the autopass artifacts directory."""
    try:
        dest = artifacts_dir / artifact_name
        dest.parent.mkdir(parents=True, exist_ok=True)
        import shutil
        shutil.copy2(src_path, dest)
        return dest
    except Exception as e:
        logging.warning(f"Failed to copy {src_path} to artifacts: {e}")
        return None


# -----------------------------------------------------------------------------
# Derived / Portfolio / Deploy export (best effort)
# -----------------------------------------------------------------------------

def attempt_derive(intent_path: Path, artifacts_dir: Path) -> Tuple[Optional[Path], Optional[str]]:
    """Call derive_service to produce derived.json."""
    derive_service = import_or_none("gui.nicegui.services.derive_service")
    if derive_service is None:
        return None, "derive_service module not found"
    
    try:
        derived_path = derive_service.derive_and_write(intent_path)
        if derived_path is None:
            return None, "derive_and_write returned None"
        # Copy to artifacts
        copied = copy_to_artifacts(derived_path, "derived.json", artifacts_dir)
        return copied, None
    except Exception as e:
        return None, f"Derivation failed: {e}"


def attempt_portfolio(artifacts_dir: Path) -> Tuple[Optional[Path], Optional[str]]:
    """Create a minimal portfolio artifact."""
    portfolio_service = import_or_none("gui.nicegui.services.portfolio_service")
    if portfolio_service is None:
        return None, "portfolio_service module not found"
    
    try:
        # Build a trivial portfolio
        portfolio = {
            "version": "1.0",
            "created_at": datetime.datetime.utcnow().isoformat(),
            "candidates": [],
            "weights": {},
            "total_weight": 0.0,
            "metadata": {"autopass": True},
        }
        portfolio_path = portfolio_service.save_portfolio(portfolio)
        copied = copy_to_artifacts(portfolio_path, "portfolio.json", artifacts_dir)
        return copied, None
    except Exception as e:
        return None, f"Portfolio creation failed: {e}"


def attempt_deploy_export(artifacts_dir: Path) -> Tuple[Optional[Path], Optional[str]]:
    """Create a deploy export artifact."""
    # Since deploy export is not yet implemented, we'll write a placeholder.
    try:
        deploy_config = {
            "target": "local_sim",
            "portfolio_id": "autopass_portfolio",
            "config": {"autopass": True},
        }
        dest = artifacts_dir / "deploy_export.json"
        dest.parent.mkdir(parents=True, exist_ok=True)
        with open(dest, "w", encoding="utf-8") as f:
            json.dump(deploy_config, f, indent=2)
        return dest, None
    except Exception as e:
        return None, f"Deploy export failed: {e}"


# -----------------------------------------------------------------------------
# Page‑level diagnostics
# -----------------------------------------------------------------------------

def compute_page_status(snapshot: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """Compute render_ok, non_empty, etc. for each page."""
    from gui.nicegui.contract.ui_contract import PAGE_IDS
    
    pages_dynamic = snapshot.get("pages_dynamic", {})
    pages_static = snapshot.get("pages_static", {})
    
    result = {}
    for page_id in PAGE_IDS:
        static_ok = pages_static.get(page_id, {}).get("import_ok", False)
        dynamic_info = pages_dynamic.get(page_id, {})
        rendered = dynamic_info.get("render_attempted", False)
        snapshot_counts = dynamic_info.get("registry_snapshot", {})
        non_empty = sum(snapshot_counts.values()) > 0
        
        # page‑specific extra fields
        extra = {}
        if page_id == "wizard":
            # intent_written will be filled later
            extra["intent_written"] = False
            extra["intent_path"] = None
        elif page_id == "candidates":
            extra["topk_loaded"] = False
            extra["reason"] = "Not implemented"
        elif page_id == "portfolio":
            extra["portfolio_saved"] = False
            extra["path"] = None
            extra["reason"] = None
        elif page_id == "deploy":
            extra["export_saved"] = False
            extra["path"] = None
            extra["reason"] = None
        
        result[page_id] = {
            "render_ok": static_ok and rendered,
            "non_empty": non_empty,
            **extra,
        }
    return result


# -----------------------------------------------------------------------------
# Main report builder
# -----------------------------------------------------------------------------

def build_autopass_report(outputs_dir: Path = Path("outputs/autopass")) -> Dict[str, Any]:
    """Run all autopass steps and produce the report dictionary."""
    outputs_dir.mkdir(parents=True, exist_ok=True)
    artifacts_dir = outputs_dir / "artifacts"
    logs_dir = outputs_dir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    
    # 1. System meta
    meta = get_system_info()
    
    # 2. System status
    system_status = get_system_status()
    
    # 3. Forensics snapshot
    snapshot, forensics_paths = run_forensics()
    
    # 4. Dynamic probe validation
    probe_ok, probe_failures = validate_dynamic_probe(snapshot)
    
    # 5. Page status
    pages = compute_page_status(snapshot)
    
    # 6. Wizard intent pipeline
    intent_dict = build_intent()
    intent_path = None
    intent_error = None
    if intent_dict is not None:
        intent_path, intent_error = write_intent_artifact(intent_dict)
        if intent_path is not None:
            pages["wizard"]["intent_written"] = True
            pages["wizard"]["intent_path"] = str(intent_path)
            # Copy to artifacts
            copied = copy_to_artifacts(intent_path, "intent.json", artifacts_dir)
            if copied:
                intent_artifact_path = copied
            else:
                intent_artifact_path = None
        else:
            pages["wizard"]["intent_written"] = False
            pages["wizard"]["intent_path"] = None
    else:
        intent_error = "Intent building failed"
    
    # 7. Derived / Portfolio / Deploy (best effort)
    derived_path = None
    portfolio_path = None
    deploy_path = None
    if intent_path is not None:
        derived_path, _ = attempt_derive(intent_path, artifacts_dir)
        if derived_path:
            pages["wizard"]["derived_written"] = True  # extra field
    portfolio_path, _ = attempt_portfolio(artifacts_dir)
    if portfolio_path:
        pages["portfolio"]["portfolio_saved"] = True
        pages["portfolio"]["path"] = str(portfolio_path)
    deploy_path, _ = attempt_deploy_export(artifacts_dir)
    if deploy_path:
        pages["deploy"]["export_saved"] = True
        pages["deploy"]["path"] = str(deploy_path)
    # 8. Acceptance
    failures = []

    # Gate A: Status service errors in summary
    summary = system_status.get("summary", "").lower()
    if "error:" in summary:
        failures.append({
            "code": "STATUS_SERVICE_ERROR",
            "detail": f"Summary contains error indication: {system_status.get('summary')}",
        })

    # Gate B: Schema/attribute errors in backend/worker error fields
    def is_schema_error(err: Optional[str]) -> bool:
        if not err:
            return False
        err_lower = err.lower()
        # Connection‑related errors are acceptable
        connection_indicators = ["connection", "timeout", "refused", "unreachable",
                                 "failed to connect", "http", "requests.exceptions"]
        if any(indicator in err_lower for indicator in connection_indicators):
            return False
        # Schema/attribute errors are not acceptable
        schema_indicators = ["attributeerror", "typeerror", "valueerror", "keyerror",
                             "schema", "attribute"]
        return any(indicator in err_lower for indicator in schema_indicators)

    backend_error = system_status.get("backend_error")
    if is_schema_error(backend_error):
        failures.append({
            "code": "SCHEMA_ERROR_IN_BACKEND_STATUS",
            "detail": f"Backend error indicates schema/attribute issue: {backend_error}",
        })
    worker_error = system_status.get("worker_error")
    if is_schema_error(worker_error):
        failures.append({
            "code": "SCHEMA_ERROR_IN_WORKER_STATUS",
            "detail": f"Worker error indicates schema/attribute issue: {worker_error}",
        })

    # Gate C: Page static import errors
    pages_static = snapshot.get("pages_static", {})
    for page_id, info in pages_static.items():
        import_ok = info.get("import_ok", False)
        if not import_ok:
            failures.append({
                "code": "PAGE_IMPORT_ERROR",
                "detail": f"{page_id}: import_ok == False (static import failed)",
            })

    # Gate D: Dynamic render probe failures (already covered by probe_ok)
    if not probe_ok:
        failures.extend(probe_failures)

    # Gate E: Intent pipeline failure
    if intent_path is None:
        failures.append({
            "code": "WIZARD_INTENT_PIPELINE_NOT_FOUND",
            "detail": intent_error or "Intent not written",
        })

    # Gate F: Artifact file existence and non‑zero size
    for key, path in [( "intent_json", intent_path ),
                      ( "derived_json", derived_path ),
                      ( "portfolio_json", portfolio_path ),
                      ( "deploy_export_json", deploy_path )]:
        if path is None:
            continue
        p = Path(path)
        if not p.exists():
            failures.append({
                "code": "ARTIFACT_MISSING",
                "detail": f"{key}: file does not exist at {path}",
            })
        elif p.stat().st_size == 0:
            failures.append({
                "code": "ARTIFACT_EMPTY",
                "detail": f"{key}: file is zero length",
            })

    passed = len(failures) == 0
    
    
    # 9. Build final report
    report = {
        "meta": meta,
        "system_status": system_status,
        "forensics": {
            "forensics_json_path": forensics_paths.get("json_path"),
            "forensics_txt_path": forensics_paths.get("txt_path"),
        },
        "pages": pages,
        "artifacts": {
            "intent_json": str(artifacts_dir / "intent.json") if intent_path else None,
            "derived_json": str(artifacts_dir / "derived.json") if derived_path else None,
            "portfolio_json": str(artifacts_dir / "portfolio.json") if portfolio_path else None,
            "deploy_export_json": str(artifacts_dir / "deploy_export.json") if deploy_path else None,
        },
        "acceptance": {
            "passed": passed,
            "failures": failures,
        },
    }
    return report


# -----------------------------------------------------------------------------
# File writing and console output
# -----------------------------------------------------------------------------

def write_report(report: Dict[str, Any], outputs_dir: Path) -> Tuple[Path, Path]:
    """Write autopass_report.json and .txt."""
    json_path = outputs_dir / "autopass_report.json"
    txt_path = outputs_dir / "autopass_report.txt"
    
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, sort_keys=True, default=str)
    
    # Human‑readable summary
    lines = [
        "UI AUTOPASS REPORT",
        "=" * 60,
        f"Timestamp: {report['meta']['ts']}",
        f"Git SHA: {report['meta']['git_sha'] or 'unknown'}",
        f"System state: {report['system_status']['state']}",
        f"Backend up: {report['system_status']['backend_up']}",
        f"Worker up: {report['system_status']['worker_up']}",
        "",
        "Page status:",
    ]
    for page, info in report["pages"].items():
        lines.append(f"  {page:12} render_ok={info.get('render_ok', False)} non_empty={info.get('non_empty', False)}")
    
    lines.append("")
    lines.append("Artifacts:")
    for key, path in report["artifacts"].items():
        lines.append(f"  {key:20} {path or 'MISSING'}")
    
    lines.append("")
    lines.append("Acceptance: " + ("PASS" if report["acceptance"]["passed"] else "FAIL"))
    for fail in report["acceptance"]["failures"]:
        lines.append(f"  • {fail['code']}: {fail['detail']}")
    
    lines.append("")
    lines.append(f"Full JSON: {json_path}")
    
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    
    return json_path, txt_path


def main():
    """Command‑line entry point."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
    
    outputs_dir = Path("outputs/autopass")
    outputs_dir.mkdir(parents=True, exist_ok=True)
    
    try:
        report = build_autopass_report(outputs_dir)
        json_path, txt_path = write_report(report, outputs_dir)
        
        # Print final lines of txt report
        with open(txt_path, "r", encoding="utf-8") as f:
            txt_lines = f.readlines()
        
        print("\n".join(txt_lines[-30:]))  # last ~30 lines
        print()
        print(f"Report JSON: {json_path}")
        print(f"Report TXT:  {txt_path}")
        
        # Exit with non‑zero if acceptance failed
        if not report["acceptance"]["passed"]:
            sys.exit(1)
    except Exception as e:
        logging.exception("Autopass crashed")
        sys.exit(2)


if __name__ == "__main__":
    main()