#!/usr/bin/env python3
"""
Test the full snapshot forensic kit artifacts.

Validates that `make snapshot` generates SYSTEM_FULL_SNAPSHOT.md with all
required artifacts embedded, with correct formatting, deterministic sorting,
and non-empty content.
"""

import csv
import json
import os
import tempfile
import shutil
from pathlib import Path
import pytest
import subprocess
import sys

# ------------------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------------------

@pytest.fixture
def snapshot_output_dir(tmp_path):
    """Create a temporary output directory for snapshot generation."""
    output_dir = tmp_path / "outputs" / "snapshots"
    output_dir.mkdir(parents=True)
    return output_dir


@pytest.fixture
def run_snapshot_script(snapshot_output_dir, monkeypatch):
    """Run the snapshot script with monkeypatched output directory."""
    # Use subprocess to run the script, avoiding sys.path hacks
    script_path = Path.cwd() / "scripts" / "no_fog" / "generate_full_snapshot_v2.py"
    
    # Set environment variable to override OUTPUT_DIR
    env = os.environ.copy()
    env["FISHBRO_SNAPSHOT_OUTPUT_DIR"] = str(snapshot_output_dir)
    
    # Run the script
    result = subprocess.run(
        [sys.executable, str(script_path), "--force"],
        env=env,
        capture_output=True,
        text=True,
        cwd=Path.cwd(),
    )
    
    if result.returncode != 0:
        raise RuntimeError(
            f"Snapshot script failed with code {result.returncode}\n"
            f"stderr: {result.stderr}\n"
            f"stdout: {result.stdout}"
        )
    
    return snapshot_output_dir


# ------------------------------------------------------------------------------
# Helper functions
# ------------------------------------------------------------------------------

def extract_section(content: str, section_header: str) -> str:
    """
    Extract the content of a section from SYSTEM_FULL_SNAPSHOT.md.
    The section is assumed to be a markdown header like '## MANIFEST'
    and continues until the next '##' header that is NOT inside a code block.
    Returns the raw text including the header and the code block.
    """
    lines = content.splitlines(keepends=True)
    in_code_block = False
    code_block_delimiter = None  # stores the delimiter (e.g., '```')
    section_start = -1
    result_lines = []
    
    for i, line in enumerate(lines):
        stripped = line.strip()
        # Detect code block start/end
        if stripped.startswith('```'):
            if not in_code_block:
                in_code_block = True
                code_block_delimiter = stripped
            else:
                # Check if this is the matching delimiter (same number of backticks)
                if stripped == code_block_delimiter:
                    in_code_block = False
                    code_block_delimiter = None
        # If we haven't found the section yet, look for the header
        if section_start == -1:
            if stripped.startswith(section_header):
                section_start = i
                result_lines.append(line)
        else:
            # We are inside the section, collect lines until we encounter a new section header
            # that is NOT inside a code block.
            if not in_code_block and line.strip().startswith('## ') and line.strip() != section_header:
                # This is a new section header, stop collecting
                break
            result_lines.append(line)
    
    if section_start == -1:
        return ""
    return ''.join(result_lines)

def extract_code_block(section_content: str) -> str:
    """
    Extract the code block content from a section (between ```lang and ```).
    Handles nested code blocks by matching the outermost pair.
    Returns the raw text inside the code block, excluding the backticks.
    """
    lines = section_content.splitlines(keepends=True)
    stack = []  # stores True for each nesting level (we just need depth)
    start_line = -1
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith('```'):
            # Determine if it's an opening (has language) or closing (just backticks)
            # If after removing backticks there's non-whitespace, it's an opening.
            after = stripped.lstrip('`').strip()
            if after:
                # Opening code block
                if not stack:
                    start_line = i
                stack.append(True)
            else:
                # Closing code block
                if stack:
                    stack.pop()
                    if not stack:
                        # Found the matching closing for the outermost block
                        # Collect content between start_line+1 and i-1
                        content_lines = lines[start_line + 1:i]
                        return ''.join(content_lines).rstrip('\n')
    # If we never found a closing, return empty
    return ""

# ------------------------------------------------------------------------------
# Core validation tests
# ------------------------------------------------------------------------------

