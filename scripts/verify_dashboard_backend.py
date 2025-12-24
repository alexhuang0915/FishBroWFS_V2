#!/usr/bin/env python3
"""
Dashboard Backend Verifier - Functional-level contract validation.

Validates R1/R3/R5/S1/S2 rules for FishBroWFS_V2 dashboard backend.
"""

import argparse
import ast
import os
import re
import signal
import subprocess
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path
from typing import List, Tuple, Optional, Dict, Any

RE_URL = re.compile(r"http://(?:127\.0\.0\.1|0\.0\.0\.0|localhost):\d+/?")
BANNED_TOPLEVEL_CALLS = {
    "open", "unlink", "remove", "rmdir", "mkdir", "makedirs", "rmtree",
    "write_text", "write_bytes", "rename", "replace", "touch", "connect"
}


def eprint(*args, **kwargs) -> None:
    """Print to stderr."""
    print(*args, file=sys.stderr, **kwargs)


def http_head(url: str, timeout: float = 2.0) -> Tuple[int, str]:
    """Perform HTTP HEAD request."""
    req = urllib.request.Request(url, method="HEAD")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.getheader("content-type") or ""
    except urllib.error.HTTPError as he:
        return int(he.code), ""
    except Exception as ex:
        raise RuntimeError(str(ex))


def http_get(url: str, timeout: float = 3.0) -> int:
    """Perform HTTP GET request."""
    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            resp.read(256)  # Read some bytes to complete request
            return resp.status
    except urllib.error.HTTPError as he:
        return int(he.code)


def start_dashboard(
    make_cmd: List[str], env: Dict[str, str], timeout: float = 15.0
) -> Tuple[subprocess.Popen, Optional[str], List[str]]:
    """Start dashboard process and capture URL."""
    proc = subprocess.Popen(
        make_cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        env=env,
        preexec_fn=os.setsid,
    )
    lines: List[str] = []
    url: Optional[str] = None
    start = time.time()
    
    while time.time() - start < timeout:
        if proc.poll() is not None:
            break
        line = proc.stdout.readline() if proc.stdout else ""
        if not line:
            time.sleep(0.1)
            continue
        line = line.rstrip("\n")
        lines.append(line)
        m = RE_URL.search(line)
        if m and url is None:
            url = m.group(0).rstrip("/")
            if len(lines) >= 5:
                break
    
    return proc, url, lines


def stop_process_group(proc: subprocess.Popen) -> None:
    """Stop process group gracefully."""
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
    except Exception:
        try:
            proc.terminate()
        except Exception:
            pass
    try:
        proc.wait(timeout=5)
    except Exception:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except Exception:
            pass


def r3_actions_freeze_gate(actions_py: Path) -> Tuple[bool, str]:
    """R3: Verify run_action contains check_season_not_frozen after enforce_action_policy."""
    try:
        tree = ast.parse(actions_py.read_text(encoding="utf-8"), filename=str(actions_py))
    except SyntaxError as e:
        return False, f"SyntaxError: {e}"
    
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "run_action":
            body = node.body[:]
            # Skip docstring if present
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                body = body[1:]
            
            if not body:
                return False, "run_action empty"
            
            # 檢查第一個語句是否為 enforce_action_policy（R6）
            first = body[0]
            is_enforce_call = False
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Call):
                fn = first.value.func
                if isinstance(fn, ast.Name) and fn.id == "enforce_action_policy":
                    is_enforce_call = True
                elif isinstance(fn, ast.Attribute) and fn.attr == "enforce_action_policy":
                    is_enforce_call = True
            elif isinstance(first, ast.Assign) and isinstance(first.value, ast.Call):
                fn = first.value.func
                if isinstance(fn, ast.Name) and fn.id == "enforce_action_policy":
                    is_enforce_call = True
                elif isinstance(fn, ast.Attribute) and fn.attr == "enforce_action_policy":
                    is_enforce_call = True
            
            if not is_enforce_call:
                # 如果第一個語句不是 enforce_action_policy，檢查是否為 check_season_not_frozen（舊版 R3）
                if isinstance(first, ast.Expr) and isinstance(first.value, ast.Call):
                    fn = first.value.func
                    if isinstance(fn, ast.Name) and fn.id == "check_season_not_frozen":
                        return True, "OK (legacy R3 only, missing R6)"
                return False, f"first stmt not enforce_action_policy: {type(first).__name__}"
            
            # 現在在 enforce_action_policy 之後搜索 check_season_not_frozen
            # 跳過第一個語句，從第二個開始搜索
            found_check = False
            for stmt in body[1:]:
                # 檢查是否為 check_season_not_frozen 調用
                if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call):
                    fn = stmt.value.func
                    if isinstance(fn, ast.Name) and fn.id == "check_season_not_frozen":
                        found_check = True
                        break
                elif isinstance(stmt, ast.Assign) and isinstance(stmt.value, ast.Call):
                    fn = stmt.value.func
                    if isinstance(fn, ast.Name) and fn.id == "check_season_not_frozen":
                        found_check = True
                        break
                # 也檢查在 If 語句內部的情況（但當前實作中 check_season_not_frozen 在 If 之後）
            
            if found_check:
                return True, "OK (R6+R3 satisfied)"
            else:
                return False, "check_season_not_frozen not found after enforce_action_policy"
    
    return False, "run_action not found"


