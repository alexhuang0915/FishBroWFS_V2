from pathlib import Path

import pytest

from wfs.policy_resolver import resolve_wfs_policy_selector


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def test_resolver_returns_default_policy_by_name():
    path = resolve_wfs_policy_selector("default", repo_root=_repo_root())
    assert path.name == "policy_v1_default.yaml"
    assert path.exists()


def test_resolver_accepts_filename():
    path = resolve_wfs_policy_selector("policy_v1_red_team.yaml", repo_root=_repo_root())
    assert path.name == "policy_v1_red_team.yaml"
    assert path.exists()


@pytest.mark.parametrize("selector", ["/etc/passwd", "../policy_v1_default.yaml", "unknown"])
def test_resolver_rejects_invalid_selectors(selector):
    with pytest.raises(ValueError):
        resolve_wfs_policy_selector(selector, repo_root=_repo_root())
