"""
Duplicate Model Ban Test for Gate Summary Protocol Hardening v1.3.1.

This test ensures that GateItemV1 and GateSummaryV1 models are defined only
in the SSOT location (src/contracts/portfolio/gate_summary_schemas.py) and
any explicitly whitelisted locations.

The test scans the entire codebase for class definitions matching these names
and fails if any are found outside the whitelist.
"""

import ast
import os
import sys
from pathlib import Path
from typing import List, Dict, Tuple

import pytest


# Whitelist of allowed locations for GateItemV1/GateSummaryV1 definitions
# Format: (file_path, class_name, reason)
WHITELIST = [
    # SSOT location - the single source of truth for gate summary protocol
    ("src/contracts/portfolio/gate_summary_schemas.py", "GateItemV1", "SSOT"),
    ("src/contracts/portfolio/gate_summary_schemas.py", "GateSummaryV1", "SSOT"),
    ("src/contracts/portfolio/gate_summary_schemas.py", "GateStatus", "SSOT (gate summary protocol)"),
    ("src/contracts/portfolio/gate_summary_schemas.py", "GateReasonCode", "SSOT"),
    
    # Other GateStatus definitions for different domains (not duplicates, different purposes)
    ("src/gui/services/gate_summary_service.py", "GateStatus", "UI gate results enum"),
    ("src/core/portfolio/evidence_aggregator.py", "GateStatus", "Evidence aggregator gate status"),
    ("src/gui/services/dataset_resolver.py", "GateStatus", "UI gate evaluation dataclass (different domain)"),
    
    # Legacy/renamed definitions that have been fixed
    # src/core/portfolio/evidence_aggregator.py had GateSummaryV1 renamed to GatekeeperMetricsV1
    # This is allowed as it's a different class name
]


def find_class_definitions(root_dir: Path, class_names: List[str]) -> List[Tuple[str, str, int]]:
    """
    Find all class definitions matching the given class names.
    
    Returns:
        List of tuples (file_path, class_name, line_number)
    """
    results = []
    
    for py_file in root_dir.rglob("*.py"):
        # Skip virtual environments and test output directories
        if any(part.startswith(".") or part == "__pycache__" for part in py_file.parts):
            continue
            
        try:
            content = py_file.read_text(encoding="utf-8")
            tree = ast.parse(content, filename=str(py_file))
            
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    if node.name in class_names:
                        # Get line number (1-indexed)
                        line_no = node.lineno
                        # Convert to relative path from root_dir
                        rel_path = str(py_file.relative_to(root_dir))
                        results.append((rel_path, node.name, line_no))
        except (SyntaxError, UnicodeDecodeError):
            # Skip files with syntax errors or encoding issues
            continue
    
    return results


def is_whitelisted(file_path: str, class_name: str) -> bool:
    """Check if a class definition is whitelisted."""
    for whitelist_path, whitelist_class, _ in WHITELIST:
        if file_path == whitelist_path and class_name == whitelist_class:
            return True
    return False


def test_no_duplicate_gate_summary_models() -> None:
    """
    Test that GateItemV1 and GateSummaryV1 are defined only in whitelisted locations.
    
    This is a critical guard against duplicate model definitions that could
    cause serialization/deserialization mismatches and protocol drift.
    """
    root_dir = Path(__file__).parent.parent.parent.parent
    target_classes = ["GateItemV1", "GateSummaryV1", "GateStatus", "GateReasonCode"]
    
    all_definitions = find_class_definitions(root_dir, target_classes)
    
    # Group by class name
    violations = []
    for file_path, class_name, line_no in all_definitions:
        if not is_whitelisted(file_path, class_name):
            violations.append((file_path, class_name, line_no))
    
    if not violations:
        return  # Success
    
    # Format violation message
    violation_lines = []
    for file_path, class_name, line_no in violations:
        violation_lines.append(f"  - {file_path}:{line_no} defines {class_name}")
    
    # Also show whitelisted definitions for context
    whitelisted_defs = []
    for file_path, class_name, line_no in all_definitions:
        if is_whitelisted(file_path, class_name):
            whitelisted_defs.append(f"  - {file_path}:{line_no} defines {class_name} (whitelisted)")
    
    error_msg = (
        f"Found {len(violations)} duplicate gate summary model definitions outside whitelist:\n"
        + "\n".join(violation_lines)
        + "\n\n"
        + "Whitelisted definitions:\n"
        + ("\n".join(whitelisted_defs) if whitelisted_defs else "  (none)")
        + "\n\n"
        + "ACTION REQUIRED:\n"
        + "1. If this is a legitimate duplicate (e.g., test fixture), add it to the WHITELIST in this test.\n"
        + "2. If this is an accidental duplicate, remove it and import from SSOT instead.\n"
        + "3. If this is a renamed class (like GatekeeperMetricsV1), ensure it doesn't conflict.\n"
        + "\n"
        + "SSOT location: src/contracts/portfolio/gate_summary_schemas.py"
    )
    
    pytest.fail(error_msg)


