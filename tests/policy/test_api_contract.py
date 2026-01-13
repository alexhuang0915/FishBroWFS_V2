"""
API Contract Policy Test.

This test ensures that the live OpenAPI spec matches the saved snapshot.
If they differ, the test fails with a message instructing the user to run
`make api-snapshot` to update the snapshot.

The snapshot is stored at tests/policy/api_contract/openapi.json.
"""

import json
import os
import sys
from pathlib import Path

import pytest


def test_api_contract_matches_snapshot() -> None:
    """
    Compare live OpenAPI spec with saved snapshot.

    If they differ, fail with a clear message.
    """
    # Import the FastAPI app (must be done after sys.path is set)
    from control.api import app

    # Load saved snapshot
    snapshot_path = Path(__file__).parent / "api_contract" / "openapi.json"
    if not snapshot_path.exists():
        pytest.fail(
            f"API contract snapshot not found at {snapshot_path}\n"
            "Please run `make api-snapshot` to generate it."
        )

    with open(snapshot_path, "r", encoding="utf-8") as f:
        snapshot = json.load(f)

    # Generate current spec
    current = app.openapi()

    # Compare (deep equality)
    if current == snapshot:
        return  # success

    # Determine diff (simplistic)
    import difflib
    snapshot_str = json.dumps(snapshot, indent=2, sort_keys=True)
    current_str = json.dumps(current, indent=2, sort_keys=True)
    diff = list(difflib.unified_diff(
        snapshot_str.splitlines(keepends=True),
        current_str.splitlines(keepends=True),
        fromfile="snapshot",
        tofile="current",
    ))

    diff_msg = "".join(diff[:50])  # limit output length
    if len(diff) > 50:
        diff_msg += f"\n... and {len(diff) - 50} more lines."

    pytest.fail(
        f"API contract mismatch.\n"
        f"Snapshot: {snapshot_path}\n"
        f"Live API spec differs from saved snapshot.\n"
        f"To update the snapshot, run:\n"
        f"    make api-snapshot\n\n"
        f"Diff (first 50 lines):\n{diff_msg}"
    )


def test_api_snapshot_is_not_auto_written() -> None:
    """
    Ensure the test does NOT write the snapshot automatically.

    This is a sanity check that the test does not have side effects.
    """
    snapshot_path = Path(__file__).parent / "api_contract" / "openapi.json"
    original_mtime = snapshot_path.stat().st_mtime if snapshot_path.exists() else None

    # Run the comparison (should not write)
    # We'll just import and call app.openapi() but not write.
    from control.api import app
    _ = app.openapi()

    if snapshot_path.exists():
        new_mtime = snapshot_path.stat().st_mtime
        if new_mtime != original_mtime:
            pytest.fail(
                "API contract test modified the snapshot file! "
                "This is forbidden; the snapshot must be updated manually via `make api-snapshot`."
            )