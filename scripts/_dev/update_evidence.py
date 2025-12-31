#!/usr/bin/env python3
"""
Update S1_REVERIFY.txt with missing research run section.
"""
from pathlib import Path

def extract_section(content, start_marker, end_marker):
    """Extract text between markers (excluding markers)."""
    try:
        start = content.index(start_marker) + len(start_marker)
        end = content.index(end_marker, start)
        return content[start:end].strip()
    except ValueError:
        return None

def main():
    evidence_dir = Path("outputs/_dp_evidence/20251230_201916")
    full_file = evidence_dir / "S1_REVERIFY_FULL.txt"
    evidence_file = evidence_dir / "S1_REVERIFY.txt"
    
    with open(full_file, 'r') as f:
        full_content = f.read()
    
    # Extract research run section
    research_section = extract_section(
        full_content,
        "=== Minimal Research Run with allow_build=False ===",
        "=== SUMMARY ==="
    )
    
    if research_section is None:
        print("Could not extract research run section")
        return
    
    # Read current evidence
    with open(evidence_file, 'r') as f:
        lines = f.readlines()
    
    # Find line with "--- 3. Minimal Research Run with allow_build=False ---"
    new_lines = []
    for line in lines:
        if line.strip() == "--- 3. Minimal Research Run with allow_build=False ---":
            new_lines.append(line)
            new_lines.append(research_section + "\n")
            # Skip the "Section not found" line
            next_line = lines[lines.index(line) + 1]
            if next_line.strip() == "Section not found":
                # Skip adding that line
                continue
        else:
            new_lines.append(line)
    
    # Write back
    with open(evidence_file, 'w') as f:
        f.writelines(new_lines)
    
    print(f"Updated {evidence_file} with research run section")

if __name__ == "__main__":
    main()