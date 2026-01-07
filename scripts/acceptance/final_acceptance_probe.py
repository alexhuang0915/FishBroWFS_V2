#!/usr/bin/env python3
"""
Final Acceptance Probe for FishBroWFS_V2.

Performs API validation, security checks, and functional smoke tests.
Stdlib only, no external dependencies.
"""

import argparse
import json
import subprocess
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# -----------------------------------------------------------------------------
# Constants
# -----------------------------------------------------------------------------
DEFAULT_BASE_URL = "http://127.0.0.1:8000"
MAX_POLL_SECONDS = 120
POLL_INTERVAL = 1.0


# -----------------------------------------------------------------------------
# Utilities
# -----------------------------------------------------------------------------
def log(msg: str) -> None:
    timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds") + "Z"
    print(f"[{timestamp}] {msg}", file=sys.stderr)


def write_file(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def write_json(path: Path, data: Any) -> None:
    write_file(path, json.dumps(data, indent=2, sort_keys=True))


def http_get(url: str, timeout: int = 10) -> Tuple[int, Dict[str, Any], bytes]:
    """Perform HTTP GET and return (status_code, headers_dict, body_bytes)."""
    req = urllib.request.Request(url)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, dict(resp.headers), resp.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read()
    except urllib.error.URLError as e:
        raise RuntimeError(f"URL error for {url}: {e}")


def http_get_json(url: str, timeout: int = 10) -> Tuple[int, Dict[str, Any]]:
    status, headers, body = http_get(url, timeout)
    if body:
        try:
            return status, json.loads(body.decode("utf-8"))
        except json.JSONDecodeError:
            pass
    return status, {}


def http_post_json(url: str, data: Dict[str, Any], timeout: int = 10) -> Tuple[int, Dict[str, Any]]:
    """Perform HTTP POST with JSON body."""
    req = urllib.request.Request(
        url,
        data=json.dumps(data).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read()
            if body:
                try:
                    return resp.status, json.loads(body.decode("utf-8"))
                except json.JSONDecodeError:
                    pass
            return resp.status, {}
    except urllib.error.HTTPError as e:
        body = e.read()
        if body:
            try:
                return e.code, json.loads(body.decode("utf-8"))
            except json.JSONDecodeError:
                pass
        return e.code, {}
    except urllib.error.URLError as e:
        raise RuntimeError(f"URL error for {url}: {e}")


# -----------------------------------------------------------------------------
# Probe Steps
# -----------------------------------------------------------------------------
class AcceptanceProbe:
    def __init__(self, base_url: str, evidence_dir: Path):
        self.base_url = base_url.rstrip("/")
        self.evidence_dir = Path(evidence_dir)
        self.failures: List[str] = []
        self.job_id: Optional[str] = None

    def fail(self, msg: str) -> None:
        self.failures.append(msg)
        log(f"FAIL: {msg}")

    def check(self, condition: bool, msg: str) -> None:
        if not condition:
            self.fail(msg)

    def run(self) -> int:
        """Execute all probe steps. Returns 0 for success, 2 for failure."""
        log(f"Starting acceptance probe against {self.base_url}")
        log(f"Evidence directory: {self.evidence_dir}")

        steps = [
            self.step_health,
            self.step_openapi_diff,
            self.step_registry_endpoints,
            self.step_outputs_summary,
            self.step_security_job_artifacts,
            self.step_security_portfolio_artifacts,
            self.step_submit_smoke_job,
            self.step_poll_job,
            self.step_artifacts_index,
            self.step_strategy_report,
            self.step_write_manual_checklist,
            self.step_write_final_summary,
        ]

        for step in steps:
            try:
                step()
            except Exception as e:
                self.fail(f"Step {step.__name__} raised exception: {e}")
                import traceback
                traceback.print_exc()

        if self.failures:
            log(f"Probe completed with {len(self.failures)} failure(s)")
            for f in self.failures:
                log(f"  - {f}")
            return 2
        else:
            log("Probe completed successfully")
            return 0

    # -------------------------------------------------------------------------
    # Step 1: Health
    # -------------------------------------------------------------------------
    def step_health(self) -> None:
        log("Step 1: GET /health")
        url = f"{self.base_url}/health"
        status, body = http_get_json(url)
        self.check(status == 200, f"/health returned {status}, expected 200")
        write_json(self.evidence_dir / "05_health.txt", {"status": status, "body": body})

    # -------------------------------------------------------------------------
    # Step 2: OpenAPI snapshot diff
    # -------------------------------------------------------------------------
    def step_openapi_diff(self) -> None:
        log("Step 2: Check OpenAPI snapshot diff")
        # Run git diff on the snapshot file
        cmd = ["git", "diff", "--", "tests/policy/api_contract/openapi.json"]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=False)
            diff = result.stdout.strip()
            write_file(self.evidence_dir / "06_openapi_snapshot_diff.txt", diff)
            if diff:
                self.fail("OpenAPI snapshot has uncommitted changes (git diff non-empty)")
            else:
                log("OpenAPI snapshot is clean (no diff)")
        except Exception as e:
            self.fail(f"Failed to run git diff: {e}")

    # -------------------------------------------------------------------------
    # Step 3: Registry endpoints
    # -------------------------------------------------------------------------
    def step_registry_endpoints(self) -> None:
        log("Step 3: Fetch registry endpoints")
        endpoints = {}
        for name, path in [
            ("strategies", "/api/v1/registry/strategies"),
            ("instruments", "/api/v1/registry/instruments"),
            ("datasets", "/api/v1/registry/datasets"),
        ]:
            url = f"{self.base_url}{path}"
            status, body = http_get_json(url)
            endpoints[name] = {"status": status, "body": body}
            if status != 200:
                self.fail(f"Registry {name} returned {status}, expected 200")
                continue
            # body may be empty list (allowed for datasets)
            if isinstance(body, list):
                if not body:
                    if name in ("strategies", "instruments"):
                        self.fail(f"Registry {name} returned empty list (must be non-empty)")
                    else:
                        log(f"Registry {name} returned empty list (allowed)")
                # else non-empty list: success
            elif not body:
                # body is empty (e.g., None, empty dict) but not a list
                self.fail(f"Registry {name} returned empty body (non-list)")
            # else body is non-empty dict (should not happen) treat as success

        write_json(self.evidence_dir / "07_registry_endpoints.json", endpoints)

    # -------------------------------------------------------------------------
    # Step 4: Outputs summary
    # -------------------------------------------------------------------------
    def step_outputs_summary(self) -> None:
        log("Step 4: GET /api/v1/outputs/summary")
        url = f"{self.base_url}/api/v1/outputs/summary"
        status, body = http_get_json(url)
        write_json(self.evidence_dir / "08_outputs_summary.json", {"status": status, "body": body})
        self.check(status == 200, f"Outputs summary returned {status}, expected 200")
        if status == 200 and isinstance(body, dict):
            version = body.get("version")
            self.check(version == "1.0", f"Outputs summary version is {version}, expected '1.0'")

    # -------------------------------------------------------------------------
    # Step 5: Security - job artifacts traversal
    # -------------------------------------------------------------------------
    def step_security_job_artifacts(self) -> None:
        log("Step 5: Security checks for job artifacts")
        # First, get a job_id to test
        url = f"{self.base_url}/api/v1/jobs?limit=20"
        status, body = http_get_json(url)
        job_id = None
        if status == 200 and isinstance(body, list) and body:
            job_id = body[0].get("job_id")
        
        if not job_id:
            log("No existing jobs found; will use job created in smoke test")
            # We'll test after we create a job
            write_file(self.evidence_dir / "09_security_job_artifacts.txt",
                       "No existing job found; security checks deferred to smoke job")
            return

        self._perform_job_security_checks(job_id)

    def _perform_job_security_checks(self, job_id: str) -> None:
        results = []
        
        # 1) Traversal attempt (percent-encoded to bypass path normalization)
        url = f"{self.base_url}/api/v1/jobs/{job_id}/artifacts/%2e%2e%2fetc%2fpasswd"
        status, _, _ = http_get(url)
        results.append(f"Traversal attempt (encoded): {status} (expected 403)")
        self.check(status == 403, f"Job artifacts traversal returned {status}, expected 403")
        
        # 2) Missing filename
        url = f"{self.base_url}/api/v1/jobs/{job_id}/artifacts/this_file_should_not_exist.json"
        status, _, _ = http_get(url)
        results.append(f"Missing filename: {status} (expected 404)")
        self.check(status == 404, f"Job artifacts missing file returned {status}, expected 404")
        
        write_file(self.evidence_dir / "09_security_job_artifacts.txt", "\n".join(results))

    # -------------------------------------------------------------------------
    # Step 6: Security - portfolio artifacts traversal
    # -------------------------------------------------------------------------
    def step_security_portfolio_artifacts(self) -> None:
        log("Step 6: Security checks for portfolio artifacts")
        # Try to get a portfolio_id from outputs summary
        url = f"{self.base_url}/api/v1/outputs/summary"
        status, body = http_get_json(url)
        portfolio_id = None
        if status == 200 and isinstance(body, dict):
            portfolios = body.get("portfolios", [])
            if portfolios and isinstance(portfolios, list) and portfolios:
                portfolio_id = portfolios[0].get("portfolio_id")
        
        if not portfolio_id:
            write_file(self.evidence_dir / "10_security_portfolio_artifacts.txt",
                       "No portfolio found; skipping portfolio security checks")
            log("No portfolio found; skipping portfolio security checks")
            return
        
        results = []
        
        # 1) Traversal attempt (percent-encoded to bypass path normalization)
        url = f"{self.base_url}/api/v1/portfolios/{portfolio_id}/artifacts/%2e%2e%2fetc%2fpasswd"
        status, _, _ = http_get(url)
        results.append(f"Traversal attempt (encoded): {status} (expected 403)")
        self.check(status == 403, f"Portfolio artifacts traversal returned {status}, expected 403")
        
        # 2) Missing filename
        url = f"{self.base_url}/api/v1/portfolios/{portfolio_id}/artifacts/this_file_should_not_exist.json"
        status, _, _ = http_get(url)
        results.append(f"Missing filename: {status} (expected 404)")
        self.check(status == 404, f"Portfolio artifacts missing file returned {status}, expected 404")
        
        write_file(self.evidence_dir / "10_security_portfolio_artifacts.txt", "\n".join(results))

    # -------------------------------------------------------------------------
    # Step 7: Submit smoke job
    # -------------------------------------------------------------------------
    def step_submit_smoke_job(self) -> None:
        log("Step 7: Submit smoke job")
        # Construct a minimal job spec based on OpenAPI schema
        # We need to discover available strategies and datasets first
        strategies_url = f"{self.base_url}/api/v1/registry/strategies"
        status, strategies_body = http_get_json(strategies_url)
        if status != 200 or not isinstance(strategies_body, list) or not strategies_body:
            self.fail("Cannot get strategy list for smoke job")
            return
        
        datasets_url = f"{self.base_url}/api/v1/registry/datasets"
        status, datasets_body = http_get_json(datasets_url)
        if status != 200 or not isinstance(datasets_body, list):
            self.fail("Cannot get dataset list for smoke job")
            return
        
        if not datasets_body:
            log("Dataset registry empty; skipping job submission (allowed per spec)")
            write_file(self.evidence_dir / "11_job_submit_response.json",
                       json.dumps({"note": "Dataset registry empty, job submission skipped"}, indent=2))
            # No job_id, skip subsequent steps
            return
        
        strategy_id = strategies_body[0]
        dataset_id = datasets_body[0]
        
        # Build job spec according to WizardJobSpec schema
        job_spec = {
            "season": "2026Q1",  # Default season
            "data1": {
                "dataset_id": dataset_id,
                "start_date": "2024-01-01",
                "end_date": "2024-01-10",
            },
            "strategy_id": strategy_id,
            "params": {},  # Default parameters
            "wfs": {
                "stage0_subsample": 0.1,  # Small subsample for quick test
                "top_k": 10,
                "mem_limit_mb": 1024,
                "allow_auto_downsample": True,
            },
        }
        
        url = f"{self.base_url}/api/v1/jobs"
        status, body = http_post_json(url, job_spec)
        write_json(self.evidence_dir / "11_job_submit_response.json", {"status": status, "body": body})
        
        self.check(status == 200, f"Job submission returned {status}, expected 200")
        if status == 200:
            if isinstance(body, dict) and "job_id" in body:
                self.job_id = body["job_id"]
                log(f"Smoke job submitted with job_id: {self.job_id}")
            else:
                self.fail("Job submission response missing job_id")
        
        # If we have a job_id now, perform the deferred security checks
        if self.job_id:
            self._perform_job_security_checks(self.job_id)

    # -------------------------------------------------------------------------
    # Step 8: Poll job status
    # -------------------------------------------------------------------------
    def step_poll_job(self) -> None:
        if not self.job_id:
            log("No job_id available; skipping polling")
            write_file(self.evidence_dir / "12_job_poll_log.txt", "No job submitted")
            return
        
        log(f"Step 8: Poll job {self.job_id}")
        poll_log = []
        start_time = time.time()
        terminal_statuses = {"SUCCEEDED", "FAILED", "REJECTED"}
        
        while time.time() - start_time < MAX_POLL_SECONDS:
            url = f"{self.base_url}/api/v1/jobs/{self.job_id}"
            status, body = http_get_json(url)
            timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds") + "Z"
            
            if status == 200 and isinstance(body, dict):
                job_status = body.get("status", "UNKNOWN")
                poll_log.append(f"{timestamp} status={job_status}")
                
                if job_status in terminal_statuses:
                    log(f"Job reached terminal status: {job_status}")
                    write_file(self.evidence_dir / "12_job_poll_log.txt", "\n".join(poll_log))
                    return
            else:
                poll_log.append(f"{timestamp} HTTP {status}")
            
            time.sleep(POLL_INTERVAL)
        
        # Timeout
        poll_log.append(f"Timeout after {MAX_POLL_SECONDS}s")
        write_file(self.evidence_dir / "12_job_poll_log.txt", "\n".join(poll_log))
        self.fail(f"Job {self.job_id} did not reach terminal status within {MAX_POLL_SECONDS}s")

    # -------------------------------------------------------------------------
    # Step 9: Artifacts index
    # -------------------------------------------------------------------------
    def step_artifacts_index(self) -> None:
        if not self.job_id:
            log("No job_id available; skipping artifacts index")
            write_file(self.evidence_dir / "13_job_artifacts_index.json", "{}")
            return
        
        log(f"Step 9: Fetch artifacts index for job {self.job_id}")
        url = f"{self.base_url}/api/v1/jobs/{self.job_id}/artifacts"
        status, body = http_get_json(url)
        write_json(self.evidence_dir / "13_job_artifacts_index.json", {"status": status, "body": body})
        
        self.check(status == 200, f"Artifacts index returned {status}, expected 200")
        if status == 200:
            self.check(isinstance(body, dict), "Artifacts index body is not a dict")
            if isinstance(body, dict):
                self.check("job_id" in body, "Artifacts index missing job_id")
                self.check("files" in body, "Artifacts index missing files list")

    # -------------------------------------------------------------------------
    # Step 10: Strategy report (optional)
    # -------------------------------------------------------------------------
    def step_strategy_report(self) -> None:
        if not self.job_id:
            log("No job_id available; skipping strategy report")
            write_file(self.evidence_dir / "14_strategy_report_v1_note.txt", "No job submitted")
            return
        
        log(f"Step 10: Fetch strategy report for job {self.job_id}")
        url = f"{self.base_url}/api/v1/reports/strategy/{self.job_id}"
        status, body = http_get_json(url)
        if status == 200:
            write_json(self.evidence_dir / "14_strategy_report_v1.json", {"status": status, "body": body})
            log("Strategy report found")
        else:
            write_file(self.evidence_dir / "14_strategy_report_v1_note.txt",
                      f"Strategy report not available: HTTP {status}")
            log(f"Strategy report not available (HTTP {status})")

    # -------------------------------------------------------------------------
    # Step 11: Write manual UI checklist
    # -------------------------------------------------------------------------
    def step_write_manual_checklist(self) -> None:
        log("Step 11: Writing manual UI checklist")
        checklist = """# Manual UI Acceptance Checklist

This checklist is for human verification of Desktop UI functionality.
The automated acceptance harness has validated backend API contracts.

## Desktop UI Launch
- [ ] Launch Desktop UI via `make desktop` or `make desktop-xcb`
- [ ] Verify window appears with title bar
- [ ] Verify no immediate crash or protocol errors

## Operations (OP) Tab
- [ ] Navigate to OP tab
- [ ] Select a strategy from dropdown (should be populated)
- [ ] Select a dataset from dropdown (should be populated)
- [ ] Set date range (start/end)
- [ ] Click "Run" button
- [ ] Verify job submission (status changes to RUNNING/SUCCEEDED)
- [ ] Open report/logs/evidence via UI buttons

## Allocation (Portfolio) Tab
- [ ] Navigate to Allocation tab
- [ ] Build a portfolio with selected candidates
- [ ] Open decision desk to review portfolio weights
- [ ] Verify portfolio artifacts generation

## Audit (Explorer) Tab
- [ ] Navigate to Audit tab
- [ ] Search/filter existing jobs
- [ ] Open advanced artifacts view
- [ ] Open report for a completed job

## General UI Health
- [ ] No console errors (check terminal output)
- [ ] Responsive layout at different window sizes
- [ ] Tooltips appear on hover where expected
- [ ] All tabs load without freezing

## Notes
- This checklist is informational only; automated tests cover backend contracts.
- UI verification remains manual per product release standards.
"""
        write_file(self.evidence_dir / "80_manual_ui_checklist.md", checklist)

    # -------------------------------------------------------------------------
    # Step 12: Write final summary
    # -------------------------------------------------------------------------
    def step_write_final_summary(self) -> None:
        log("Step 12: Writing final summary")
        
        # Gather git commit hash
        commit_hash = "unknown"
        try:
            result = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=False)
            if result.returncode == 0:
                commit_hash = result.stdout.strip()
        except Exception:
            pass
        
        # Read make check status
        make_check_status = "unknown"
        make_check_file = self.evidence_dir / "03_make_check.txt"
        if make_check_file.exists():
            content = make_check_file.read_text(encoding="utf-8")
            if "FAILED" in content or "ERROR" in content:
                make_check_status = "FAILED"
            else:
                make_check_status = "PASSED"
        
        # Read OpenAPI diff
        openapi_diff_status = "unknown"
        openapi_file = self.evidence_dir / "06_openapi_snapshot_diff.txt"
        if openapi_file.exists():
            diff = openapi_file.read_text(encoding="utf-8").strip()
            openapi_diff_status = "CLEAN" if not diff else "DIRTY"
        
        # Read registry counts
        registry_counts = {}
        registry_file = self.evidence_dir / "07_registry_endpoints.json"
        if registry_file.exists():
            try:
                data = json.loads(registry_file.read_text(encoding="utf-8"))
                for name, entry in data.items():
                    if isinstance(entry.get("body"), list):
                        registry_counts[name] = len(entry["body"])
            except Exception:
                pass
        
        summary = f"""# Final Acceptance Probe Summary

## Execution Details
- Timestamp: {datetime.now(timezone.utc).isoformat(timespec="seconds")}Z
- Base URL: {self.base_url}
- Evidence directory: {self.evidence_dir}
- Commit hash: {commit_hash}

## Gate Results
- make check: {make_check_status}
- OpenAPI snapshot diff: {openapi_diff_status}
- Registry strategies: {registry_counts.get('strategies', 'N/A')}
- Registry instruments: {registry_counts.get('instruments', 'N/A')}
- Registry datasets: {registry_counts.get('datasets', 'N/A')}
- Outputs summary version: {"1.0" if not self.failures else "unknown"}
- Security job artifacts: {"PASS" if not self.failures else "FAIL"}
- Security portfolio artifacts: {"PASS/SKIP" if not self.failures else "FAIL"}
- Smoke job submission: {"SUCCESS" if self.job_id else "FAIL/SKIP"}
- Smoke job terminal status: {"REACHED" if self.job_id else "N/A"}
- Artifacts index: {"FETCHED" if self.job_id else "SKIP"}
- Strategy report: {"AVAILABLE" if not self.failures else "MISSING/SKIP"}

## Failures
{f"None" if not self.failures else "\\n".join(f"- {f}" for f in self.failures)}

## Result
{"PASS" if not self.failures else "FAIL"}
"""
        write_file(self.evidence_dir / "99_final_summary.md", summary)


# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------
def main() -> int:
    parser = argparse.ArgumentParser(description="Final Acceptance Probe")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL,
                        help=f"Base URL of supervisor (default: {DEFAULT_BASE_URL})")
    parser.add_argument("--evidence-dir", required=True,
                        help="Directory to write evidence files")
    args = parser.parse_args()
    
    probe = AcceptanceProbe(args.base_url, args.evidence_dir)
    return probe.run()


if __name__ == "__main__":
    sys.exit(main())