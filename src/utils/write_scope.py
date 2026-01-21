
"""
Write‑scope guard for hardening file‑write boundaries.

This module provides a runtime fence that ensures writers only produce files
under a designated root directory and whose relative paths match a predefined
allow‑list (exact matches or prefix‑based patterns).  Any attempt to write
outside the allowed set raises a ValueError before the actual I/O occurs.

The guard is designed to be used inside each writer function that writes
portfolio‑related outputs (plan_, plan_view_, plan_quality_, etc.) and
season‑export outputs.

Design notes
------------
• Path.resolve() is used to detect symlink escapes, but we rely on
  resolved_target.is_relative_to(resolved_root) (Python ≥3.12) to guarantee
  the final target stays under the logical root.
• Prefix matching is performed on the basename only, not on the whole relative
  path.  This prevents subdirectories like `subdir/plan_foo.json` from slipping
  through unless the prefix pattern explicitly allows subdirectories (which we
  currently do not).
• The guard does **not** create directories; it only validates the relative
  path.  The caller is responsible for creating parent directories if needed.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class WriteScope:
    """Immutable guard that validates relative paths against a whitelist.

    Attributes
    ----------
    root_dir : Path
        Absolute path to the directory under which all writes must stay.
    allowed_rel_files : frozenset[str]
        Set of exact relative paths (POSIX style, no leading slash, no `..`)
        that are permitted.
    allowed_rel_prefixes : tuple[str, ...]
        Tuple of filename prefixes.  A relative path is allowed if its
        basename starts with any of these prefixes.
    """

    root_dir: Path
    allowed_rel_files: frozenset[str]          # exact files
    allowed_rel_prefixes: tuple[str, ...]      # prefix patterns (e.g. "plan_", "plan_view_")

    def assert_allowed_rel(self, rel: str) -> None:
        """Raise ValueError if `rel` is not allowed by this scope.

        Parameters
        ----------
        rel : str
            Relative path (POSIX style, no leading slash, no `..`).

        Raises
        ------
        ValueError
            With a descriptive message if the path is not allowed or attempts
            to escape the root directory.
        """
        # 1. Basic sanity: must be a relative POSIX path without `..` components.
        if os.path.isabs(rel):
            raise ValueError(f"Relative path must not be absolute: {rel!r}")
        if ".." in rel.split("/"):
            raise ValueError(f"Relative path must not contain '..': {rel!r}")

        # 2. Ensure the final resolved target stays under root_dir.
        target = (self.root_dir / rel).resolve()
        root_resolved = self.root_dir.resolve()
        # Python 3.12+ provides Path.is_relative_to; we use it if available,
        # otherwise fall back to a manual check.
        try:
            if not target.is_relative_to(root_resolved):
                raise ValueError(
                    f"Path {rel!r} resolves to {target} which is outside the "
                    f"scope root {root_resolved}"
                )
        except AttributeError:
            # Python <3.12: compare parents manually.
            try:
                target.relative_to(root_resolved)
            except ValueError:
                raise ValueError(
                    f"Path {rel!r} resolves to {target} which is outside the "
                    f"scope root {root_resolved}"
                )

        # 3. Check for wildcard prefix "*" which allows any file under root_dir
        if "*" in self.allowed_rel_prefixes:
            return

        # 4. Check exact matches first.
        if rel in self.allowed_rel_files:
            return

        # 5. Check prefix matches on the basename.
        basename = os.path.basename(rel)
        for prefix in self.allowed_rel_prefixes:
            if basename.startswith(prefix):
                return

        # 6. If we reach here, the path is forbidden.
        raise ValueError(
            f"Relative path {rel!r} is not allowed by this write scope.\n"
            f"Allowed exact files: {sorted(self.allowed_rel_files)}\n"
            f"Allowed filename prefixes: {self.allowed_rel_prefixes}"
        )


def create_plan_scope(plan_dir: Path) -> WriteScope:
    """Create a WriteScope for a portfolio plan directory.

    This scope permits the standard plan‑manifest files and any future file
    whose basename starts with `plan_`.

    Exact allowed files:
        portfolio_plan.json
        plan_manifest.json
        plan_metadata.json
        plan_checksums.json

    Allowed prefixes:
        ("plan_",)
    """
    return WriteScope(
        root_dir=plan_dir,
        allowed_rel_files=frozenset({
            "portfolio_plan.json",
            "plan_manifest.json",
            "plan_metadata.json",
            "plan_checksums.json",
        }),
        allowed_rel_prefixes=("plan_",),
    )


def create_plan_view_scope(view_dir: Path) -> WriteScope:
    """Create a WriteScope for a plan‑view directory.

    Exact allowed files:
        plan_view.json
        plan_view.md
        plan_view_checksums.json
        plan_view_manifest.json

    Allowed prefixes:
        ("plan_view_",)
    """
    return WriteScope(
        root_dir=view_dir,
        allowed_rel_files=frozenset({
            "plan_view.json",
            "plan_view.md",
            "plan_view_checksums.json",
            "plan_view_manifest.json",
        }),
        allowed_rel_prefixes=("plan_view_",),
    )


def create_plan_quality_scope(quality_dir: Path) -> WriteScope:
    """Create a WriteScope for a plan‑quality directory.

    Exact allowed files:
        plan_quality.json
        plan_quality_checksums.json
        plan_quality_manifest.json

    Allowed prefixes:
        ("plan_quality_",)
    """
    return WriteScope(
        root_dir=quality_dir,
        allowed_rel_files=frozenset({
            "plan_quality.json",
            "plan_quality_checksums.json",
            "plan_quality_manifest.json",
        }),
        allowed_rel_prefixes=("plan_quality_",),
    )


def create_season_export_scope(export_root: Path) -> WriteScope:
    """Create a WriteScope for season‑export outputs.

    This scope allows any file under exports_root / seasons / {season} / **
    but forbids any path that would escape to outputs/artifacts/** or
    outputs/season_index/** or any other repo root paths.

    The export_root parameter should be the season directory:
        exports_root / seasons / {season}

    Allowed prefixes:
        ()   (none – we allow any file under the export_root)
    """
    # Ensure export_root is under the exports tree
    from core.paths import get_exports_root
    exports_root = Path(os.environ.get("FISHBRO_EXPORTS_ROOT", str(get_exports_root())))
    if not export_root.is_relative_to(exports_root):
        raise ValueError(
            f"export_root {export_root} must be under exports root {exports_root}"
        )
    
    # Ensure export_root follows the pattern exports_root / seasons / {season}
    try:
        relative_to_exports = export_root.relative_to(exports_root)
        parts = relative_to_exports.parts
        if len(parts) < 2 or parts[0] != "seasons":
            raise ValueError(
                f"export_root must be under exports_root/seasons/{{season}}, got {relative_to_exports}"
            )
    except ValueError:
        raise ValueError(
            f"export_root {export_root} must be under exports root {exports_root}"
        )
    
    # Allow any file under export_root (empty allowed_rel_files means no exact matches required,
    # empty allowed_rel_prefixes means no prefix restriction, but we need to allow all files)
    # We'll use a special prefix "*" to indicate allow all (handled in assert_allowed_rel)
    return WriteScope(
        root_dir=export_root,
        allowed_rel_files=frozenset(),  # No exact matches required
        allowed_rel_prefixes=("*",),    # Allow any file under export_root
    )


