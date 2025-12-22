
"""Test that Streamlit viewer has zero-write guarantee (including mtime)."""
import tempfile
from pathlib import Path

from FishBroWFS_V2.utils.fs_snapshot import snapshot_tree, diff_snap
from tests.hardening.zero_write_patch import ZeroWritePatch


def test_streamlit_viewer_zero_write():
    """Guarantee Streamlit viewer zero write (including mtime)."""
    # Create temp outputs root
    with tempfile.TemporaryDirectory() as tmpdir:
        outputs_root = Path(tmpdir) / "outputs"
        outputs_root.mkdir()
        
        # Create minimal plan package
        plan_dir = outputs_root / "portfolio" / "plans" / "plan_test_zero_write"
        plan_dir.mkdir(parents=True)
        
        # Create minimal plan package files
        plan_files = [
            "portfolio_plan.json",
            "plan_manifest.json",
            "plan_metadata.json",
            "plan_checksums.json",
        ]
        
        for filename in plan_files:
            (plan_dir / filename).write_text('{"test": "data"}')
        
        # Create view files (optional for this test)
        view_file = plan_dir / "plan_view.json"
        view_file.write_text('{"plan_id": "plan_test_zero_write", "test": "view"}')
        
        # Take snapshot before
        snap_before = snapshot_tree(outputs_root, include_sha256=True)
        
        # Use unified zero-write patch
        with ZeroWritePatch() as patcher:
            # Import the viewer module (should not scan on import due to lazy scanning)
            import FishBroWFS_V2.ui.plan_viewer as viewer_module
            
            # Call the scan function (this is what the sidebar would do)
            available_plans = viewer_module.scan_plan_ids(outputs_root)
            
            # Try to load a plan view
            try:
                view_data = viewer_module.load_view(outputs_root, "plan_test_zero_write")
            except (FileNotFoundError, ValueError):
                # Expected if view file doesn't match schema, but that's OK
                pass
        
        # Take snapshot after
        snap_after = snapshot_tree(outputs_root, include_sha256=True)
        
        # Verify no writes detected
        assert len(patcher.write_calls) == 0, f"Write operations detected: {patcher.write_calls}"
        
        # Verify file system unchanged
        diff = diff_snap(snap_before, snap_after)
        assert diff["added"] == [], f"Files added: {diff['added']}"
        assert diff["removed"] == [], f"Files removed: {diff['removed']}"
        assert diff["changed"] == [], f"Files changed: {diff['changed']}"
        
        # Verify mtimes unchanged by checking specific files
        for rel_path, snap in snap_before.items():
            if rel_path in snap_after:
                assert snap.mtime_ns == snap_after[rel_path].mtime_ns, \
                    f"mtime changed for {rel_path}"


