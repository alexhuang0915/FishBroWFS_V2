from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence
import os
import subprocess
import sys


@dataclass(frozen=True)
class ExecResult:
    returncode: int
    stdout: str
    stderr: str


def run_python_module(
    module: str,
    args: Sequence[str],
    *,
    cwd: Path,
    env: Mapping[str, str] | None = None,
    timeout_s: int = 60,
) -> ExecResult:
    """
    Runs: sys.executable -m <module> <args...>
    Ensures PYTHONPATH contains <repo>/src for imports.
    """
    base_env = os.environ.copy()
    if env:
        base_env.update(env)

    pythonpath = base_env.get("PYTHONPATH", "")
    src_path = str(Path(__file__).resolve().parents[1])
    if pythonpath:
        if src_path not in pythonpath.split(os.pathsep):
            pythonpath = f"{src_path}{os.pathsep}{pythonpath}"
    else:
        pythonpath = src_path
    base_env["PYTHONPATH"] = pythonpath

    result = subprocess.run(
        [sys.executable, "-m", module, *args],
        cwd=str(cwd),
        env=base_env,
        capture_output=True,
        text=True,
        timeout=timeout_s,
    )
    return ExecResult(
        returncode=result.returncode,
        stdout=result.stdout or "",
        stderr=result.stderr or "",
    )
