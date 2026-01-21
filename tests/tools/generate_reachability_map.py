
import os
import re
from pathlib import Path

def classify_test(filepath):
    # R0: Guards active runtime path
    # R1: Guards config / contract / policy
    # R2: Guards deprecated or shadowed code
    # R3: No clear reachable path (suspect dead test)

    path = str(filepath)
    
    # 1. Broad Category Heuristics
    if "tests/contracts" in path:
        return "R1", "Contract/Policy Compliance"
    
    if "tests/legacy" in path:
        return "R2", "Legacy Codebase"

    if "tests/gui_desktop" in path:
        return "R0", "Active Desktop UI"
    
    if "tests/product" in path:
        # Check if it's "control" or "core" -> usually R0
        if "control" in path or "core" in path or "engine" in path:
            return "R0", "Core Product Logic"
        if "strategy" in path:
            return "R0", "Strategy Logic"
        # Others in product are likely R0 but verify
        return "R0", "Product Logic"

    if "tests/boundary" in path:
        return "R1", "Boundary Contract"

    if "tests/tools" in path:
        return "R3", "Internal Tooling Test"
    
    if "tests/gui_services" in path:
        return "R0", "GUI Services"

    return "R3", "Unclassified/Other"

def main():
    with open("outputs/_dp_evidence/full_test_files.txt", "r") as f:
        files = [line.strip() for line in f if line.strip()]

    # Write output
    out_path = Path("docs/tests/TEST_RUNTIME_REACHABILITY_MAP_V1.txt")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    
    with out_path.open("w") as f:
        f.write(f"{'File':<80} | {'Class':<4} | {'Reason'}\n")
        f.write("-" * 120 + "\n")
        
        counts = {"R0": 0, "R1": 0, "R2": 0, "R3": 0}

        for fp in files:
            cls, reason = classify_test(fp)
            counts[cls] += 1
            f.write(f"{fp:<80} | {cls:<4} | {reason}\n")
        
        f.write("-" * 120 + "\n")
        f.write("Summary:\n")
        for k, v in counts.items():
            f.write(f"{k}: {v}\n")

if __name__ == "__main__":
    main()
