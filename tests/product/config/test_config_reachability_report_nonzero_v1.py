"""
Test that config reachability instrumentation records at least one config load.

This test ensures that the reachability reporting system is functional and
that a minimal job (or any config load) results in a non‑zero report.
"""

import json
import tempfile
from pathlib import Path
from src.config import (
    reset_config_load_records,
    get_config_load_records,
    enable_config_recording,
    write_config_load_report,
    load_profile,
    clear_config_caches,
)


def test_reachability_records_at_least_one_config() -> None:
    """
    Verify that loading a profile increments the config load counter.
    
    Steps:
    1. Reset records and enable recording.
    2. Clear caches to force a fresh load.
    3. Load a known profile (CME_MNQ_TPE_v1).
    4. Assert that the recorded configs count > 0.
    5. Optionally verify the specific path is recorded.
    """
    # Ensure recording is enabled
    enable_config_recording(True)
    reset_config_load_records()
    
    # Clear caches to ensure a fresh load (not from cache)
    clear_config_caches()
    
    # Load a profile that is guaranteed to exist after HARD DELETE
    profile_id = "CME_MNQ_TPE_v1"
    try:
        profile = load_profile(profile_id)
    except Exception as e:
        # If profile doesn't exist, skip the test? But it must exist.
        raise AssertionError(f"Profile {profile_id} failed to load: {e}")
    
    # Get records
    records = get_config_load_records()
    
    # Must have at least one recorded config
    assert len(records) > 0, (
        f"Expected at least one config load after loading profile {profile_id}, "
        f"but got {len(records)} records. Reachability instrumentation may be broken."
    )
    
    # The loaded profile should appear in records
    expected_rel_path = f"profiles/{profile_id}.yaml"
    found = any(expected_rel_path in path for path in records.keys())
    assert found, (
        f"Expected to find '{expected_rel_path}' in records, but got: {list(records.keys())}"
    )
    
    # Each record should have count >= 1 and a SHA256
    for path, info in records.items():
        assert info["count"] >= 1, f"Record {path} has count {info['count']}"
        assert info["sha256"] is not None, f"Record {path} missing SHA256"
        # SHA256 should be 64 hex characters
        assert len(info["sha256"]) == 64, f"Record {path} SHA256 length invalid"


def test_write_config_load_report_produces_valid_json() -> None:
    """
    Verify that write_config_load_report generates a well‑formed JSON report.
    """
    # Reset and load something to have data
    enable_config_recording(True)
    reset_config_load_records()
    clear_config_caches()
    
    # Load a profile to generate a record
    load_profile("CME_MNQ_TPE_v1")
    
    # Write report to a temporary directory
    with tempfile.TemporaryDirectory() as tmpdir:
        output_dir = Path(tmpdir)
        write_config_load_report(output_dir)
        
        report_path = output_dir / "loaded_configs_report.json"
        summary_path = output_dir / "loaded_configs_summary.txt"
        
        # JSON report must exist
        assert report_path.exists(), f"Report file not created: {report_path}"
        
        # Parse JSON
        with open(report_path, "r", encoding="utf-8") as f:
            report = json.load(f)
        
        # Validate structure
        assert "generated_at" in report
        assert "generated_at_iso" in report
        assert "configs_loaded" in report
        assert "records" in report
        
        # configs_loaded must match length of records
        assert report["configs_loaded"] == len(report["records"])
        
        # At least one config loaded
        assert report["configs_loaded"] > 0, "Report claims zero configs loaded"
        
        # Summary file must exist
        assert summary_path.exists(), f"Summary file not created: {summary_path}"
        
        # Summary content should contain the count
        with open(summary_path, "r", encoding="utf-8") as f:
            summary_text = f.read()
        assert "Total config files loaded:" in summary_text


def test_reachability_records_cache_hits() -> None:
    """
    Verify that repeated loads of the same config do NOT increment the count
    when the load is served from cache (i.e., no YAML file read).
    
    The instrumentation records YAML file reads, not logical loads.
    """
    enable_config_recording(True)
    reset_config_load_records()
    clear_config_caches()
    
    profile_id = "CME_MNQ_TPE_v1"
    
    # First load (reads YAML from disk)
    load_profile(profile_id)
    records = get_config_load_records()
    first_count = records.get(f"profiles/{profile_id}.yaml", {}).get("count", 0)
    assert first_count == 1, f"First load should record count=1, got {first_count}"
    
    # Second load (served from LRU cache, no YAML read)
    load_profile(profile_id)
    records = get_config_load_records()
    second_count = records.get(f"profiles/{profile_id}.yaml", {}).get("count", 0)
    
    # Count should stay the same because no file was read
    assert second_count == first_count, (
        f"Expected count unchanged on cache hit, got {first_count} -> {second_count}"
    )