def r6_action_policy_gate(actions_py: Path) -> Tuple[bool, str]:
    """R6: Verify run_action first statement is enforce_action_policy."""
    try:
        tree = ast.parse(actions_py.read_text(encoding="utf-8"), filename=str(actions_py))
    except SyntaxError as e:
        return False, f"SyntaxError: {e}"
    
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "run_action":
            body = node.body[:]
            # Skip docstring if present
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                body = body[1:]
            
            if not body:
                return False, "run_action empty"
            
            first = body[0]
            # Check for enforce_action_policy call
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Call):
                fn = first.value.func
                if isinstance(fn, ast.Name) and fn.id == "enforce_action_policy":
                    return True, "OK"
                elif isinstance(fn, ast.Attribute) and fn.attr == "enforce_action_policy":
                    return True, "OK (attribute)"
            
            # Also check for assignment pattern: policy_decision = enforce_action_policy(...)
            if isinstance(first, ast.Assign):
                if isinstance(first.value, ast.Call):
                    fn = first.value.func
                    if isinstance(fn, ast.Name) and fn.id == "enforce_action_policy":
                        return True, "OK (assignment)"
                    elif isinstance(fn, ast.Attribute) and fn.attr == "enforce_action_policy":
                        return True, "OK (assignment attribute)"
            
            return False, f"first stmt not enforce_action_policy: {type(first).__name__}"
    
    return False, "run_action not found"


def r5_audit_append_only(audit_py: Path) -> Tuple[bool, str]:
    """R5: Verify audit_log.py uses append-only open."""
    try:
        src = audit_py.read_text(encoding="utf-8")
    except Exception as e:
        return False, f"read error: {e}"
    
    compact = src.replace(" ", "")
    
    # Must have at least one open()
    if "open(" not in src:
        return False, "no open()"
    
    # Must NOT have write mode "w"
    if '"w"' in compact or "'w'" in compact:
        return False, "found write-mode open('w') in audit_log.py"
    
    # Must have append mode "a"
    if ",'a'" in compact or ',"a"' in compact or "'a'," in src or '"a",' in src:
        return True, "OK"
    
    return False, "no append-mode open('a') detected"


