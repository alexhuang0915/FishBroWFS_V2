
import os
import re
from pathlib import Path

def classify_test_topology(filepath, content):
    """
    Classify test into R0-R3 and extract metadata.
    """
    path = str(filepath)
    
    # 1. Classification (R0-R3)
    if "tests/contracts" in path:
        category = "R1 (Contract)"
        invariant = "Architecture/Policy Compliance"
        risk = "Governance Violation"
    elif "tests/legacy" in path:
        category = "R2 (Legacy)"
        invariant = "Historical Behavior"
        risk = "None (Shadowed)"
    elif "tests/tools" in path:
        category = "R3 (Tooling)"
        invariant = "Dev Utility"
        risk = "Broken Workflow"
    else: # Product/GUI
        category = "R0 (Runtime)"
        invariant = "Functional Correctness"
        risk = "Regression/Bug"

    # 2. Refine Breakdown
    if "gui_desktop" in path:
        invariant = "UI Component Behavior"
    if "portfolio" in path:
        invariant = "Portfolio Logic/Math"
    if "safety" in path:
        invariant = "Safety Gate Enforcement"

    # 3. Superseded Check
    superseded_by = "-"
    if "legacy" in path:
        superseded_by = "Corresponding Product Test"

    return category, invariant, risk, superseded_by

def main():
    root = Path("tests")
    out_path = Path("docs/maps/TEST_TOPOLOGY_MAP.txt")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    
    with out_path.open("w") as f:
        f.write(f"{'File':<90} | {'Class':<15} | {'Invariant Protected':<30} | {'Breakage Risk':<20} | {'Superseded By'}\n")
        f.write("-" * 180 + "\n")
        
        # Walk all test files
        for r, d, files in os.walk(root):
            for file in sorted(files):
                if not file.startswith("test_") or not file.endswith(".py"):
                    continue
                    
                full_path = Path(r) / file
                try:
                    content = full_path.read_text(encoding="utf-8")
                except:
                    content = ""
                
                cat, inv, risk, sup = classify_test_topology(full_path, content)
                
                f.write(f"{str(full_path):<90} | {cat:<15} | {inv:<30} | {risk:<20} | {sup}\n")

if __name__ == "__main__":
    main()
