from __future__ import annotations
import os
import signal
import subprocess
import time
import threading
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
        artifacts_root: Optional[Path] = None
    ):
        self.db_path = db_path or get_default_db_path()
        self.max_workers = max_workers
        self.tick_interval = tick_interval
        self.artifacts_root = artifacts_root or Path("outputs/_dp_evidence/supervisor_artifacts")
        
        self.db = SupervisorDB(self.db_path)
        self.children: Dict[int, subprocess.Popen] = {}  # pid -> Popen
        self.running = False
        self._lock = threading.RLock()
        
        # Ensure artifacts directory exists
        self.artifacts_root.mkdir(parents=True, exist_ok=True)
    
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
                # Start process with new process group for clean kill
                proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    start_new_session=True,
                    env=os.environ.copy()
                )
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
                    # Read any remaining output
                    try:
                        stdout, stderr = proc.communicate(timeout=0.1)
                        if stdout:
                            print(f"Worker {pid} stdout: {stdout.decode()[:200]}")
                        if stderr:
                            print(f"Worker {pid} stderr: {stderr.decode()[:200]}")
                    except Exception:
                        pass
            
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
            self.db.mark_orphaned(job.job_id, "heartbeat_timeout")
            
            # Kill associated worker if any
            if job.worker_pid:
                print(f"Killing stale worker {job.worker_pid} for job {job.job_id}")
                self.kill_worker(job.worker_pid, force=True)
    
    def tick(self) -> None:
        """Perform one supervisor tick."""
        # 1. Reap exited children
        self.reap_children()
        
        # 2. Handle stale jobs
        self.handle_stale_jobs()
        
        # 3. Spawn workers for queued jobs
        available_slots = self.max_workers - len(self.children)
        for _ in range(available_slots):
            job_id = self.db.fetch_next_queued_job()
            if job_id is None:
                break
            pid = self.spawn_worker(job_id)
            if pid is None:
                # No more slots
                break
            print(f"Spawned worker {pid} for job {job_id}")
    
    def run_forever(self) -> None:
        """Run supervisor loop forever."""
        self.running = True
        print(f"Supervisor started (max_workers={self.max_workers}, db={self.db_path})")
        
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
                       help="Path to jobs_v2.db (default: outputs/jobs_v2.db)")
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