def test_whitelist_integrity() -> None:
    """
    Test that whitelisted definitions actually exist.
    
    This ensures the whitelist doesn't contain stale entries.
    """
    root_dir = Path(__file__).parent.parent.parent.parent
    
    for whitelist_path, whitelist_class, reason in WHITELIST:
        full_path = root_dir / whitelist_path
        if not full_path.exists():
            pytest.fail(
                f"Whitelist references non-existent file: {whitelist_path}\n"
                f"Class: {whitelist_class}, Reason: {reason}\n"
                "Update or remove this whitelist entry."
            )
        
        # Check that the class is actually defined in the file
        try:
            content = full_path.read_text(encoding="utf-8")
            tree = ast.parse(content, filename=str(full_path))
            
            class_found = False
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef) and node.name == whitelist_class:
                    class_found = True
                    break
            
            if not class_found:
                pytest.fail(
                    f"Whitelist references class {whitelist_class} not found in {whitelist_path}\n"
                    f"Reason: {reason}\n"
                    "Update or remove this whitelist entry."
                )
        except (SyntaxError, UnicodeDecodeError):
            pytest.fail(
                f"Failed to parse whitelisted file: {whitelist_path}\n"
                "Check file syntax and encoding."
            )


def test_ssot_models_have_frozen_config() -> None:
    """
    Test that SSOT models have frozen=True configuration.
    
    This ensures the SSOT models are immutable, preventing accidental mutations
    that could cause protocol violations.
    """
    ssot_path = Path(__file__).parent.parent.parent.parent / "src" / "contracts" / "portfolio" / "gate_summary_schemas.py"
    
    if not ssot_path.exists():
        pytest.fail(f"SSOT file not found: {ssot_path}")
    
    content = ssot_path.read_text(encoding="utf-8")
    
    # Check for frozen=True in ConfigDict
    if "ConfigDict(frozen=True" not in content and "frozen=True" not in content:
        pytest.fail(
            f"SSOT models in {ssot_path} must have frozen=True configuration.\n"
            "Add `model_config = ConfigDict(frozen=True, extra='forbid')` to GateItemV1 and GateSummaryV1."
        )
    
    # Check for extra='forbid' to prevent silent field additions
    if "extra='forbid'" not in content and 'extra="forbid"' not in content:
        pytest.warn(
            f"SSOT models in {ssot_path} should have extra='forbid' to prevent silent field additions.\n"
            "Consider adding `extra='forbid'` to ConfigDict."
        )


def test_gate_status_enum_documentation() -> None:
    """
    Test that GateStatus enum definitions are documented in whitelist.
    
    This ensures we're aware of all GateStatus enum definitions in the codebase
    and have explicitly decided whether they're allowed.
    """
    root_dir = Path(__file__).parent.parent.parent.parent
    
    # Find all GateStatus enum definitions
    gate_status_defs = find_class_definitions(root_dir, ["GateStatus"])
    
    # Check that all definitions are whitelisted
    violations = []
    for file_path, class_name, line_no in gate_status_defs:
        if not is_whitelisted(file_path, class_name):
            violations.append((file_path, line_no))
    
    if violations:
        violation_lines = "\n".join([f"  - {path}:{line}" for path, line in violations])
        pytest.fail(
            f"Found {len(violations)} GateStatus enum definitions not in whitelist:\n"
            + violation_lines
            + "\n\n"
            + "ACTION REQUIRED:\n"
            + "1. If this is a legitimate GateStatus enum for a different domain, add it to WHITELIST.\n"
            + "2. If this is a duplicate that should use SSOT, remove it and import from SSOT.\n"
            + "3. Consider renaming to avoid confusion (e.g., UIGateStatus, EvidenceGateStatus).\n"
            + "\n"
            + "Current whitelisted GateStatus definitions:\n"
            + "\n".join([f"  - {path}: {reason}" for path, cls, reason in WHITELIST if cls == "GateStatus"])
        )
    
    # Log warning about potential confusion if there are multiple definitions
    if len(gate_status_defs) > 1:
        definitions_info = "\n".join([
            f"  - {path}:{line} ({'whitelisted' if is_whitelisted(path, 'GateStatus') else 'NOT whitelisted'})"
            for path, _, line in gate_status_defs
        ])
        # Use print for now since pytest.warn doesn't exist
        print(
            f"WARNING: Multiple GateStatus definitions found ({len(gate_status_defs)} total):\n"
            + definitions_info
            + "\n\n"
            + "Consider whether these should be consolidated or renamed to avoid confusion."
        )


if __name__ == "__main__":
    # Run a quick scan when executed directly
    root_dir = Path(__file__).parent.parent.parent.parent
    target_classes = ["GateItemV1", "GateSummaryV1", "GateStatus", "GateReasonCode"]
    
    print("Scanning for gate summary model definitions...")
    all_defs = find_class_definitions(root_dir, target_classes)
    
    print(f"\nFound {len(all_defs)} definitions:")
    for file_path, class_name, line_no in all_defs:
        whitelisted = "✓" if is_whitelisted(file_path, class_name) else "✗"
        print(f"  [{whitelisted}] {file_path}:{line_no} - {class_name}")
    
    violations = [(f, c, l) for f, c, l in all_defs if not is_whitelisted(f, c)]
    if violations:
        print(f"\n❌ Found {len(violations)} violations outside whitelist!")
        sys.exit(1)
    else:
        print("\n✅ All definitions are whitelisted.")
        sys.exit(0)