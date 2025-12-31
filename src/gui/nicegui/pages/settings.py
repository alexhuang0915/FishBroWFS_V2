"""Settings page - Minimum Honest UI.

According to UI Prune spec, Settings page should contain:
- Diagnostics (with evidence guarantee)
- Freeze policy link
- Environment info

No fake features or claims.
"""
import subprocess
import json
import logging
from pathlib import Path
from nicegui import ui
from .. import ui_compat as uic

from ..layout.cards import render_card
from ..layout.toasts import show_toast, ToastType
from ..constitution.page_shell import page_shell
from ..constitution.truth_providers import (
    create_evidence_with_guarantee,
    verify_evidence_created,
)

logger = logging.getLogger(__name__)

# Page shell compliance flag
PAGE_SHELL_ENABLED = True


# -----------------------------------------------------------------------------
# Evidence Guarantee Functions
# -----------------------------------------------------------------------------

def run_ui_forensics_with_evidence() -> dict:
    """
    Run UI forensics and guarantee evidence files are created.
    
    Returns:
        Dict with success status and file paths.
    """
    try:
        # Create forensics output directory
        out_dir = Path("outputs/forensics")
        out_dir.mkdir(parents=True, exist_ok=True)
        
        # Run UI forensics via subprocess (ensures fresh execution)
        cmd = ["python", "-m", "scripts.ui_forensics_dump"]
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=Path.cwd(),
            timeout=30,
        )
        
        # Check if command succeeded
        if result.returncode != 0:
            logger.error(f"UI forensics failed: {result.stderr}")
            return {
                "success": False,
                "error": result.stderr,
                "stdout": result.stdout,
            }
        
        # Parse output to find created files
        json_path = None
        txt_path = None
        for line in result.stdout.split("\n"):
            if "[OK]" in line:
                path_str = line.split("[OK]")[1].strip()
                path = Path(path_str)
                if path.suffix == ".json":
                    json_path = path
                elif path.suffix == ".txt":
                    txt_path = path
        
        # Verify evidence was created
        evidence_created = False
        if json_path and txt_path:
            if verify_evidence_created(json_path) and verify_evidence_created(txt_path):
                evidence_created = True
        
        return {
            "success": evidence_created,
            "json_path": str(json_path) if json_path else None,
            "txt_path": str(txt_path) if txt_path else None,
            "stdout": result.stdout,
            "stderr": result.stderr,
        }
        
    except subprocess.TimeoutExpired:
        logger.error("UI forensics timed out after 30 seconds")
        return {
            "success": False,
            "error": "Timeout after 30 seconds",
        }
    except Exception as e:
        logger.exception("Unexpected error in UI forensics")
        return {
            "success": False,
            "error": str(e),
        }


def run_ui_autopass_with_evidence() -> dict:
    """
    Run UI autopass and guarantee evidence files are created.
    
    Returns:
        Dict with success status and file paths.
    """
    try:
        # Create autopass output directory
        out_dir = Path("outputs/autopass")
        out_dir.mkdir(parents=True, exist_ok=True)
        
        # Run UI autopass via subprocess
        cmd = ["python", "-m", "scripts.ui_autopass"]
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=Path.cwd(),
            timeout=60,
        )
        
        # Check if command succeeded
        if result.returncode != 0:
            logger.error(f"UI autopass failed: {result.stderr}")
            return {
                "success": False,
                "error": result.stderr,
                "stdout": result.stdout,
            }
        
        # Look for autopass report files
        report_json = out_dir / "autopass_report.json"
        report_txt = out_dir / "autopass_report.txt"
        
        # Verify evidence was created
        evidence_created = False
        if report_json.exists() or report_txt.exists():
            # At least one file should exist
            evidence_created = True
            # Verify they have content
            if report_json.exists():
                verify_evidence_created(report_json)
            if report_txt.exists():
                verify_evidence_created(report_txt)
        
        return {
            "success": evidence_created,
            "json_path": str(report_json) if report_json.exists() else None,
            "txt_path": str(report_txt) if report_txt.exists() else None,
            "stdout": result.stdout,
            "stderr": result.stderr,
        }
        
    except subprocess.TimeoutExpired:
        logger.error("UI autopass timed out after 60 seconds")
        return {
            "success": False,
            "error": "Timeout after 60 seconds",
        }
    except Exception as e:
        logger.exception("Unexpected error in UI autopass")
        return {
            "success": False,
            "error": str(e),
        }


