
"""Test that read_tail reads last n lines efficiently without loading entire file."""

from __future__ import annotations

from pathlib import Path

import pytest

from FishBroWFS_V2.control.app_nicegui import read_tail


def test_read_tail_returns_last_n_lines(tmp_path: Path) -> None:
    """Test that read_tail returns exactly the last n lines."""
    p = tmp_path / "big.log"
    lines = [f"line {i}\n" for i in range(5000)]
    p.write_text("".join(lines), encoding="utf-8")

    out = read_tail(p, n=200)
    out_lines = out.splitlines()

    assert len(out_lines) == 200
    assert out_lines[0] == "line 4800"
    assert out_lines[-1] == "line 4999"


def test_read_tail_handles_small_file(tmp_path: Path) -> None:
    """Test that read_tail handles files with fewer lines than requested."""
    p = tmp_path / "small.log"
    lines = [f"line {i}\n" for i in range(50)]
    p.write_text("".join(lines), encoding="utf-8")

    out = read_tail(p, n=200)
    out_lines = out.splitlines()

    assert len(out_lines) == 50
    assert out_lines[0] == "line 0"
    assert out_lines[-1] == "line 49"


def test_read_tail_handles_empty_file(tmp_path: Path) -> None:
    """Test that read_tail handles empty files."""
    p = tmp_path / "empty.log"
    p.touch()

    out = read_tail(p, n=200)
    assert out == ""


def test_read_tail_handles_missing_file(tmp_path: Path) -> None:
    """Test that read_tail handles missing files gracefully."""
    p = tmp_path / "missing.log"

    out = read_tail(p, n=200)
    assert out == ""


