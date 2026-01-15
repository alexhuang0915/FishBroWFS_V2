"""
Resolve WFS policy selectors into canonical YAML paths.
"""

from __future__ import annotations

from pathlib import Path
from typing import Mapping


_NAMED_POLICIES: Mapping[str, str] = {
    "default": "policy_v1_default.yaml",
    "red_team": "policy_v1_red_team.yaml",
}


def resolve_wfs_policy_selector(selector: str, *, repo_root: Path) -> Path:
    """
    Resolve a selector string into an absolute path under configs/strategies/wfs/.

    Args:
        selector: Policy selector string (name or filename).
        repo_root: Root directory of the repository.

    Returns:
        Absolute Path to the policy YAML file.

    Raises:
        ValueError: If the selector is invalid, unsafe, or the file does not exist.
    """
    if not selector or not isinstance(selector, str) or selector.strip() == "":
        raise ValueError("Policy selector must be a non-empty string.")

    if selector.startswith("/"):
        raise ValueError("Absolute paths are not allowed for policy selectors.")

    cleaned = Path(selector)
    if any(part in {".."} for part in cleaned.parts):
        raise ValueError("Path traversal is not allowed in policy selectors.")

    wfs_policy_dir = repo_root / "configs" / "strategies" / "wfs"
    if not wfs_policy_dir.exists():
        raise ValueError(f"WFS policy directory not found: {wfs_policy_dir}")

    candidate: Path | None = None
    if selector.endswith(".yaml"):
        candidate = wfs_policy_dir / selector
    else:
        mapped = _NAMED_POLICIES.get(selector)
        if mapped:
            candidate = wfs_policy_dir / mapped

    if candidate is None:
        raise ValueError(f"Unknown policy selector: {selector}")

    candidate_resolved = candidate.resolve()
    if not candidate_resolved.exists():
        raise ValueError(f"Policy file not found: {candidate_resolved}")

    if not candidate_resolved.is_relative_to(wfs_policy_dir.resolve()):
        raise ValueError("Resolved policy path is outside the WFS policy directory.")

    return candidate_resolved