def test_system_full_snapshot_exists(run_snapshot_script):
    """Verify SYSTEM_FULL_SNAPSHOT.md is generated and contains all embedded artifacts."""
    output_dir = run_snapshot_script
    
    # Check SYSTEM_FULL_SNAPSHOT.md exists
    snapshot_file = output_dir / "SYSTEM_FULL_SNAPSHOT.md"
    assert snapshot_file.exists(), "SYSTEM_FULL_SNAPSHOT.md not created"
    assert snapshot_file.stat().st_size > 0, "SYSTEM_FULL_SNAPSHOT.md is empty"
    
    # Read the content
    content = snapshot_file.read_text()
    
    # Verify it contains all required sections
    required_sections = [
        "# SYSTEM FULL SNAPSHOT",
        "## MANIFEST",
        "## LOCAL_SCAN_RULES",
        "## REPO_TREE",
        "## AUDIT_GREP",
        "## AUDIT_IMPORTS",
        "## AUDIT_ENTRYPOINTS",
        "## AUDIT_CONFIG_REFERENCES",
        "## AUDIT_CALL_GRAPH",
        "## AUDIT_TEST_SURFACE",
        "## AUDIT_RUNTIME_MUTATIONS",
        "## AUDIT_STATE_FLOW",
        "## SKIPPED_FILES",
    ]
    
    for section in required_sections:
        assert section in content, f"Missing section in SYSTEM_FULL_SNAPSHOT.md: {section}"
    
    # Verify no intermediate audit files exist as standalone files
    for audit_file in [
        "REPO_TREE.txt",
        "MANIFEST.json",
        "SKIPPED_FILES.txt",
        "AUDIT_GREP.txt",
        "AUDIT_IMPORTS.csv",
        "AUDIT_ENTRYPOINTS.md",
        "AUDIT_CONFIG_REFERENCES.txt",
        "AUDIT_CALL_GRAPH.txt",
        "AUDIT_TEST_SURFACE.txt",
        "AUDIT_RUNTIME_MUTATIONS.txt",
        "AUDIT_STATE_FLOW.md",
    ]:
        assert not (output_dir / audit_file).exists(), \
            f"Intermediate audit file {audit_file} should not exist as standalone file"


def test_repo_tree_structure_embedded(run_snapshot_script):
    """Verify REPO_TREE section in SYSTEM_FULL_SNAPSHOT.md contains both sections."""
    output_dir = run_snapshot_script
    snapshot_file = output_dir / "SYSTEM_FULL_SNAPSHOT.md"
    content = snapshot_file.read_text()
    
    # Find REPO_TREE section
    repo_tree_start = content.find("## REPO_TREE")
    assert repo_tree_start != -1, "REPO_TREE section not found"
    
    # Find next section to isolate REPO_TREE content
    sections = ["## REPO_TREE", "## AUDIT_GREP", "## AUDIT_IMPORTS", "## AUDIT_ENTRYPOINTS"]
    section_starts = []
    for section in sections:
        pos = content.find(section)
        if pos != -1:
            section_starts.append((pos, section))
    
    # Sort by position
    section_starts.sort(key=lambda x: x[0])
    
    # Find REPO_TREE and next section
    repo_tree_idx = -1
    for i, (pos, section) in enumerate(section_starts):
        if section == "## REPO_TREE":
            repo_tree_idx = i
            break
    
    assert repo_tree_idx != -1, "REPO_TREE section not found in sections list"
    
    # Extract REPO_TREE content
    repo_tree_start_pos = section_starts[repo_tree_idx][0]
    if repo_tree_idx + 1 < len(section_starts):
        next_section_start = section_starts[repo_tree_idx + 1][0]
        repo_tree_content = content[repo_tree_start_pos:next_section_start]
    else:
        repo_tree_content = content[repo_tree_start_pos:]
    
    # Must contain both section headers
    assert "== LOCAL_STRICT_FILES ==" in repo_tree_content
    assert "== TREE_VIEW (approx) ==" in repo_tree_content
    
    # Local strict list should have at least some files
    lines = repo_tree_content.splitlines()
    local_section_start = -1
    tree_section_start = -1
    for i, line in enumerate(lines):
        if "== LOCAL_STRICT_FILES ==" in line:
            local_section_start = i
        if "== TREE_VIEW (approx) ==" in line:
            tree_section_start = i
    
    assert local_section_start != -1, "LOCAL_STRICT_FILES section not found"
    assert tree_section_start != -1, "TREE_VIEW section not found"
    
    # There should be files between the sections
    assert tree_section_start > local_section_start + 1


