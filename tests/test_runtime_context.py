#!/usr/bin/env python3
"""
Test runtime context generation.

Contract:
- Call write_runtime_context(out_path=tmp_path/...) with dummy entrypoint.
- Monkeypatch subprocess calls to raise; verify file still written with headings and UNKNOWN.
- Assert policy hash section present (UNKNOWN allowed).
"""

import tempfile
import json
import subprocess
import hashlib
import os
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest

from FishBroWFS_V2.gui.services.runtime_context import (
    write_runtime_context,
    get_snapshot_timestamp,
    get_git_info,
    get_policy_hash,
)


def test_write_runtime_context_basic(tmp_path: Path):
    """Basic test that writes a runtime context file."""
    out_path = tmp_path / "RUNTIME_CONTEXT.md"
    
    result = write_runtime_context(
        out_path=out_path,
        entrypoint="test_entrypoint.py",
        listen_host="127.0.0.1",
        listen_port=9999,
    )
    
    assert result == out_path
    assert out_path.exists()
    
    content = out_path.read_text(encoding="utf-8")
    
    # Required headings
    assert "# Runtime Context" in content
    assert "## Timestamp" in content
    assert "## Process" in content
    assert "## Build" in content
    assert "## Entrypoint" in content
    assert "## Network" in content
    assert "## Governance" in content
    assert "## Snapshot Policy Binding" in content
    assert "## Notes" in content
    
    # Specific content
    assert "test_entrypoint.py" in content
    assert "127.0.0.1:9999" in content or ":9999" in content
    
    # Should have PID
    import os
    assert f"PID: {os.getpid()}" in content


def test_write_runtime_context_no_crash_on_error(tmp_path: Path):
    """Test that write_runtime_context never crashes."""
    out_path = tmp_path / "RUNTIME_CONTEXT.md"
    
    # Monkeypatch subprocess.check_output to raise
    with patch('subprocess.check_output', side_effect=Exception("Mock error")):
        # Also patch psutil.Process to raise if psutil is available
        # First check if psutil module is imported in the runtime_context module
        import sys
        if 'psutil' in sys.modules:
            with patch('psutil.Process', side_effect=Exception("Psutil error")):
                result = write_runtime_context(
                    out_path=out_path,
                    entrypoint="test.py",
                )
        else:
            # psutil not available, just test without patching it
            result = write_runtime_context(
                out_path=out_path,
                entrypoint="test.py",
            )
    
    assert result == out_path
    assert out_path.exists()
    
    content = out_path.read_text(encoding="utf-8")
    # Should still have basic structure
    assert "# Runtime Context" in content
    assert "## Timestamp" in content
    # Might have error section or minimal info
    assert "PID:" in content or "Error" in content


def test_policy_hash_section(tmp_path: Path):
    """Test that policy hash section is present."""
    out_path = tmp_path / "RUNTIME_CONTEXT.md"
    
    # Create a dummy LOCAL_SCAN_RULES.json
    policy_dir = tmp_path / "outputs" / "snapshots" / "full"
    policy_dir.mkdir(parents=True)
    policy_content = json.dumps({"mode": "test", "allowed_roots": ["src"]})
    (policy_dir / "LOCAL_SCAN_RULES.json").write_text(policy_content)
    
    # Mock the policy path to point to our dummy
    with patch('FishBroWFS_V2.gui.services.runtime_context.Path') as MockPath:
        mock_path_instance = MagicMock()
        mock_path_instance.exists.return_value = True
        mock_path_instance.__str__.return_value = str(policy_dir / "LOCAL_SCAN_RULES.json")
        
        def side_effect(*args, **kwargs):
            if args[0] == "outputs/snapshots/full/LOCAL_SCAN_RULES.json":
                return mock_path_instance
            return Path(*args, **kwargs)
        
        MockPath.side_effect = side_effect
        
        result = write_runtime_context(
            out_path=out_path,
            entrypoint="test.py",
        )
    
    assert out_path.exists()
    content = out_path.read_text(encoding="utf-8")
    
    # Should have policy hash section
    assert "## Snapshot Policy Binding" in content
    assert "Local scan rules sha256:" in content
    # Hash could be UNKNOWN or actual hash
    assert "Local scan rules source:" in content


