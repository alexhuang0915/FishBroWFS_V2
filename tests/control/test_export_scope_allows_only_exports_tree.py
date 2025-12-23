"""
Test that season export write scope only allows files under exports/seasons/{season}/.

P0-3: Season Export WriteScope 對齊真實輸出（防漏檔）
"""

import os
from pathlib import Path

import pytest

from FishBroWFS_V2.utils.write_scope import create_season_export_scope, WriteScope


def test_export_scope_allows_exports_tree(tmp_path: Path) -> None:
    """Create a scope under exports/seasons/{season} and verify allowed paths."""
    exports_root = tmp_path / "outputs" / "exports"
    season = "2026Q1"
    export_root = exports_root / "seasons" / season
    
    # Set environment variable for exports root
    os.environ["FISHBRO_EXPORTS_ROOT"] = str(exports_root)
    
    scope = create_season_export_scope(export_root)
    assert isinstance(scope, WriteScope)
    assert scope.root_dir == export_root
    
    # Allowed: any file under export_root
    scope.assert_allowed_rel("season_index.json")
    scope.assert_allowed_rel("batches/batch1/metadata.json")
    scope.assert_allowed_rel("batches/batch1/index.json")
    scope.assert_allowed_rel("deep/nested/file.txt")
    
    # Disallowed: paths with ".." that escape
    with pytest.raises(ValueError, match="must not contain"):
        scope.assert_allowed_rel("../outside.json")
    
    with pytest.raises(ValueError, match="must not contain"):
        scope.assert_allowed_rel("batches/../../escape.json")
    
    # Disallowed: absolute paths
    with pytest.raises(ValueError, match="must not be absolute"):
        scope.assert_allowed_rel("/etc/passwd")
    
    # The scope should prevent escaping via symlinks or resolved paths
    # (tested by the is_relative_to check inside WriteScope)


def test_export_scope_rejects_wrong_root(tmp_path: Path) -> None:
    """create_season_export_scope must reject roots not under exports/seasons/{season}."""
    exports_root = tmp_path / "outputs" / "exports"
    os.environ["FISHBRO_EXPORTS_ROOT"] = str(exports_root)
    
    # Wrong: not under exports root
    wrong_root = tmp_path / "other" / "seasons" / "2026Q1"
    with pytest.raises(ValueError, match="must be under exports root"):
        create_season_export_scope(wrong_root)
    
    # Wrong: under exports but not seasons/{season}
    wrong_root2 = exports_root / "other" / "2026Q1"
    with pytest.raises(ValueError, match="must be under exports"):
        create_season_export_scope(wrong_root2)
    
    # Wrong: missing seasons segment
    wrong_root3 = exports_root / "2026Q1"
    with pytest.raises(ValueError, match="must be under exports"):
        create_season_export_scope(wrong_root3)
    
    # Correct: exports/seasons/2026Q1
    correct_root = exports_root / "seasons" / "2026Q1"
    scope = create_season_export_scope(correct_root)
    assert scope.root_dir == correct_root


def test_export_scope_blocks_artifacts_and_season_index(tmp_path: Path) -> None:
    """
    Ensure the scope does not allow writing to outputs/artifacts/** or outputs/season_index/**.
    
    This is enforced by the root_dir being exports/seasons/{season}, and the
    is_relative_to check preventing escape.
    """
    exports_root = tmp_path / "outputs" / "exports"
    season = "2026Q1"
    export_root = exports_root / "seasons" / season
    export_root.mkdir(parents=True)
    
    os.environ["FISHBRO_EXPORTS_ROOT"] = str(exports_root)
    scope = create_season_export_scope(export_root)
    
    # Try to craft a relative path that would resolve outside export_root
    # via symlink or ".." is already caught.
    
    # Create a symlink inside export_root pointing to artifacts
    artifacts_root = tmp_path / "outputs" / "artifacts"
    artifacts_root.mkdir(parents=True)
    symlink_path = export_root / "link_to_artifacts"
    symlink_path.symlink_to(artifacts_root)
    
    # Writing to the symlink's child should still be under export_root
    # (because the symlink is inside export_root). The WriteScope's
    # is_relative_to check uses resolve(), which will follow the symlink
    # and detect the escape.
    # Let's test:
    target_path = symlink_path / "batch1" / "metadata.json"
    rel_path = target_path.relative_to(export_root)
    
    # The resolved path is outside export_root, so assert_allowed_rel should raise.
    with pytest.raises(ValueError, match="outside the scope root"):
        scope.assert_allowed_rel(str(rel_path))


def test_export_scope_wildcard_allows_any_file(tmp_path: Path) -> None:
    """Verify that the wildcard prefix '*' allows any file under export_root."""
    exports_root = tmp_path / "outputs" / "exports"
    season = "2026Q1"
    export_root = exports_root / "seasons" / season
    
    os.environ["FISHBRO_EXPORTS_ROOT"] = str(exports_root)
    scope = create_season_export_scope(export_root)
    
    # The scope uses "*" prefix to allow any file
    assert "*" in scope.allowed_rel_prefixes
    
    # Test various allowed paths
    for rel in [
        "file.txt",
        "subdir/file.json",
        "deep/nested/structure/data.bin",
    ]:
        scope.assert_allowed_rel(rel)
    
    # Ensure exact matches are not required
    assert len(scope.allowed_rel_files) == 0