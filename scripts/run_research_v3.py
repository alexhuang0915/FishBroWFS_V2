#!/usr/bin/env python3
"""
Research v3 – Execution Script.

Calls generate_research.py with default parameters.
This is a placeholder; adapt to actual research script.
"""

import sys
from pathlib import Path

# Ensure the package root is in sys.path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from scripts.generate_research import main as research_main


def main() -> None:
    # Call the research script with default arguments
    # You may need to adjust based on actual script signature.
    research_main()


if __name__ == "__main__":
    main()