def r1_no_import_time_io(src_root: Path) -> Tuple[bool, List[str]]:
    """R1: Detect top-level IO calls in src modules."""
    violations: List[str] = []
    
    for py in src_root.rglob("*.py"):
        try:
            mod = ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
        except SyntaxError as se:
            violations.append(f"{py}: SyntaxError: {se}")
            continue
        
        for st in mod.body:
            # Skip function and class definitions
            if isinstance(st, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            
            call = None
            if isinstance(st, ast.Expr) and isinstance(st.value, ast.Call):
                call = st.value
            elif isinstance(st, ast.Assign) and isinstance(st.value, ast.Call):
                call = st.value
            elif isinstance(st, ast.AnnAssign) and isinstance(st.value, ast.Call):
                call = st.value
            
            if not call:
                continue
            
            fn = call.func
            name = None
            if isinstance(fn, ast.Name):
                name = fn.id
            elif isinstance(fn, ast.Attribute):
                name = fn.attr
            
            if name in BANNED_TOPLEVEL_CALLS:
                violations.append(f"{py}:{st.lineno} top-level call {name}()")
    
    return (len(violations) == 0), violations


def main() -> int:
    """Main entry point."""
    ap = argparse.ArgumentParser(
        description="Dashboard Backend Verifier - Functional contract validation"
    )
    ap.add_argument(
        "--no-server",
        action="store_true",
        help="Skip dashboard server tests (R1/R3/R5 only)"
    )
    ap.add_argument(
        "--port",
        type=int,
        default=None,
        help="Use specified port instead of detecting from make dashboard"
    )
    ap.add_argument(
        "--make-cmd",
        default="make dashboard",
        help="Command to start dashboard (default: 'make dashboard')"
    )
    ap.add_argument(
        "--startup-timeout",
        type=int,
        default=15,
        help="Timeout in seconds for dashboard startup and HTTP responsiveness (default: 15)"
    )
    args = ap.parse_args()
    
    # Verify we're in repo root
    root = Path.cwd()
    if not (root / "src" / "FishBroWFS_V2").exists():
        eprint("ERROR: Must run from repo root")
        return 2
    
    results: List[Tuple[str, bool, str]] = []
    
    # Paths
    actions_py = root / "src/FishBroWFS_V2/gui/services/actions.py"
    audit_py = root / "src/FishBroWFS_V2/gui/services/audit_log.py"
    src_root = root / "src/FishBroWFS_V2"
    
    # R3: Actions freeze gate (legacy)
    ok, msg = r3_actions_freeze_gate(actions_py)
    results.append(("R3 actions.run_action freeze-gate first statement", ok, msg))
    
    # R6: Action policy gate (M4)
    ok, msg = r6_action_policy_gate(actions_py)
    results.append(("R6 actions.run_action policy-gate first statement", ok, msg))
    
    # R5: Audit append-only
    ok, msg = r5_audit_append_only(audit_py)
    results.append(("R5 audit append-only", ok, msg))
    
    # R1: No import-time IO
    ok, violations = r1_no_import_time_io(src_root)
    results.append(("R1 no import-time IO", ok, "OK" if ok else f"{len(violations)} violations"))
    if not ok:
        for v in violations[:20]:
            eprint("  VIOL:", v)
    
    # Server tests (S1, S2)
    proc = None
    url = None
    logs: List[str] = []
    
    if not args.no_server:
        env = os.environ.copy()
        env.setdefault("PYTHONPATH", "src")
        
        # Start dashboard with timeout
        proc, url, logs = start_dashboard(args.make_cmd.split(), env, timeout=args.startup_timeout)
        
        if args.port is not None:
            url = f"http://127.0.0.1:{args.port}"
        
        if url is None:
            results.append((
                "S1 dashboard server responds (HTTP < 500)",
                False,
                f"no url detected within {args.startup_timeout}s; use --port"
            ))
            # Kill process if still running
            if proc:
                stop_process_group(proc)
                proc = None
        else:
            # Test server responsiveness with timeout
            responsive = False
            last_error = ""
            start_time = time.time()
            while time.time() - start_time < args.startup_timeout:
                try:
                    status, _ = http_head(url + "/")
                    if status < 500:
                        responsive = True
                        break
                except Exception as ex:
                    last_error = str(ex)
                time.sleep(0.3)
            
            if not responsive:
                results.append((
                    "S1 dashboard server responds (HTTP < 500)",
                    False,
                    f"url={url} timeout={args.startup_timeout}s err={last_error}"
                ))
                # Kill process if still running
                if proc:
                    stop_process_group(proc)
                    proc = None
            else:
                results.append((
                    "S1 dashboard server responds (HTTP < 500)",
                    True,
                    f"url={url}"
                ))
                
                # S2: Route probing with required/optional paths
                REQUIRED_PATHS = ["/", "/history", "/health"]
                OPTIONAL_PATHS = ["/viewer", "/dashboard", "/api/health"]
                
                bad_required: List[str] = []
                bad_optional: List[str] = []
                optional_404: List[str] = []
                
                # Test required paths
                for path in REQUIRED_PATHS:
                    try:
                        status = http_get(url + path)
                        if status == 404 or status >= 500:
                            bad_required.append(f"{path}=>{status}")
                    except Exception as ex:
                        bad_required.append(f"{path}=>EXC {ex}")
                
                # Test optional paths
                for path in OPTIONAL_PATHS:
                    try:
                        status = http_get(url + path)
                        if status >= 500:
                            bad_optional.append(f"{path}=>{status}")
                        elif status == 404:
                            optional_404.append(f"{path}=>404")
                    except Exception as ex:
                        bad_optional.append(f"{path}=>EXC {ex}")
                
                # Build result message
                s2_ok = len(bad_required) == 0 and len(bad_optional) == 0
                s2_msg_parts = []
                if bad_required:
                    s2_msg_parts.append(f"REQUIRED_FAIL: {', '.join(bad_required)}")
                if bad_optional:
                    s2_msg_parts.append(f"OPTIONAL_FAIL: {', '.join(bad_optional)}")
                if optional_404:
                    s2_msg_parts.append(f"OPTIONAL_404: {', '.join(optional_404)}")
                if not s2_msg_parts:
                    s2_msg_parts.append("OK")
                
                results.append((
                    "S2 routes probe",
                    s2_ok,
                    "; ".join(s2_msg_parts)
                ))
    
    # Clean up dashboard process
    if proc:
        stop_process_group(proc)
    
    # Print results
    print("\n=== Dashboard Backend Smoke Test ===")
    fails = 0
    for name, ok, msg in results:
        status = "PASS" if ok else "FAIL"
        print(f"[{status}] {name} :: {msg}")
        if not ok:
            fails += 1
    
    # Print logs if available
    if logs:
        print("\n--- dashboard logs (first 40 lines) ---")
        for ln in logs[:40]:
            print(ln)
    
    # Overall result
    if fails == 0:
        print("\nOVERALL: PASS ✅")
        return 0
    else:
        print(f"\nOVERALL: FAIL ❌ (failed checks: {fails})")
        return 1


if __name__ == "__main__":
    sys.exit(main())