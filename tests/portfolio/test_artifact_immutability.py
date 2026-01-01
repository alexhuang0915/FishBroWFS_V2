"""
Test artifact immutability (no overwriting) and append‑only log.
"""
import json
import pytest
from pathlib import Path
from unittest.mock import patch

from portfolio.models.governance_models import GovernanceParams, GovernanceLogEvent, ReasonCode
from portfolio.governance.governance_logging import (
    governance_root,
    write_artifact_json,
    append_governance_event,
)


@pytest.fixture
def tmp_governance_root(tmp_path):
    with patch("portfolio.governance.governance_logging.governance_root") as mock_root:
        mock_root.return_value = tmp_path / "governance"
        yield mock_root


class TestArtifactImmutability:
    def test_write_artifact_does_not_overwrite_if_different(self, tmp_governance_root):
        """If same filename but different content, a new file with hash suffix is created."""
        root = tmp_governance_root.return_value
        artifacts_dir = root / "artifacts"
        artifacts_dir.mkdir(parents=True, exist_ok=True)

        # First artifact
        obj1 = GovernanceParams(corr_portfolio_hard_limit=0.7)
        path1 = write_artifact_json("test.json", obj1)
        assert path1.name == "test.json"
        assert path1.exists()

        # Second artifact with different content
        obj2 = GovernanceParams(corr_portfolio_hard_limit=0.8)
        path2 = write_artifact_json("test.json", obj2)
        assert path2 != path1
        assert path2.name.startswith("test-")
        assert path2.name.endswith(".json")
        assert path2.exists()

        # Original file unchanged
        content1 = json.loads(path1.read_text())
        assert content1["corr_portfolio_hard_limit"] == 0.7
        content2 = json.loads(path2.read_text())
        assert content2["corr_portfolio_hard_limit"] == 0.8

    def test_write_artifact_identical_content_no_new_file(self, tmp_governance_root):
        """If same filename and identical content, returns same path."""
        root = tmp_governance_root.return_value
        artifacts_dir = root / "artifacts"
        artifacts_dir.mkdir(parents=True, exist_ok=True)

        obj = GovernanceParams()
        path1 = write_artifact_json("same.json", obj)
        path2 = write_artifact_json("same.json", obj)  # identical content
        assert path2 == path1
        # Ensure only one file exists
        files = list(artifacts_dir.glob("same*.json"))
        assert len(files) == 1

    def test_append_only_log(self, tmp_governance_root):
        """Governance log is append‑only; existing lines are never modified."""
        root = tmp_governance_root.return_value
        log_file = root / "governance_log.jsonl"
        assert not log_file.exists()

        # Write first event
        event1 = GovernanceLogEvent(
            timestamp_utc="2026-01-01T00:00:00Z",
            actor="test",
            strategy_key="key1",
            from_state=None,
            to_state=None,
            reason_code=ReasonCode.PROMOTE_TO_PAPER,
            attached_artifacts=[],
            data_fingerprint=None,
            extra={},
        )
        append_governance_event(event1)
        lines1 = log_file.read_text().splitlines()
        assert len(lines1) == 1

        # Write second event
        event2 = GovernanceLogEvent(
            timestamp_utc="2026-01-01T00:01:00Z",
            actor="test",
            strategy_key="key2",
            from_state=None,
            to_state=None,
            reason_code=ReasonCode.PROMOTE_TO_LIVE,
            attached_artifacts=[],
            data_fingerprint=None,
            extra={},
        )
        append_governance_event(event2)
        lines2 = log_file.read_text().splitlines()
        assert len(lines2) == 2
        assert lines2[0] == lines1[0]  # first line unchanged

        # Verify content
        data1 = json.loads(lines2[0])
        assert data1["reason_code"] == "PROMOTE_TO_PAPER"
        data2 = json.loads(lines2[1])
        assert data2["reason_code"] == "PROMOTE_TO_LIVE"

    def test_log_file_never_truncated(self, tmp_governance_root):
        """Opening log in append mode ensures previous content stays."""
        root = tmp_governance_root.return_value
        log_file = root / "governance_log.jsonl"
        # Manually write something
        log_file.parent.mkdir(parents=True, exist_ok=True)
        log_file.write_text("existing line\n")

        # Append via governance function
        event = GovernanceLogEvent(
            timestamp_utc="2026-01-01T00:00:00Z",
            actor="test",
            strategy_key="key",
            from_state=None,
            to_state=None,
            reason_code=ReasonCode.PROMOTE_TO_PAPER,
            attached_artifacts=[],
            data_fingerprint=None,
            extra={},
        )
        append_governance_event(event)

        lines = log_file.read_text().splitlines()
        assert len(lines) == 2
        assert lines[0] == "existing line"
        assert "PROMOTE_TO_PAPER" in lines[1]