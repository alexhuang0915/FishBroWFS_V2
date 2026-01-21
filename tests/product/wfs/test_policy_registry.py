from pathlib import Path

from wfs.policy_registry import list_wfs_policies


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def test_policy_registry_includes_default_and_red_team():
    entries = list_wfs_policies(repo_root=_repo_root())
    selectors = [entry.selector for entry in entries]
    assert "default" in selectors
    assert "red_team" in selectors
    hash_prefixes = [entry.hash for entry in entries]
    assert all(h.startswith("sha256:") for h in hash_prefixes)
    wfs_dir = (_repo_root() / "configs" / "strategies" / "wfs").resolve()
    for entry in entries:
        resolved = Path(entry.resolved_source).resolve()
        assert resolved.is_relative_to(wfs_dir)
