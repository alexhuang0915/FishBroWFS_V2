"""
Pytest configuration and fixtures.

Ensures PYTHONPATH is set correctly for imports.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Add src/ to Python path if not already present
# This ensures tests can import FishBroWFS_V2 without manual PYTHONPATH setup
repo_root = Path(__file__).parent.parent
src_path = repo_root / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))
