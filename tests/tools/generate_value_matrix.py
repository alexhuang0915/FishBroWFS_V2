
import os
from pathlib import Path

def get_reachability_class(filepath):
    # This logic replicates the heuristics from generate_reachability_map.py
    # Ideally should read the generated file, but re-computing is safer context-wise.
    path = str(filepath)
    if "tests/contracts" in path: return "R1"
    if "tests/legacy" in path: return "R2"
    if "tests/gui_desktop" in path: return "R0"
    if "tests/product" in path: return "R0"
    if "tests/boundary" in path: return "R1"
    if "tests/tools" in path: return "R3"
    if "tests/gui_services" in path: return "R0"
    return "R3"

def classify_value(filepath, r_class):
    # Returns (Action, Value, Cost, Risk)
    
    if r_class == "R0":
        return "KEEP (Core)", "High", "Medium", "Low"
    
    if r_class == "R1":
        return "KEEP (Contract)", "High", "Low", "Low"
    
    if r_class == "R2":
        # Legacy is low value, medium cost (confusion)
        return "CANDIDATE FOR MERGE", "Low", "Medium", "Low"
    
    if r_class == "R3":
        # Tools or unknown
        return "CANDIDATE FOR REMOVAL", "Low", "Low", "Low"
        
    return "QUARANTINE", "Unknown", "Unknown", "Unknown"

def main():
    with open("outputs/_dp_evidence/full_test_files.txt", "r") as f:
        files = [line.strip() for line in f if line.strip()]

    out_path = Path("docs/tests/TEST_VALUE_MATRIX_V1.txt")
    
    with out_path.open("w") as f:
        f.write(f"{'File':<80} | {'Action':<25} | {'Val':<5} | {'Cost':<5} | {'Risk'}\n")
        f.write("-" * 130 + "\n")
        
        counts = {}
        
        for fp in files:
            r_class = get_reachability_class(fp)
            action, val, cost, risk = classify_value(fp, r_class)
            
            counts[action] = counts.get(action, 0) + 1
            f.write(f"{fp:<80} | {action:<25} | {val:<5} | {cost:<5} | {risk}\n")

        f.write("-" * 130 + "\n")
        f.write("Summary:\n")
        for k, v in counts.items():
            f.write(f"{k}: {v}\n")

if __name__ == "__main__":
    main()
