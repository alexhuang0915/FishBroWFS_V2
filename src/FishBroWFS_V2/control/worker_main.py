"""Worker main entry point (for subprocess execution)."""

from __future__ import annotations

import sys
from pathlib import Path

from FishBroWFS_V2.control.worker import worker_loop

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m FishBroWFS_V2.control.worker_main <db_path>")
        sys.exit(1)
    
    db_path = Path(sys.argv[1])
    worker_loop(db_path)

