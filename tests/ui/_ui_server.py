"""UI server lifecycle helper for Playwright contract tests.

Provides functions to start, wait for, and stop the UI server in a subprocess.
"""
import subprocess
import time
import logging
import sys
import os
from typing import Optional
import urllib.request
import urllib.error

logger = logging.getLogger(__name__)


def start_ui_server(port: int = 8080) -> subprocess.Popen:
    """Start the UI server as a subprocess.

    Args:
        port: Port to bind the server to.

    Returns:
        subprocess.Popen instance representing the server process.
    """
    # Ensure we're in the project root
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    os.chdir(project_root)

    # Build command: python main.py with the given port
    cmd = [sys.executable, "main.py"]
    env = os.environ.copy()
    env.update({
        "PYTHONPATH": f"src:{env.get('PYTHONPATH', '')}",
        "PYTHONDONTWRITEBYTECODE": "1",
    })

    logger.info("Starting UI server on port %d with command: %s", port, " ".join(cmd))
    proc = subprocess.Popen(
        cmd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )
    return proc


def wait_for_http_ok(url: str, timeout_s: float = 30.0) -> None:
    """Wait until the given URL returns HTTP 200.

    Args:
        url: URL to poll.
        timeout_s: Maximum time to wait in seconds.

    Raises:
        TimeoutError: If the server does not become responsive within timeout.
    """
    start = time.monotonic()
    while time.monotonic() - start < timeout_s:
        try:
            with urllib.request.urlopen(url, timeout=2) as resp:
                if resp.status == 200:
                    logger.info("Server %s is ready (HTTP 200)", url)
                    return
        except (urllib.error.URLError, ConnectionError, OSError) as e:
            # Server not ready yet
            time.sleep(0.5)
            continue
    raise TimeoutError(f"Server {url} did not respond with HTTP 200 within {timeout_s}s")


def stop_process(proc: subprocess.Popen) -> None:
    """Stop a subprocess gracefully, then kill if needed.

    Args:
        proc: The subprocess to stop.
    """
    if proc.poll() is None:
        logger.info("Terminating UI server (pid=%d)", proc.pid)
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            logger.warning("UI server did not terminate gracefully, killing")
            proc.kill()
            proc.wait()
    # Read any remaining output to avoid resource warnings
    if proc.stdout:
        proc.stdout.close()
    if proc.stderr:
        proc.stderr.close()