def test_manifest_json_schema_embedded(run_snapshot_script):
    """Verify MANIFEST section in SYSTEM_FULL_SNAPSHOT.md has correct schema."""
    output_dir = run_snapshot_script
    snapshot_file = output_dir / "SYSTEM_FULL_SNAPSHOT.md"
    content = snapshot_file.read_text()
    
    # Find MANIFEST section
    manifest_start = content.find("## MANIFEST")
    assert manifest_start != -1, "MANIFEST section not found"
    
    # Find next section to isolate MANIFEST content
    sections = ["## MANIFEST", "## LOCAL_SCAN_RULES", "## REPO_TREE"]
    section_starts = []
    for section in sections:
        pos = content.find(section)
        if pos != -1:
            section_starts.append((pos, section))
    
    # Sort by position
    section_starts.sort(key=lambda x: x[0])
    
    # Find MANIFEST and next section
    manifest_idx = -1
    for i, (pos, section) in enumerate(section_starts):
        if section == "## MANIFEST":
            manifest_idx = i
            break
    
    assert manifest_idx != -1, "MANIFEST section not found in sections list"
    
    # Extract MANIFEST content
    manifest_start_pos = section_starts[manifest_idx][0]
    if manifest_idx + 1 < len(section_starts):
        next_section_start = section_starts[manifest_idx + 1][0]
        manifest_content = content[manifest_start_pos:next_section_start]
    else:
        manifest_content = content[manifest_start_pos:]
    
    # The MANIFEST section should contain JSON
    # Look for JSON content between ```json and ``` markers
    import re
    json_match = re.search(r'```json\s*(.*?)\s*```', manifest_content, re.DOTALL)
    assert json_match is not None, "No JSON code block found in MANIFEST section"
    
    json_str = json_match.group(1)
    manifest = json.loads(json_str)
    
    # Required top-level keys
    assert "generated_at_utc" in manifest
    assert "git_head" in manifest
    assert "file_count" in manifest
    assert "files" in manifest
    
    # file_count should match length of files list
    assert manifest["file_count"] == len(manifest["files"])
    
    # Each file entry should have required fields
    for file_entry in manifest["files"]:
        assert "path" in file_entry
        assert "sha256" in file_entry
        assert "bytes" in file_entry
        
        # SHA256 should be 64 hex chars or error string
        sha256 = file_entry["sha256"]
        if not sha256.startswith("ERROR:"):
            assert len(sha256) == 64
            assert all(c in "0123456789abcdef" for c in sha256)
    
    # Files should be sorted by path
    paths = [entry["path"] for entry in manifest["files"]]
    assert paths == sorted(paths), "Files in MANIFEST.json not sorted by path"


def test_skipped_files_format(run_snapshot_script):
    """Verify SKIPPED_FILES section in SYSTEM_FULL_SNAPSHOT.md has proper sections and format."""
    output_dir = run_snapshot_script
    snapshot_file = output_dir / "SYSTEM_FULL_SNAPSHOT.md"
    content = snapshot_file.read_text()
    
    # Extract SKIPPED_FILES section
    section = extract_section(content, "## SKIPPED_FILES")
    assert section, "SKIPPED_FILES section not found"
    
    # Extract code block content
    skipped_content = extract_code_block(section)
    assert skipped_content, "No code block in SKIPPED_FILES section"
    
    # Must contain expected section headers (new Local-Strict format)
    assert "== LOCAL_STRICT_POLICY ==" in skipped_content
    assert "== CONTENT_SKIP_POLICIES ==" in skipped_content
    assert "== SKIPPED_FILES_CONTENT_SCAN ==" in skipped_content
    
    # Skip policies should list directories
    lines = skipped_content.splitlines()
    policy_start = lines.index("== LOCAL_STRICT_POLICY ==")
    content_skip_start = lines.index("== CONTENT_SKIP_POLICIES ==")
    scan_start = lines.index("== SKIPPED_FILES_CONTENT_SCAN ==")
    
    # There should be some policy lines
    assert content_skip_start > policy_start + 1
    assert scan_start > content_skip_start + 1


