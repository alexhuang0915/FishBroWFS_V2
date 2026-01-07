"""
Test registry preload works headless (missing dataset index file).

Ensures that supervisor startup does not crash when dataset index file is missing,
and registry endpoints return 200 with appropriate content (empty dataset list allowed).
"""

import subprocess
import time
import json
import urllib.request
import urllib.error
import tempfile
import shutil
import os
import sys
from pathlib import Path
import pytest
import psutil


def wait_for_supervisor(host: str, port: int, timeout: int = 10) -> bool:
    """Wait until supervisor /health endpoint returns 200."""
    start = time.time()
    url = f"http://{host}:{port}/health"
    while time.time() - start < timeout:
        try:
            with urllib.request.urlopen(url, timeout=1) as resp:
                if resp.status == 200:
                    return True
        except (urllib.error.URLError, ConnectionError):
            pass
        time.sleep(0.5)
    return False


def kill_process_tree(pid):
    """Kill process and its children."""
    try:
        parent = psutil.Process(pid)
        children = parent.children(recursive=True)
        for child in children:
            try:
                child.terminate()
            except psutil.NoSuchProcess:
                pass
        parent.terminate()
        gone, alive = psutil.wait_procs([parent] + children, timeout=5)
        for p in alive:
            try:
                p.kill()
            except psutil.NoSuchProcess:
                pass
    except psutil.NoSuchProcess:
        pass


@pytest.mark.integration
@pytest.mark.slow
def test_registry_preload_headless():
    """Start supervisor with missing dataset index file; verify registry endpoints work."""
    # Create a temporary outputs root that lacks datasets index
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        # Create minimal outputs structure (optional)
        outputs_root = tmp_path / "outputs"
        outputs_root.mkdir()
        # No datasets directory, so dataset index file will be missing

        # Start supervisor on a different port to avoid conflict with existing supervisor
        host = "127.0.0.1"
        port = 8001

        # Build environment with custom outputs root
        env = os.environ.copy()
        env["FISHBRO_OUTPUTS_ROOT"] = str(outputs_root)
        env["PYTHONPATH"] = str(Path(__file__).parent.parent.parent / "src")

        cmd = [
            sys.executable, "-m", "uvicorn", "control.api:app",
            "--host", host,
            "--port", str(port),
            "--reload",
        ]

        proc = subprocess.Popen(
            cmd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )

        try:
            # Wait for supervisor to start
            if not wait_for_supervisor(host, port, timeout=15):
                # If supervisor didn't start, capture logs for debugging
                stdout, stderr = proc.communicate(timeout=2)
                raise AssertionError(
                    f"Supervisor failed to start on {host}:{port}\n"
                    f"stdout: {stdout.decode()}\n"
                    f"stderr: {stderr.decode()}"
                )

            # Test registry endpoints
            base_url = f"http://{host}:{port}"

            # 1) Strategies registry
            url = f"{base_url}/api/v1/registry/strategies"
            with urllib.request.urlopen(url, timeout=5) as resp:
                assert resp.status == 200, f"Strategies endpoint returned {resp.status}"
                body = json.loads(resp.read().decode())
                assert isinstance(body, list), "Strategies response should be a list"
                assert len(body) > 0, "Strategies list should be non-empty"

            # 2) Instruments registry
            url = f"{base_url}/api/v1/registry/instruments"
            with urllib.request.urlopen(url, timeout=5) as resp:
                assert resp.status == 200, f"Instruments endpoint returned {resp.status}"
                body = json.loads(resp.read().decode())
                assert isinstance(body, list), "Instruments response should be a list"
                assert len(body) > 0, "Instruments list should be non-empty"

            # 3) Datasets registry (should be empty list, not 503)
            url = f"{base_url}/api/v1/registry/datasets"
            with urllib.request.urlopen(url, timeout=5) as resp:
                assert resp.status == 200, f"Datasets endpoint returned {resp.status}"
                body = json.loads(resp.read().decode())
                assert isinstance(body, list), "Datasets response should be a list"
                # Empty list is allowed (headless-safe)
                # No assertion on length; could be empty or non-empty if there are derived datasets

            # 4) Meta endpoints (should also work)
            url = f"{base_url}/api/v1/meta/strategies"
            with urllib.request.urlopen(url, timeout=5) as resp:
                assert resp.status == 200, f"Meta strategies endpoint returned {resp.status}"

            url = f"{base_url}/api/v1/meta/datasets"
            with urllib.request.urlopen(url, timeout=5) as resp:
                # Should return 200 with empty dataset list (or 503 if not preloaded?)
                # With our fix, it should return 200.
                assert resp.status == 200, f"Meta datasets endpoint returned {resp.status}"

            # 5) Health endpoint (already verified)
            url = f"{base_url}/health"
            with urllib.request.urlopen(url, timeout=5) as resp:
                assert resp.status == 200

            # If we reach here, all registry endpoints succeeded without 503.
            # That's the desired behavior for headless acceptance.

        finally:
            # Clean up supervisor process
            kill_process_tree(proc.pid)
            proc.wait(timeout=5)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])