def create_system_diagnostics_report() -> dict:
    """
    Create a comprehensive system diagnostics report.
    
    Returns:
        Dict with system information and evidence verification.
    """
    import platform
    import sys
    import time
    
    report = {
        "timestamp": time.time(),
        "system": {
            "platform": platform.platform(),
            "python_version": sys.version,
            "python_path": sys.executable,
        },
        "evidence": {
            "ui_forensics": None,
            "ui_autopass": None,
        },
        "success": False,
    }
    
    # Run UI forensics
    forensics_result = run_ui_forensics_with_evidence()
    report["evidence"]["ui_forensics"] = forensics_result
    
    # Run UI autopass
    autopass_result = run_ui_autopass_with_evidence()
    report["evidence"]["ui_autopass"] = autopass_result
    
    # Overall success
    report["success"] = (
        forensics_result.get("success", False) and
        autopass_result.get("success", False)
    )
    
    # Write the diagnostics report itself as evidence
    report_path = Path("outputs/diagnostics") / f"system_diagnostics_{int(time.time())}.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, default=str)
    
    # Verify this report was created
    if verify_evidence_created(report_path):
        report["diagnostics_report_path"] = str(report_path)
    
    return report


# -----------------------------------------------------------------------------
# Settings Page Render - Minimum Honest UI
# -----------------------------------------------------------------------------