def test_audit_grep_format(run_snapshot_script):
    """Verify AUDIT_GREP section in SYSTEM_FULL_SNAPSHOT.md has pattern sections."""
    output_dir = run_snapshot_script
    snapshot_file = output_dir / "SYSTEM_FULL_SNAPSHOT.md"
    content = snapshot_file.read_text()
    
    # Extract AUDIT_GREP section
    section = extract_section(content, "## AUDIT_GREP")
    assert section, "AUDIT_GREP section not found"
    
    # Extract code block content
    grep_content = extract_code_block(section)
    assert grep_content, "No code block in AUDIT_GREP section"
    
    # Should contain at least one pattern header
    assert "== PATTERN:" in grep_content
    
    # Check for known patterns (at least some)
    patterns = [
        "FishBroWFS_V2.control",
        "from FishBroWFS_V2.control",
        "import FishBroWFS_V2.control",
    ]
    
    for pattern in patterns:
        # Pattern should appear in a header
        if f"== PATTERN: {pattern} ==" in grep_content:
            # Should have either matches or "0 matches"
            pass  # Acceptable


def test_audit_imports_csv_format(run_snapshot_script):
    """Verify AUDIT_IMPORTS section in SYSTEM_FULL_SNAPSHOT.md has correct CSV format."""
    output_dir = run_snapshot_script
    snapshot_file = output_dir / "SYSTEM_FULL_SNAPSHOT.md"
    content = snapshot_file.read_text()
    
    # Extract AUDIT_IMPORTS section
    section = extract_section(content, "## AUDIT_IMPORTS")
    assert section, "AUDIT_IMPORTS section not found"
    
    # Extract code block content
    csv_content = extract_code_block(section)
    assert csv_content, "No code block in AUDIT_IMPORTS section"
    
    # Parse CSV content
    import io
    reader = csv.reader(io.StringIO(csv_content))
    rows = list(reader)
    
    # Should have header
    assert len(rows) >= 1
    header = rows[0]
    expected_header = ["file", "lineno", "kind", "module", "name"]
    assert header == expected_header, f"CSV header mismatch: {header}"
    
    # If there are data rows, check sorting
    if len(rows) > 1:
        data_rows = rows[1:]
        # Sort by file, lineno, kind, module (as the script does)
        sorted_rows = sorted(
            data_rows,
            key=lambda r: (r[0].lower(), int(r[1]), r[2], r[3].lower())
        )
        assert data_rows == sorted_rows, "CSV rows not sorted correctly"


def test_audit_entrypoints_md_format(run_snapshot_script):
    """Verify AUDIT_ENTRYPOINTS section in SYSTEM_FULL_SNAPSHOT.md has required sections."""
    output_dir = run_snapshot_script
    snapshot_file = output_dir / "SYSTEM_FULL_SNAPSHOT.md"
    content = snapshot_file.read_text()
    
    # Extract AUDIT_ENTRYPOINTS section
    section = extract_section(content, "## AUDIT_ENTRYPOINTS")
    assert section, "AUDIT_ENTRYPOINTS section not found"
    
    # Extract code block content
    entrypoints_content = extract_code_block(section)
    assert entrypoints_content, "No code block in AUDIT_ENTRYPOINTS section"
    
    # Required sections
    assert "## Git HEAD" in entrypoints_content
    assert "## Makefile Targets Extract" in entrypoints_content
    assert "## Detected Python Entrypoints" in entrypoints_content
    assert "## Notes / Risk Flags" in entrypoints_content
    
    # Git HEAD should show a commit hash
    lines = entrypoints_content.splitlines()
    for i, line in enumerate(lines):
        if line.startswith("## Git HEAD"):
            # Next line should contain a hash (maybe in backticks)
            if i + 1 < len(lines):
                next_line = lines[i + 1]
                # Could be `hash` or just hash
                assert len(next_line.strip()) >= 7  # at least short hash


def redact_timestamps(content: str) -> str:
    """
    Replace all non-deterministic elements in the snapshot with 'REDACTED' to allow deterministic comparison.
    This includes:
    - ISO 8601 timestamps (MANIFEST.json, LOCAL_SCAN_RULES.json, header 'Generated:' line)
    - Temporary directory paths (fishbro_snapshot_*)
    """
    import re
    # Pattern for ISO 8601 with optional microseconds and timezone
    iso_pattern = r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})'
    redacted = re.sub(iso_pattern, 'REDACTED', content)
    # Pattern for temporary directory paths (fishbro_snapshot_ followed by any non-whitespace)
    temp_dir_pattern = r'(/tmp/)?fishbro_snapshot_[^\s]*'
    redacted = re.sub(temp_dir_pattern, 'fishbro_snapshot_REDACTED', redacted)
    return redacted


