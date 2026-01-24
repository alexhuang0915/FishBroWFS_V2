from __future__ import annotations
import os
import signal
import subprocess
import time
import threading
import sys
from pathlib import Path
from typing import Dict, Optional, List
from datetime import datetime, timezone

from .db import SupervisorDB, get_default_db_path
from .models import HEARTBEAT_TIMEOUT_SEC, REAP_GRACE_SEC, now_iso


class Supervisor:
    """Main supervisor loop."""
    
    def __init__(
        self,
        db_path: Optional[Path] = None,
        max_workers: int = 4,
        tick_interval: float = 1.0,
        artifacts_root: Optional[Path] = None,
    ):
        from core.paths import get_artifacts_root
        self.db_path = db_path or get_default_db_path()
        self.max_workers = max_workers
        self.tick_interval = tick_interval
        self.artifacts_root = artifacts_root or get_artifacts_root()
        
        self.db = SupervisorDB(self.db_path)
        self.children: Dict[int, subprocess.Popen] = {}  # pid -> Popen
        self.running = False
        self._lock = threading.RLock()
        
        # Ensure artifacts directory exists
        self.artifacts_root.mkdir(parents=True, exist_ok=True)

        # Supervisor Identity
        import socket
        self.hostname = socket.gethostname()
        self.pid = os.getpid()
        self.supervisor_id = f"sup_{self.hostname}_{self.pid}"
    
    def spawn_worker(self, job_id: str) -> Optional[int]:
        """Spawn a worker process for the given job."""
        with self._lock:
            if len(self.children) >= self.max_workers:
                return None
            
            # Build bootstrap command
            cmd = [
                sys.executable, "-m", "control.supervisor.bootstrap",
                "--db", str(self.db_path),
                "--job-id", job_id,
                "--artifacts-root", str(self.artifacts_root)
            ]
            
            try:
                # Manually construct job dir to avoid double-nesting "artifacts"
                # get_job_artifact_dir expects outputs_root, but we have artifacts_root
                job_artifacts_dir = self.artifacts_root / "jobs" / job_id
                job_artifacts_dir.mkdir(parents=True, exist_ok=True)

                stdout_path = job_artifacts_dir / "worker_stdout.txt"
                stderr_path = job_artifacts_dir / "worker_stderr.txt"

                stdout_f = None
                stderr_f = None
                try:
                    stdout_f = open(stdout_path, "ab", buffering=0)
                    stderr_f = open(stderr_path, "ab", buffering=0)

                    env = os.environ.copy()
                    src_path = str(Path(__file__).resolve().parents[2])
                    pythonpath = env.get("PYTHONPATH", "")
                    if pythonpath:
                        if src_path not in pythonpath.split(os.pathsep):
                            pythonpath = f"{src_path}{os.pathsep}{pythonpath}"
                    else:
                        pythonpath = src_path
                    env["PYTHONPATH"] = pythonpath

                    proc = subprocess.Popen(
                        cmd,
                        stdout=stdout_f,
                        stderr=stderr_f,
                        start_new_session=True,
                        env=env,
                    )
                finally:
                    if stdout_f is not None:
                        stdout_f.close()
                    if stderr_f is not None:
                        stderr_f.close()
                self.children[proc.pid] = proc
                return proc.pid
            except Exception as e:
                print(f"ERROR: Failed to spawn worker for job {job_id}: {e}")
                return None
    
    def reap_children(self) -> None:
        """Reap exited child processes."""
        with self._lock:
            to_remove = []
            for pid, proc in self.children.items():
                retcode = proc.poll()
                if retcode is not None:
                    # Process has exited
                    to_remove.append(pid)
            
            for pid in to_remove:
                del self.children[pid]
    
    def kill_worker(self, pid: int, force: bool = False) -> bool:
        """Kill a worker process."""
        with self._lock:
            if pid not in self.children:
                # Try to kill via OS
                try:
                    if force:
                        os.kill(pid, signal.SIGKILL)
                    else:
                        os.kill(pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                return True
            
            proc = self.children[pid]
            try:
                if force:
                    proc.kill()
                else:
                    proc.terminate()
                # Wait briefly
                try:
                    proc.wait(timeout=1.0)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()
                del self.children[pid]
                return True
            except Exception as e:
                print(f"ERROR: Failed to kill worker {pid}: {e}")
                return False
    
    def handle_stale_jobs(self) -> None:
        """Detect and handle jobs with stale heartbeats."""
        now = now_iso()
        stale = self.db.find_running_jobs_stale(now, HEARTBEAT_TIMEOUT_SEC)
        
        for job in stale:
            print(f"WARNING: Job {job.job_id} has stale heartbeat, marking ORPHANED")
            error_details = {
                "type": "HeartbeatTimeout",
                "msg": "heartbeat_timeout",
                "timestamp": now_iso(),
                "phase": "supervisor"
            }
            if job.worker_pid:
                error_details["pid"] = job.worker_pid
            self.db.mark_orphaned(job.job_id, "heartbeat_timeout", error_details=error_details)
            
            # Kill associated worker if any
            if job.worker_pid:
                print(f"Killing stale worker {job.worker_pid} for job {job.job_id}")
                self.kill_worker(job.worker_pid, force=True)

    def handle_abort_requests(self) -> None:
        """Handle jobs with abort_requested flag."""
        from .models import JobStatus
        # Fetch QUEUED and RUNNING jobs with abort_requested = 1
        with self.db._connect() as conn:
            cursor = conn.execute("""
                SELECT * FROM jobs
                WHERE abort_requested = 1
                AND state IN (?, ?)
            """, (JobStatus.QUEUED, JobStatus.RUNNING))
            rows = cursor.fetchall()
        
        for row in rows:
            job = self.db.get_job_row(row["job_id"])  # convert to JobRow
            if job is None:
                continue
            if job.state == JobStatus.QUEUED:
                # Directly transition to ABORTED
                error_details = {
                    "type": "AbortRequested",
                    "msg": "user_abort",
                    "timestamp": now_iso(),
                    "phase": "supervisor"
                }
                self.db.mark_aborted(job.job_id, "user_abort", error_details=error_details)
                print(f"Aborted QUEUED job {job.job_id}")
            elif job.state == JobStatus.RUNNING:
                # Kill worker process
                pid = job.worker_pid
                process_missing = False
                if pid is not None:
                    print(f"Aborting RUNNING job {job.job_id}, killing worker {pid}")
                    # Check if process already dead before attempting kill
                    try:
                        os.kill(pid, 0)
                    except ProcessLookupError:
                        process_missing = True
                    
                    if not process_missing:
                        # Send SIGTERM to process group
                        try:
                            os.killpg(pid, signal.SIGTERM)
                        except ProcessLookupError:
                            # Process died between check and kill
                            process_missing = True
                        except Exception:
                            # Fallback to os.kill
                            try:
                                os.kill(pid, signal.SIGTERM)
                            except ProcessLookupError:
                                process_missing = True
                        
                        # Wait up to 5 seconds for termination
                        waited = 0
                        while waited < 5 and not process_missing:
                            try:
                                os.kill(pid, 0)  # check if process exists
                            except ProcessLookupError:
                                # process dead
                                break
                            time.sleep(0.1)
                            waited += 0.1
                        
                        # If still alive, SIGKILL
                        if not process_missing:
                            try:
                                os.killpg(pid, signal.SIGKILL)
                            except ProcessLookupError:
                                process_missing = True
                            except Exception:
                                try:
                                    os.kill(pid, signal.SIGKILL)
                                except ProcessLookupError:
                                    process_missing = True
                    
                    # Remove from children dict if present
                    if pid in self.children:
                        del self.children[pid]
                
                # Mark job as ABORTED with error_details including PID
                error_details = {
                    "type": "AbortRequested",
                    "msg": "user_abort",
                    "timestamp": now_iso(),
                    "phase": "supervisor"
                }
                if pid is not None:
                    error_details["pid"] = pid
                if process_missing:
                    error_details["process_missing"] = True
                self.db.mark_aborted(job.job_id, "user_abort", error_details=error_details)
                print(f"Aborted RUNNING job {job.job_id}")
    
    def tick(self) -> List[str]:
        """Perform one supervisor tick.

        Returns:
            List of job_ids spawned this tick.
        """
        # 0. Heartbeat self
        try:
            self.db.heartbeat_supervisor(self.supervisor_id)
        except Exception as e:
            print(f"Supervisor heartbeat failed: {e}")

        # 1. Reap exited children
        self.reap_children()
        
        # 2. Handle stale jobs
        self.handle_stale_jobs()
        
        # 3. Handle abort requests
        self.handle_abort_requests()
        
        # 4. Spawn workers for queued jobs
        available_slots = self.max_workers - len(self.children)
        spawned: List[str] = []
        for _ in range(available_slots):
            job_id = self.db.fetch_next_queued_job()
            if job_id is None:
                break
            pid = self.spawn_worker(job_id)
            if pid is None:
                # No more slots
                break
            print(f"Spawned worker {pid} for job {job_id}")
            spawned.append(job_id)
        return spawned
    
    def run_forever(self) -> None:
        """Run supervisor loop forever."""
        self.running = True
        print(f"Supervisor started (max_workers={self.max_workers}, db={self.db_path})")
        
        # Register self
        try:
            self.db.register_supervisor(self.supervisor_id, self.pid, self.hostname)
        except Exception as e:
            print(f"Failed to register supervisor: {e}")

        try:
            while self.running:
                self.tick()
                time.sleep(self.tick_interval)
        except KeyboardInterrupt:
            print("\nSupervisor shutting down...")
        finally:
            self.shutdown()
    
    def shutdown(self) -> None:
        """Shutdown supervisor and all workers."""
        self.running = False
        print("Shutting down workers...")
        
        with self._lock:
            # First SIGTERM
            for pid in list(self.children.keys()):
                self.kill_worker(pid, force=False)
            
            # Wait a bit
            time.sleep(0.5)
            
            # Then SIGKILL any remaining
            for pid in list(self.children.keys()):
                self.kill_worker(pid, force=True)
            
            self.children.clear()
        
        print("Supervisor shutdown complete")


# Import sys at module level
import sys


def main() -> None:
    """Entry point for supervisor CLI."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Supervisor main loop")
    parser.add_argument("--db", type=Path, default=None,
                       help="Path to jobs_v2.db (default: outputs/runtime/jobs_v2.db)")
    parser.add_argument("--max-workers", type=int, default=4,
                       help="Maximum concurrent workers")
    parser.add_argument("--tick-interval", type=float, default=1.0,
                       help="Tick interval in seconds")
    parser.add_argument("--artifacts-root", type=Path, default=None,
                       help="Artifacts root directory")
    
    args = parser.parse_args()
    
    supervisor = Supervisor(
        db_path=args.db,
        max_workers=args.max_workers,
        tick_interval=args.tick_interval,
        artifacts_root=args.artifacts_root
    )
    
    supervisor.run_forever()


if __name__ == "__main__":
    main()
