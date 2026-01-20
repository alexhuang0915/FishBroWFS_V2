from __future__ import annotations

from typing import Any


def select_build_manifest_filename(artifact_index: dict | list) -> str | None:
    """Select build_data_manifest.json from artifact index payload."""
    if isinstance(artifact_index, list):
        files = artifact_index
    else:
        files = artifact_index.get("artifacts") or artifact_index.get("files") or []
    for entry in files:
        if isinstance(entry, dict):
            filename = entry.get("filename")
        else:
            filename = None
        if filename and filename.endswith("build_data_manifest.json"):
            return filename
    return None


def parse_build_manifest(payload: dict[str, Any]) -> tuple[list[dict[str, Any]], str | None]:
    """Return inventory rows and produced_bars_path from manifest payload."""
    rows = payload.get("inventory_rows") or []
    if not isinstance(rows, list):
        rows = []
    produced_bars_path = payload.get("produced_bars_path")
    return rows, produced_bars_path
