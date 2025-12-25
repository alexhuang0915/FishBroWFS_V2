#!/usr/bin/env python3
"""
Phase A Audit Helper for No-Fog 2.0 Deep Clean - Evidence Inventory.

This script runs evidence collection commands and generates structured data
for the Phase A report. It is READ-ONLY - does not delete, move, rename, or
refactor any files.

Usage:
    python3 scripts/no_fog/phase_a_audit.py [--output-json OUTPUT_JSON]

Outputs:
    - Prints evidence summary to stdout
    - Optionally writes JSON with collected evidence
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, asdict


@dataclass
class EvidenceItem:
    """Single piece of evidence collected."""
    command: str
    exit_code: int
    matches: List[str]
    match_count: int


@dataclass
class PhaseAAudit:
    """Container for all Phase A evidence."""
    candidate_cleanup_items: EvidenceItem
    runner_schism: EvidenceItem
    ui_bypass_scan: EvidenceItem
    test_inventory: EvidenceItem
    tooling_rules_drift: EvidenceItem
    imports_audit: EvidenceItem


def run_rg(pattern: str, path: str = ".", extra_args: Optional[List[str]] = None) -> EvidenceItem:
    """Run ripgrep and collect results."""
    cmd = ["rg", "-n", pattern, path]
    if extra_args:
        cmd.extend(extra_args)
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, cwd=Path.cwd())
        lines = result.stdout.strip().split("\n") if result.stdout.strip() else []
        return EvidenceItem(
            command=" ".join(cmd),
            exit_code=result.returncode,
            matches=lines,
            match_count=len(lines)
        )
    except FileNotFoundError:
        print(f"Warning: rg not found, skipping pattern '{pattern}'", file=sys.stderr)
        return EvidenceItem(
            command=" ".join(cmd),
            exit_code=127,
            matches=[],
            match_count=0
        )


def collect_evidence() -> PhaseAAudit:
    """Run all evidence collection commands."""
    print("=== Phase A Evidence Collection ===", file=sys.stderr)
    
    # 1. Candidate Cleanup Items (File/Folder Level)
    print("1. Searching for GM_Huang|launch_b5.sh|restore_from_release_txt_force...", file=sys.stderr)
    # Exclude snapshot directories from count as they contain historical references
    candidate_cleanup = run_rg("GM_Huang|launch_b5\.sh|restore_from_release_txt_force", ".", extra_args=["--glob", "!TEST_SNAPSHOT*", "--glob", "!SYSTEM_FULL_SNAPSHOT*"])
    
    # 2. Runner Schism (Single Truth Audit)
    print("2. Searching for runner patterns in src/FishBroWFS_V2...", file=sys.stderr)
    runner_schism = run_rg(
        "funnel_runner|wfs_runner|research_runner|run_funnel|run_wfs|run_research",
        "src/FishBroWFS_V2"
    )
    
    # 3. UI Bypass Scan (Direct Write / Direct Logic Calls)
    print("3. Searching for database operations in GUI...", file=sys.stderr)
    ui_bypass = run_rg(
        "commit\(|execute\(|insert\(|update\(|delete\(|\.write\(",
        "src/FishBroWFS_V2/gui"
    )
    
    # 4. ActionQueue/Intent patterns in GUI
    print("4. Searching for ActionQueue/Intent patterns in GUI...", file=sys.stderr)
    action_queue = run_rg(
        "ActionQueue|UserIntent|submit_intent|enqueue\(",
        "src/FishBroWFS_V2/gui"
    )
    
    # 5. Test Inventory & Obsolescence Candidates
    print("5. Searching for stage0 tests...", file=sys.stderr)
    test_inventory = run_rg("tests/test_stage0_|stage0_", "tests")
    
    # 6. Imports audit (FishBroWFS_V2 within GUI)
    print("6. Searching for FishBroWFS_V2 imports in GUI...", file=sys.stderr)
    imports_audit = run_rg("^from FishBroWFS_V2|^import FishBroWFS_V2", "src/FishBroWFS_V2/gui")
    
    # 7. Tooling Rules Drift (.continue/rules, Makefile, .github)
    print("7. Searching for tooling patterns...", file=sys.stderr)
    tooling_drift = run_rg("pytest|make check|no-fog|full-snapshot|snapshot", "Makefile", extra_args=[".github", "scripts"])
    
    # Combine ActionQueue results into UI bypass for reporting
    # (The UI bypass scan originally included both)
    ui_bypass.matches.extend(action_queue.matches)
    ui_bypass.match_count += action_queue.match_count
    
    return PhaseAAudit(
        candidate_cleanup_items=candidate_cleanup,
        runner_schism=runner_schism,
        ui_bypass_scan=ui_bypass,
        test_inventory=test_inventory,
        tooling_rules_drift=tooling_drift,
        imports_audit=imports_audit
    )


def print_summary(audit: PhaseAAudit) -> None:
    """Print human-readable summary of evidence."""
    print("\n" + "="*60)
    print("PHASE A EVIDENCE SUMMARY")
    print("="*60)
    
    print(f"\n1. Candidate Cleanup Items (File/Folder Level):")
    print(f"   Matches: {audit.candidate_cleanup_items.match_count}")
    if audit.candidate_cleanup_items.match_count > 0:
        print(f"   Sample matches (first 5):")
        for line in audit.candidate_cleanup_items.matches[:5]:
            print(f"     - {line}")
    
    print(f"\n2. Runner Schism (Single Truth Audit):")
    print(f"   Matches: {audit.runner_schism.match_count}")
    if audit.runner_schism.match_count > 0:
        print(f"   Found runner patterns in:")
        unique_files = set(line.split(":")[0] for line in audit.runner_schism.matches if ":" in line)
        for file in sorted(unique_files)[:10]:
            print(f"     - {file}")
    
    print(f"\n3. UI Bypass Scan (Direct Write / Direct Logic Calls):")
    print(f"   Matches: {audit.ui_bypass_scan.match_count}")
    if audit.ui_bypass_scan.match_count > 0:
        print(f"   Found in files:")
        unique_files = set(line.split(":")[0] for line in audit.ui_bypass_scan.matches if ":" in line)
        for file in sorted(unique_files):
            print(f"     - {file}")
    
    print(f"\n4. Test Inventory & Obsolescence Candidates:")
    print(f"   Matches: {audit.test_inventory.match_count}")
    if audit.test_inventory.match_count > 0:
        print(f"   Stage0-related tests found:")
        test_files = set(line.split(":")[0] for line in audit.test_inventory.matches if ":" in line)
        for file in sorted(test_files):
            print(f"     - {file}")
    
    print(f"\n5. Tooling Rules Drift (.continue/rules, Makefile, .github):")
    print(f"   Matches: {audit.tooling_rules_drift.match_count}")
    
    print(f"\n6. Imports Audit (FishBroWFS_V2 within GUI):")
    print(f"   Matches: {audit.imports_audit.match_count}")
    if audit.imports_audit.match_count > 0:
        print(f"   GUI files importing FishBroWFS_V2:")
        unique_files = set(line.split(":")[0] for line in audit.imports_audit.matches if ":" in line)
        for file in sorted(unique_files)[:15]:
            print(f"     - {file}")
    
    print("\n" + "="*60)
    print("ANALYSIS NOTES")
    print("="*60)
    
    # Generate analysis notes based on evidence
    notes = []
    
    if audit.candidate_cleanup_items.match_count > 100:
        notes.append("High number of GM_Huang/launch_b5.sh references - potential cleanup candidates")
    
    if audit.runner_schism.match_count > 0:
        notes.append(f"Multiple runner implementations found ({audit.runner_schism.match_count} matches) - check for single truth violations")
    
    if audit.ui_bypass_scan.match_count > 0:
        notes.append(f"UI bypass patterns detected ({audit.ui_bypass_scan.match_count} matches) - potential direct write/logic calls")
    
    if audit.test_inventory.match_count > 20:
        notes.append(f"Many stage0-related tests ({audit.test_inventory.match_count}) - consider test consolidation")
    
    if audit.imports_audit.match_count > 30:
        notes.append(f"High GUI import count ({audit.imports_audit.match_count}) - check for circular dependencies")
    
    if not notes:
        notes.append("No major issues detected in initial scan")
    
    for i, note in enumerate(notes, 1):
        print(f"{i}. {note}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase A Audit Helper for No-Fog 2.0 Deep Clean")
    parser.add_argument(
        "--output-json",
        help="Path to write JSON output with collected evidence",
        type=Path,
        default=None
    )
    args = parser.parse_args()
    
    audit = collect_evidence()
    print_summary(audit)
    
    if args.output_json:
        # Convert to serializable dict
        output_dict = {
            "phase_a_audit": {
                "candidate_cleanup_items": asdict(audit.candidate_cleanup_items),
                "runner_schism": asdict(audit.runner_schism),
                "ui_bypass_scan": asdict(audit.ui_bypass_scan),
                "test_inventory": asdict(audit.test_inventory),
                "tooling_rules_drift": asdict(audit.tooling_rules_drift),
                "imports_audit": asdict(audit.imports_audit),
            }
        }
        
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        with open(args.output_json, "w", encoding="utf-8") as f:
            json.dump(output_dict, f, indent=2, ensure_ascii=False)
        
        print(f"\nJSON output written to: {args.output_json}", file=sys.stderr)
    
    return 0


if __name__ == "__main__":
    sys.exit(main())