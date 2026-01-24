
import time
import os
import sys
from pathlib import Path

# Add src to sys.path
src_path = str(Path.cwd() / "src")
if src_path not in sys.path:
    sys.path.insert(0, src_path)

from control.supervisor.db import get_default_db_path, SupervisorDB
from control.supervisor.models import now_iso

def main():
    db_path = get_default_db_path()
    db = SupervisorDB(db_path)
    
    worker_id = f"worker_SIMULATED_{os.getpid()}"
    print(f"Simulating worker {worker_id} for 10 seconds...")
    
    # Manually insert active worker
    with db._connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            conn.execute("""
                INSERT INTO workers (worker_id, pid, spawned_at, status)
                VALUES (?, ?, ?, 'BUSY')
            """, (worker_id, os.getpid(), now_iso()))
            conn.commit()
            print("Worker REGISTERED. Check TUI: W should be at least 1.")
        except Exception as e:
            print(f"Error registering: {e}")
            conn.rollback()
            return
            
    time.sleep(10)
    
    # Needs to be marked EXITED to clear W count
    with db._connect() as conn:
        try:
            conn.execute("""
                UPDATE workers 
                SET status = 'EXITED', exited_at = ?
                WHERE worker_id = ?
            """, (now_iso(), worker_id))
            print("Worker EXITED. TUI W should decrement.")
        except Exception as e:
            print(f"Error deregistering: {e}")

if __name__ == "__main__":
    main()