def test_get_snapshot_timestamp(tmp_path: Path):
    """Test snapshot timestamp retrieval."""
    # Test with MANIFEST.json
    manifest_dir = tmp_path / "outputs" / "snapshots" / "full"
    manifest_dir.mkdir(parents=True)
    manifest_path = manifest_dir / "MANIFEST.json"
    
    expected_time = "2025-12-26T12:00:00Z"
    manifest_path.write_text(json.dumps({"generated_at_utc": expected_time}))
    
    with patch('FishBroWFS_V2.gui.services.runtime_context.Path') as MockPath:
        def side_effect(*args, **kwargs):
            if args[0] == "outputs/snapshots/full/MANIFEST.json":
                return manifest_path
            return Path(*args, **kwargs)
        
        MockPath.side_effect = side_effect
        
        timestamp = get_snapshot_timestamp()
        assert timestamp == expected_time
    
    # Test with SYSTEM_FULL_SNAPSHOT.md mtime
    import time
    snapshot_path = tmp_path / "SYSTEM_FULL_SNAPSHOT.md"
    snapshot_path.write_text("# Snapshot")
    expected_mtime = time.time() - 3600
    os.utime(snapshot_path, (expected_mtime, expected_mtime))
    
    with patch('FishBroWFS_V2.gui.services.runtime_context.Path') as MockPath:
        def side_effect(*args, **kwargs):
            if args[0] == "outputs/snapshots/full/MANIFEST.json":
                return Path("/nonexistent")
            if args[0] == "outputs/snapshots/SYSTEM_FULL_SNAPSHOT.md":
                return snapshot_path
            return Path(*args, **kwargs)
        
        MockPath.side_effect = side_effect
        
        timestamp = get_snapshot_timestamp()
        # Should be ISO format
        assert "T" in timestamp
        assert "Z" in timestamp or "+" in timestamp
    
    # Test UNKNOWN when neither exists
    with patch('FishBroWFS_V2.gui.services.runtime_context.Path') as MockPath:
        MockPath.return_value.exists.return_value = False
        
        timestamp = get_snapshot_timestamp()
        assert timestamp == "UNKNOWN"


def test_get_git_info():
    """Test git info retrieval."""
    with patch('subprocess.check_output') as mock_check_output:
        # Mock successful git commands
        mock_check_output.return_value = b"abc123\n"
        
        commit, dirty = get_git_info()
        assert commit == "abc123"
        # dirty could be "yes" or "no" depending on mock
        
        # Test git error
        mock_check_output.side_effect = Exception("git not found")
        commit, dirty = get_git_info()
        assert commit == "UNKNOWN"
        assert dirty == "UNKNOWN"


# def test_port_occupancy():
#     """Test port occupancy checking."""
#     with patch('FishBroWFS_V2.gui.services.runtime_context._run') as mock_run:
#         mock_run.return_value = "LISTEN 0 128 0.0.0.0:8080 0.0.0.0:* users:(python)"
#
#         result = port_occupancy(8080)
#         assert "8080" in result or "python" in result
#
#         # Test error case
#         mock_run.return_value = "ERROR: something"
#         result = port_occupancy(8080)
#         assert "ERROR" in result


def test_get_policy_hash(tmp_path: Path):
    """Test policy hash computation."""
    policy_path = tmp_path / "policy.json"
    content = b'{"test": "data"}'
    policy_path.write_bytes(content)
    
    expected_hash = hashlib.sha256(content).hexdigest()
    
    hash_val = get_policy_hash(policy_path)
    assert hash_val == expected_hash
    
    # Test missing file
    missing_path = tmp_path / "missing.json"
    hash_val = get_policy_hash(missing_path)
    assert hash_val == "UNKNOWN"
    
    # Test read error
    with patch('builtins.open', side_effect=Exception("I/O error")):
        hash_val = get_policy_hash(policy_path)
        assert hash_val == "UNKNOWN"


def test_runtime_context_integration(tmp_path: Path):
    """Integration test with real file system."""
    # Create a minimal repo-like structure
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    
    # Create outputs/snapshots/full/LOCAL_SCAN_RULES.json
    policy_dir = repo_root / "outputs" / "snapshots" / "full"
    policy_dir.mkdir(parents=True)
    policy_content = json.dumps({
        "mode": "local-strict",
        "allowed_roots": ["src", "tests"],
        "max_files": 20000,
    })
    (policy_dir / "LOCAL_SCAN_RULES.json").write_text(policy_content)
    
    # Create MANIFEST.json
    (policy_dir / "MANIFEST.json").write_text(json.dumps({
        "generated_at_utc": "2025-12-26T12:00:00Z",
        "git_head": "test123",
    }))
    
    # Change to repo directory
    import os
    old_cwd = os.getcwd()
    os.chdir(repo_root)
    
    try:
        out_path = repo_root / "runtime_test.md"
        
        result = write_runtime_context(
            out_path=out_path,
            entrypoint="scripts/launch_dashboard.py",
            listen_port=8080,
        )
        
        assert result.exists()
        content = result.read_text(encoding="utf-8")
        
        # Check key sections
        assert "## Snapshot Policy Binding" in content
        assert "Local scan rules sha256:" in content
        assert "scripts/launch_dashboard.py" in content
        
    finally:
        os.chdir(old_cwd)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])