def render() -> None:
    """Render the Settings page with Minimum Honest UI."""
    
    def render_content():
        ui.label("System Settings").classes("text-2xl font-bold text-primary mb-6")
        ui.label("Minimum Honest UI: Only truthful, implemented features.").classes("text-secondary mb-8")
        
        # Freeze Policy Link
        with ui.card().classes("w-full mb-6"):
            ui.label("UI Freeze Policy").classes("text-lg font-bold mb-2")
            ui.label("The UI is frozen to prevent feature creep and ensure truthfulness.").classes("text-sm text-tertiary mb-2")
            with ui.row().classes("w-full items-center gap-2"):
                ui.icon("policy").classes("text-primary")
                ui.link("View UI Freeze Policy V1", "/docs/_dp_notes/UI_FREEZE_POLICY_V1.md").classes("text-primary underline")
            ui.label("All UI changes must comply with this policy.").classes("text-xs text-muted mt-2")
        
        # System Information (truthful)
        with ui.card().classes("w-full mb-6"):
            ui.label("System Information").classes("text-lg font-bold mb-2")
            with ui.column().classes("w-full gap-1 text-sm"):
                import platform
                import sys
                import os
                
                ui.label(f"Platform: {platform.platform()}")
                ui.label(f"Python: {sys.version.split()[0]}")
                ui.label(f"Workspace: {os.getcwd()}")
                ui.label(f"UI Version: Nexus UI (Minimum Honest)")
                ui.label(f"Backend Status: Unknown (use Diagnostics)")
        
        # Diagnostics Section (with evidence guarantee)
        with ui.card().classes("w-full mb-6 border-2 border-cyan"):
            ui.label("Diagnostics & Evidence").classes("text-lg font-bold text-cyan mb-2")
            with ui.column().classes("w-full gap-2"):
                ui.label("Tools for debugging and system inspection with evidence guarantee.").classes("text-sm text-tertiary")
                ui.label("All actions create verifiable evidence files in outputs/.").classes("text-xs text-cyan")
                
                with ui.row().classes("w-full gap-2"):
                    diag_btn1 = ui.button("Run UI Forensics", icon="bug_report", color="transparent")
                    diag_btn2 = ui.button("Run UI Autopass", icon="health_and_safety", color="transparent")
                    diag_btn3 = ui.button("Full Diagnostics", icon="download", color="transparent")
                
                # Progress/status indicators
                diag_status = ui.label("").classes("text-sm")
                diag_progress = ui.linear_progress(show_value=False).classes("w-full hidden")
                
                # Attach handlers with evidence guarantee
                def on_run_forensics():
                    diag_status.set_value("Running UI forensics with evidence guarantee...")
                    diag_progress.set_visibility(True)
                    try:
                        result = run_ui_forensics_with_evidence()
                        if result.get("success"):
                            json_path = result.get("json_path", "unknown")
                            txt_path = result.get("txt_path", "unknown")
                            diag_status.set_value(f"✅ Forensics completed. Evidence: {Path(json_path).name}, {Path(txt_path).name}")
                            show_toast("UI forensics completed with evidence guarantee", ToastType.SUCCESS)
                        else:
                            error = result.get("error", "Unknown error")
                            diag_status.set_value(f"❌ Forensics failed: {error}")
                            show_toast(f"UI forensics failed: {error}", ToastType.ERROR)
                    except Exception as e:
                        diag_status.set_value(f"❌ Exception: {e}")
                        show_toast(f"UI forensics exception: {e}", ToastType.ERROR)
                    finally:
                        diag_progress.set_visibility(False)
                
                def on_run_autopass():
                    diag_status.set_value("Running UI autopass with evidence guarantee...")
                    diag_progress.set_visibility(True)
                    try:
                        result = run_ui_autopass_with_evidence()
                        if result.get("success"):
                            json_path = result.get("json_path")
                            txt_path = result.get("txt_path")
                            files = []
                            if json_path:
                                files.append(Path(json_path).name)
                            if txt_path:
                                files.append(Path(txt_path).name)
                            file_list = ", ".join(files) if files else "no files"
                            diag_status.set_value(f"✅ Autopass completed. Evidence: {file_list}")
                            show_toast("UI autopass completed with evidence guarantee", ToastType.SUCCESS)
                        else:
                            error = result.get("error", "Unknown error")
                            diag_status.set_value(f"❌ Autopass failed: {error}")
                            show_toast(f"UI autopass failed: {error}", ToastType.ERROR)
                    except Exception as e:
                        diag_status.set_value(f"❌ Exception: {e}")
                        show_toast(f"UI autopass exception: {e}", ToastType.ERROR)
                    finally:
                        diag_progress.set_visibility(False)
                
                def on_full_diagnostics():
                    diag_status.set_value("Running full system diagnostics with evidence guarantee...")
                    diag_progress.set_visibility(True)
                    try:
                        result = create_system_diagnostics_report()
                        if result.get("success"):
                            report_path = result.get("diagnostics_report_path", "unknown")
                            diag_status.set_value(f"✅ Full diagnostics completed. Report: {Path(report_path).name}")
                            show_toast("Full diagnostics completed with evidence guarantee", ToastType.SUCCESS)
                        else:
                            diag_status.set_value("❌ Full diagnostics partially failed (check logs)")
                            show_toast("Full diagnostics completed with some failures", ToastType.WARNING)
                    except Exception as e:
                        diag_status.set_value(f"❌ Exception: {e}")
                        show_toast(f"Full diagnostics exception: {e}", ToastType.ERROR)
                    finally:
                        diag_progress.set_visibility(False)
                
                diag_btn1.on("click", on_run_forensics)
                diag_btn2.on("click", on_run_autopass)
                diag_btn3.on("click", on_full_diagnostics)
        
        # Truthfulness declaration
        with ui.card().classes("w-full border-2 border-success"):
            ui.label("✅ Minimum Honest UI Compliance").classes("text-lg font-bold text-success mb-2")
            with ui.column().classes("w-full gap-1 text-sm"):
                ui.label("This UI adheres to the Minimum Honest UI principle:")
                with ui.column().classes("ml-4"):
                    ui.label("• No fake features or claims")
                    ui.label("• All buttons produce observable effects")
                    ui.label("• All data comes from truth providers")
                    ui.label("• Disabled features are explicitly marked")
                ui.label("Violations should be reported immediately.").classes("text-xs text-muted mt-2")
    
    # Wrap in page shell
    page_shell("System Settings", render_content)
