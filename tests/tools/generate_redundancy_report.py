
import os
from pathlib import Path
from collections import defaultdict
import difflib

def main():
    with open("outputs/_dp_evidence/full_test_files.txt", "r") as f:
        files = [line.strip() for line in f if line.strip()]

    # Group by basename
    by_basename = defaultdict(list)
    for fp in files:
        name = Path(fp).name
        by_basename[name].append(fp)

    # Find collisions
    collisions = {k: v for k, v in by_basename.items() if len(v) > 1}

    # Find fuzzy matches (Legacy vs Product)
    legacy_files = [f for f in files if "tests/legacy" in f]
    product_files = [f for f in files if "tests/product" in f]
    
    overlaps = []
    for lf in legacy_files:
        l_name = Path(lf).name.replace("test_", "").replace(".py", "")
        # Fuzzy match against product files
        for pf in product_files:
            p_name = Path(pf).name.replace("test_", "").replace(".py", "")
            
            # Check for high similarity
            ratio = difflib.SequenceMatcher(None, l_name, p_name).ratio()
            if ratio > 0.8 or l_name in p_name or p_name in l_name:
                overlaps.append((lf, pf, ratio))

    # Write Report
    out_path = Path("docs/tests/TEST_REDUNDANCY_REPORT_V1.txt")
    with out_path.open("w") as f:
        f.write("TEST REDUNDANCY & SHADOWING REPORT\n")
        f.write("==================================\n\n")

        f.write("1. Exact Basename Collisions (Potential Shadowing)\n")
        f.write("--------------------------------------------------\n")
        if not collisions:
            f.write("None.\n")
        else:
            for name, paths in collisions.items():
                f.write(f"- {name}:\n")
                for p in paths:
                    f.write(f"  * {p}\n")
        
        f.write("\n2. Legacy vs Product Overlap (Potential Redundancy)\n")
        f.write("---------------------------------------------------\n")
        if not overlaps:
             f.write("None.\n")
        else:
            sorted_overlaps = sorted(overlaps, key=lambda x: x[2], reverse=True)
            for lf, pf, ratio in sorted_overlaps:
                f.write(f"- Legacy:  {lf}\n")
                f.write(f"  Product: {pf}\n")
                f.write(f"  Similarity: {ratio:.2f}\n\n")

        f.write("\n3. Contract vs Product Overlap (Coverage Duplication)\n")
        f.write("-----------------------------------------------------\n")
        # Contracts often test "governance" or "policy". Product tests "behavior".
        # Check for files with similar names in contracts and product.
        contract_files = [f for f in files if "tests/contracts" in f]
        cp_overlaps = []
        for cf in contract_files:
             c_name = Path(cf).name.replace("test_", "").replace(".py", "")
             for pf in product_files:
                 p_name = Path(pf).name.replace("test_", "").replace(".py", "")
                 if c_name == p_name: # Strict match for now
                     cp_overlaps.append((cf, pf))
        
        if not cp_overlaps:
            f.write("None.\n")
        else:
             for cf, pf in cp_overlaps:
                 f.write(f"- Contract: {cf}\n")
                 f.write(f"  Product:  {pf}\n\n")

if __name__ == "__main__":
    main()