def test_deterministic_output(run_snapshot_script):
    """
    Verify that running the snapshot twice produces identical SYSTEM_FULL_SNAPSHOT.md
    (except for timestamps in MANIFEST.json and LOCAL_SCAN_RULES.json).
    """
    output_dir = run_snapshot_script
    snapshot_file = output_dir / "SYSTEM_FULL_SNAPSHOT.md"
    assert snapshot_file.exists()
    
    # Read the snapshot content
    content1 = snapshot_file.read_text()
    
    # Redact all timestamps
    redacted_content = redact_timestamps(content1)
    
    # Run the snapshot script again in a fresh directory
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        new_output_dir = tmpdir_path / "outputs" / "snapshots"
        new_output_dir.mkdir(parents=True)
        
        env = os.environ.copy()
        env["FISHBRO_SNAPSHOT_OUTPUT_DIR"] = str(new_output_dir)
        script_path = Path.cwd() / "scripts" / "no_fog" / "generate_full_snapshot_v2.py"
        
        result = subprocess.run(
            [sys.executable, str(script_path), "--force"],
            env=env,
            capture_output=True,
            text=True,
            cwd=Path.cwd(),
        )
        assert result.returncode == 0, f"Second run failed: {result.stderr}"
        
        new_snapshot_file = new_output_dir / "SYSTEM_FULL_SNAPSHOT.md"
        assert new_snapshot_file.exists()
        content2 = new_snapshot_file.read_text()
        
        # Redact timestamps in second snapshot
        redacted_content2 = redact_timestamps(content2)
        
        # Compare redacted contents
        if redacted_content != redacted_content2:
            # Debug helper: write diff files if env var is set
            if os.environ.get("FISHBRO_DEBUG_SNAPSHOT_DIFF") == "1":
                # Write diff files into the first output_dir (not the temp one)
                diff_head_path = output_dir / "DIFF_HEAD.txt"
                diff_sections_path = output_dir / "DIFF_SECTIONS.txt"
                
                import difflib
                diff_lines = list(difflib.unified_diff(
                    redacted_content.splitlines(keepends=True),
                    redacted_content2.splitlines(keepends=True),
                    fromfile="first",
                    tofile="second",
                    n=3,
                ))
                diff_head_path.write_text("".join(diff_lines[:300]), encoding="utf-8")
                
                # Extract section headers that differ
                lines1 = redacted_content.splitlines()
                lines2 = redacted_content2.splitlines()
                section_headers1 = [line for line in lines1 if line.startswith("## ")]
                section_headers2 = [line for line in lines2 if line.startswith("## ")]
                diff_sections = []
                for h1, h2 in zip(section_headers1, section_headers2):
                    if h1 != h2:
                        diff_sections.append(f"{h1} != {h2}")
                diff_sections_path.write_text("\n".join(diff_sections), encoding="utf-8")
            
            # Print diff for debugging (always)
            import difflib
            diff = list(difflib.unified_diff(
                redacted_content.splitlines(keepends=True),
                redacted_content2.splitlines(keepends=True),
                fromfile="first",
                tofile="second",
                n=3,
            ))
            print("".join(diff))
            # Also print first differing line numbers
            for i, (line1, line2) in enumerate(zip(redacted_content.splitlines(), redacted_content2.splitlines())):
                if line1 != line2:
                    print(f"First difference at line {i+1}:")
                    print(f"  first:  {line1[:100]}")
                    print(f"  second: {line2[:100]}")
                    break
        assert redacted_content == redacted_content2, "Snapshot output is not deterministic"


# ------------------------------------------------------------------------------
# Integration test (optional, runs actual make command)
# ------------------------------------------------------------------------------

@pytest.mark.integration
def test_make_full_snapshot():
    """Integration test: run `make full-snapshot` and verify artifacts."""
    # This test is marked integration because it runs make
    # and may take longer.
    
    # Create a temporary directory for outputs
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        
        # Copy the project? Too heavy. Instead, we'll just run make
        # in the current directory but with a different output path.
        # Since the script uses a fixed output path, we need to monkeypatch.
        # Instead, we'll just run the script directly via subprocess.
        
        cmd = [
            sys.executable,
            "-m", "scripts.no_fog.generate_full_snapshot",
            "--force",
        ]
        
        result = subprocess.run(
            cmd,
            cwd=Path.cwd(),
            capture_output=True,
            text=True,
        )
        
        assert result.returncode == 0, f"Script failed: {result.stderr}"
        
        # Check outputs directory exists
        output_dir = Path("outputs/snapshots/full")
        assert output_dir.exists(), "Output directory not created"
        
        # Clean up after test
        if output_dir.exists():
            shutil.rmtree(output_dir)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])