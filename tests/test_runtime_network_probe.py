#!/usr/bin/env python3
"""
Test runtime network probe hardening.

Validates dual-probe strategy for port occupancy detection in runtime context.
"""

import pytest

from src.gui.services.runtime_context import (
    _probe_ss,
    _probe_lsof,
    _analyze_port_occupancy,
)


def test_probe_ss_mocked_empty(monkeypatch):
    """Test when ss returns empty (simulating WSL permission issue)."""
    
    def mock_run(cmd):
        return ""  # Empty output
    
    monkeypatch.setattr(
        "src.gui.services.runtime_context._run",
        mock_run
    )
    
    result = _probe_ss(8080)
    assert "NOT AVAILABLE" in result
    assert "ss command failed" in result or "empty" in result


def test_probe_lsof_mocked_pid(monkeypatch):
    """Test when lsof returns a PID."""
    
    def mock_run(cmd):
        # cmd is a list like ["bash", "-lc", "lsof -i :8080 -sTCP:LISTEN -n -P"]
        # Check if any part of the command contains "lsof"
        cmd_str = " ".join(cmd)
        if "lsof" in cmd_str:
            return "python3 12345 user 3u IPv4 12345 0t0 TCP *:8080 (LISTEN)"
        return ""
    
    monkeypatch.setattr(
        "src.gui.services.runtime_context._run",
        mock_run
    )
    
    result = _probe_lsof(8080)
    assert "python3" in result
    assert "12345" in result
    assert "8080" in result


def test_analyze_port_occupancy_both_fail(monkeypatch):
    """Test when both probes fail -> UNRESOLVED."""
    
    def mock_probe_ss(port):
        return "NOT AVAILABLE (ss command failed)"
    
    def mock_probe_lsof(port):
        return "NOT AVAILABLE (lsof command failed)"
    
    monkeypatch.setattr(
        "src.gui.services.runtime_context._probe_ss",
        mock_probe_ss
    )
    monkeypatch.setattr(
        "src.gui.services.runtime_context._probe_lsof",
        mock_probe_lsof
    )
    
    ss_out, lsof_out, bound, verdict = _analyze_port_occupancy(8080)
    
    assert "NOT AVAILABLE" in ss_out
    assert "NOT AVAILABLE" in lsof_out
    assert bound == "no"  # No LISTEN in output
    assert "UNRESOLVED" in verdict or "PORT NOT BOUND" in verdict


def test_analyze_port_occupancy_ss_has_pid(monkeypatch):
    """Test when ss returns PID."""
    
    def mock_probe_ss(port):
        return 'State  Recv-Q Send-Q Local Address:Port Peer Address:Port Process\nLISTEN 0      128    127.0.0.1:8080    0.0.0.0:*      users:(("python3",pid=12345,fd=3))'
    
    def mock_probe_lsof(port):
        return "NOT AVAILABLE (lsof command failed)"
    
    monkeypatch.setattr(
        "src.gui.services.runtime_context._probe_ss",
        mock_probe_ss
    )
    monkeypatch.setattr(
        "src.gui.services.runtime_context._probe_lsof",
        mock_probe_lsof
    )
    
    ss_out, lsof_out, bound, verdict = _analyze_port_occupancy(8080)
    
    assert "pid=12345" in ss_out
    assert "NOT AVAILABLE" in lsof_out
    assert bound == "yes"
    assert "PID 12345" in verdict


def test_analyze_port_occupancy_lsof_has_pid(monkeypatch):
    """Test when lsof returns PID (ss empty)."""
    
    def mock_probe_ss(port):
        return "State  Recv-Q Send-Q Local Address:Port Peer Address:Port"
    
    def mock_probe_lsof(port):
        return "python3   12345  user    3u  IPv4  12345      0t0  TCP *:8080 (LISTEN)"
    
    monkeypatch.setattr(
        "src.gui.services.runtime_context._probe_ss",
        mock_probe_ss
    )
    monkeypatch.setattr(
        "src.gui.services.runtime_context._probe_lsof",
        mock_probe_lsof
    )
    
    ss_out, lsof_out, bound, verdict = _analyze_port_occupancy(8080)
    
    assert "LISTEN" in ss_out or bound == "yes"  # ss shows LISTEN but no PID
    assert "12345" in lsof_out
    assert bound == "yes"
    assert "PID 12345" in verdict


def test_analyze_port_occupancy_bound_no_pid(monkeypatch):
    """Test when port is bound but no PID identified."""
    
    def mock_probe_ss(port):
        return "State  Recv-Q Send-Q Local Address:Port Peer Address:Port\nLISTEN 0      128    127.0.0.1:8080    0.0.0.0:*"
    
    def mock_probe_lsof(port):
        return "COMMAND  PID USER   FD   TYPE DEVICE SIZE/OFF NODE NAME"
    
    monkeypatch.setattr(
        "src.gui.services.runtime_context._probe_ss",
        mock_probe_ss
    )
    monkeypatch.setattr(
        "src.gui.services.runtime_context._probe_lsof",
        mock_probe_lsof
    )
    
    ss_out, lsof_out, bound, verdict = _analyze_port_occupancy(8080)
    
    assert bound == "yes"
    assert "UNRESOLVED" in verdict
    assert "bound but no PID" in verdict


def test_write_runtime_context_integration(monkeypatch, tmp_path):
    """Integration test: write_runtime_context produces correct Network section."""
    
    # Mock probes to return known values
    def mock_probe_ss(port):
        return "ss output with pid=9999"
    
    def mock_probe_lsof(port):
        return "lsof output"
    
    monkeypatch.setattr(
        "src.gui.services.runtime_context._probe_ss",
        mock_probe_ss
    )
    monkeypatch.setattr(
        "src.gui.services.runtime_context._probe_lsof",
        mock_probe_lsof
    )
    
    # Import after monkeypatching
    from src.gui.services.runtime_context import write_runtime_context
    
    out_path = tmp_path / "RUNTIME_CONTEXT.md"
    
    # Write runtime context
    result_path = write_runtime_context(
        out_path=str(out_path),
        entrypoint="test.py",
        listen_port=9090,
    )
    
    assert result_path.exists()
    content = result_path.read_text()
    
    # Check required sections
    assert "## Network" in content
    assert "Listen: :9090" in content
    assert "Port occupancy (9090):" in content
    assert "### ss" in content
    assert "### lsof" in content
    assert "### Resolution" in content
    assert "- Bound:" in content
    assert "- Process identified:" in content
    assert "- Final verdict:" in content
    
    # Check our mocked PID appears
    assert "pid=9999" in content or "PID 9999" in content


if __name__ == "__main__":
    pytest.main([__file__, "-v"])