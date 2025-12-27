import asyncio
import os
import sys
from datetime import datetime

class WarRoomService:
    # 腳本對應表
    SCRIPT_MAP = {
        'research': 'scripts/run_research_v3.py',
        'plateau': 'scripts/run_phase3a_plateau.py',
        'freeze': 'scripts/run_phase3b_freeze.py',
        'compile': 'scripts/run_phase3c_compile.py',
        'kill_stray_workers': 'scripts/kill_stray_workers.py',
        'topology_probe': 'scripts/topology_probe.py'
    }

    def __init__(self):
        self._running = False
        self._current_script = None
        self._exit_code = None
        self._log_buffer = []

    def get_script_status(self):
        return {
            'running': self._running,
            'script': self._current_script,
            'exit_code': self._exit_code
        }

    def get_script_log(self):
        if not self._log_buffer: return ""
        logs = "\n".join(self._log_buffer)
        self._log_buffer = []
        return logs

    async def run_script(self, script_key: str):
        if self._running:
            self._log_buffer.append(f"[SYS] Error: Script is busy.")
            return

        script_path = self.SCRIPT_MAP.get(script_key)
        if not script_path or not os.path.exists(script_path):
             self._log_buffer.append(f"[SYS] Error: Script not found: {script_path}")
             return

        self._running = True
        self._current_script = script_key
        self._log_buffer.append(f">>> STARTING {script_key.upper()} ...")

        try:
            # 設定環境變數，確保子進程能吃到 src
            env = os.environ.copy()
            src_path = os.path.abspath("src")
            env["PYTHONPATH"] = src_path + os.pathsep + env.get("PYTHONPATH", "")

            process = await asyncio.create_subprocess_exec(
                sys.executable, "-u", script_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env
            )

            await asyncio.gather(
                self._stream(process.stdout, "LOG"),
                self._stream(process.stderr, "ERR")
            )

            self._exit_code = await process.wait()
            status = "SUCCESS" if self._exit_code == 0 else f"FAIL ({self._exit_code})"
            self._log_buffer.append(f">>> {script_key.upper()} FINISHED: {status}")

        except Exception as e:
            self._log_buffer.append(f"[SYS] Exception: {e}")
        finally:
            self._running = False

    async def _stream(self, stream, prefix):
        while True:
            line = await stream.readline()
            if not line: break
            decoded = line.decode('utf-8', errors='replace').rstrip()
            if decoded: self._log_buffer.append(f"[{prefix}] {decoded}")