"""Minimal server helper for ASGI tests."""
import subprocess
import time
import os
import sys
import urllib.request
import urllib.error
import logging
from typing import Optional

logger = logging.getLogger(__name__)


def start_test_server(port: int = 18080) -> subprocess.Popen:
    """Start the UI server as a subprocess for testing.
    
    Returns:
        subprocess.Popen instance representing the server process.
    """
    # Ensure we're in the project root
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    os.chdir(project_root)

    # Build command: python main.py with the given port
    cmd = [sys.executable, "main.py", "--port", str(port)]
    env = os.environ.copy()
    env.update({
        "PYTHONPATH": f"src:{env.get('PYTHONPATH', '')}",
        "PYTHONDONTWRITEBYTECODE": "1",
    })

    logger.info("Starting test server on port %d", port)
    proc = subprocess.Popen(
        cmd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )
    return proc


def wait_for_server_ready(url: str, timeout_s: float = 45.0) -> None:
    """Wait until the given URL returns HTTP 200 (or any 2xx).
    
    Raises:
        TimeoutError: If the server does not become responsive within timeout.
    """
    start = time.monotonic()
    while time.monotonic() - start < timeout_s:
        try:
            with urllib.request.urlopen(url, timeout=2) as resp:
                if 200 <= resp.status < 300:
                    logger.info("Server %s is ready (HTTP %d)", url, resp.status)
                    return
        except (urllib.error.URLError, ConnectionError, OSError) as e:
            # Server not ready yet
            time.sleep(0.5)
            continue
    raise TimeoutError(f"Server {url} did not respond with HTTP 2xx within {timeout_s}s")


def stop_server(proc: subprocess.Popen) -> None:
    """Stop a subprocess gracefully, then kill if needed."""
    if proc.poll() is None:
        logger.info("Terminating test server (pid=%d)", proc.pid)
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            logger.warning("Test server did not terminate gracefully, killing")
            proc.kill()
            proc.wait()
    # Read any remaining output to avoid resource warnings
    if proc.stdout:
        proc.stdout.close()
    if proc.stderr:
        proc.stderr.close()