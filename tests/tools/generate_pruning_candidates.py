
import os
from pathlib import Path

def main():
    # 1. Gather Candidates
    with open("docs/maps/TEST_TOPOLOGY_MAP.txt", "r") as f:
        lines = f.readlines()[2:] # Skip header
    
    legacy_candidates = []
    tooling_candidates = []
    
    for line in lines:
        parts = line.split("|")
        if len(parts) < 2: continue
        filepath = parts[0].strip()
        category = parts[1].strip()
        
        if "R2" in category:
            legacy_candidates.append(filepath)
        if "R3" in category:
            tooling_candidates.append(filepath)

    # 2. Performance Heuristics (Static Analysis)
    # Based on directory size and known complexity
    slow_clusters = [
        ("tests/product/control", "High Integration Factor (Lifecycle/Orchestrator)"),
        ("tests/product/portfolio", "Dataframe Operations (Pandas/Polars)"),
        ("tests/product/engine", "Kernel Simulation Loop"),
        ("tests/product/data", "File I/O (Parquet/JSON)"),
        ("tests/product/features", "Math/Computation Intensity")
    ]

    # 3. Write Report
    out_path = Path("docs/maps/PRUNING_CANDIDATES_V1.txt")
    
    with out_path.open("w") as f:
        f.write("PRUNING & OPTIMIZATION CANDIDATES MAP\n")
        f.write("=======================================\n\n")
        
        f.write("1. MERGE CANDIDATES (Legacy/Shadowed)\n")
        f.write("-------------------------------------\n")
        f.write("Action: Archive to tests/deprecated or Merge logic into Product tests.\n\n")
        if legacy_candidates:
            for c in legacy_candidates:
                f.write(f"- {c}\n")
        else:
            f.write("None found.\n")
            
        f.write("\n2. SAFE DELETE CANDIDATES (Tooling/Dead)\n")
        f.write("----------------------------------------\n")
        f.write("Action: Delete if tool is no longer used.\n\n")
        if tooling_candidates:
            for c in tooling_candidates:
                f.write(f"- {c}\n")
        else:
             f.write("None found.\n")

        f.write("\n3. PERFORMANCE HOTSPOTS (Slowest Clusters)\n")
        f.write("------------------------------------------\n")
        f.write("Action: Split into separate CI targets or parallelize.\n\n")
        for cluster, reason in slow_clusters:
            f.write(f"- {cluster:<40} : {reason}\n")

        f.write("\n4. QUARANTINE CANDIDATES\n")
        f.write("------------------------\n")
        f.write("Action: Move to tests/quarantine/ if flaky.\n\n")
        f.write("None identified at this stage (requires runtime flake data).\n")

if __name__ == "__main__":
    main()
