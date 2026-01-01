"""
Append‑only governance log and artifact writer.

All writes are deterministic and auditable. No overwriting of existing artifacts.
"""
import json
import hashlib
from pathlib import Path
from typing import Union, Optional
from datetime import datetime, timezone

from ..models.governance_models import BaseModel, GovernanceLogEvent


# ========== Path Utilities ==========

def governance_root() -> Path:
    """
    Return the root directory for governance outputs.
    Creates the directory if it does not exist.
    """
    root = Path("outputs/governance")
    root.mkdir(parents=True, exist_ok=True)
    return root


def artifacts_dir() -> Path:
    """Return the artifacts subdirectory (creates if missing)."""
    artifacts = governance_root() / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)
    return artifacts


def log_file() -> Path:
    """Return the path to the append‑only governance log."""
    return governance_root() / "governance_log.jsonl"


def now_utc_iso() -> str:
    """Return current UTC time as ISO‑8601 string."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ========== Artifact Writer ==========

def write_artifact_json(filename: str, obj: BaseModel) -> Path:
    """
    Write a JSON artifact under outputs/governance/artifacts/{filename}.

    If a file with the same name already exists and its content differs,
    the new file is saved with a suffix "-<shorthash>.json".

    Returns the actual Path written to.
    """
    artifacts = artifacts_dir()
    target = artifacts / filename

    # Serialize deterministically using json.dumps with sort_keys
    data = obj.model_dump(mode="json")
    content = json.dumps(data, indent=2, sort_keys=True)
    content_bytes = content.encode("utf-8")

    # If target exists, compare content
    if target.exists():
        existing = target.read_bytes()
        if existing == content_bytes:
            # Identical content – no need to write again
            return target
        else:
            # Different content – generate unique suffix
            h = hashlib.sha256(content_bytes).hexdigest()[:8]
            stem = target.stem
            suffix = f"-{h}"
            new_name = f"{stem}{suffix}{target.suffix}"
            target = artifacts / new_name

    # Write the file
    target.write_bytes(content_bytes)
    return target


# ========== Log Writer ==========

def append_governance_event(event: GovernanceLogEvent) -> Path:
    """
    Append a single GovernanceLogEvent as a JSON line to the governance log.

    The log file is opened in append mode; each line is newline‑terminated.
    Returns the path to the log file.
    """
    log_path = log_file()
    log_path.parent.mkdir(parents=True, exist_ok=True)
    line = event.model_dump_json() + "\n"
    with log_path.open("a", encoding="utf-8") as f:
        f.write(line)
    return log_path


# ========== Convenience Functions ==========

def write_and_log(
    event: GovernanceLogEvent,
    artifact_filename: Optional[str] = None,
    artifact_obj: Optional[BaseModel] = None,
) -> tuple[Path, Optional[Path]]:
    """
    Write an artifact (if provided) and append the log event.

    Returns (log_path, artifact_path).
    """
    artifact_path = None
    if artifact_filename is not None and artifact_obj is not None:
        artifact_path = write_artifact_json(artifact_filename, artifact_obj)
        event.attached_artifacts.append(str(artifact_path.relative_to(governance_root())))

    log_path = append_governance_event(event)
    return log_path, artifact_path