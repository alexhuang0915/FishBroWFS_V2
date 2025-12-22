
"""Read-only loader for portfolio plan views with schema validation."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from FishBroWFS_V2.contracts.portfolio.plan_view_models import PortfolioPlanView


def load_plan_view_json(plan_dir: Path) -> PortfolioPlanView:
    """Read-only: load plan_view.json and validate schema.
    
    Args:
        plan_dir: Directory containing plan_view.json.
    
    Returns:
        Validated PortfolioPlanView instance.
    
    Raises:
        FileNotFoundError: If plan_view.json doesn't exist.
        ValueError: If JSON is invalid or schema validation fails.
    """
    view_path = plan_dir / "plan_view.json"
    if not view_path.exists():
        raise FileNotFoundError(f"plan_view.json not found in {plan_dir}")
    
    try:
        content = view_path.read_text(encoding="utf-8")
        data = json.loads(content)
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise ValueError(f"Invalid JSON in {view_path}: {e}")
    
    # Validate using Pydantic model
    try:
        return PortfolioPlanView.model_validate(data)
    except Exception as e:
        raise ValueError(f"Schema validation failed for {view_path}: {e}")


def load_plan_view_manifest(plan_dir: Path) -> Dict[str, Any]:
    """Load and parse plan_view_manifest.json.
    
    Args:
        plan_dir: Directory containing plan_view_manifest.json.
    
    Returns:
        Parsed manifest dict.
    
    Raises:
        FileNotFoundError: If manifest doesn't exist.
        ValueError: If JSON is invalid.
    """
    manifest_path = plan_dir / "plan_view_manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"plan_view_manifest.json not found in {plan_dir}")
    
    try:
        content = manifest_path.read_text(encoding="utf-8")
        return json.loads(content)
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise ValueError(f"Invalid JSON in {manifest_path}: {e}")


def load_plan_view_checksums(plan_dir: Path) -> Dict[str, str]:
    """Load and parse plan_view_checksums.json.
    
    Args:
        plan_dir: Directory containing plan_view_checksums.json.
    
    Returns:
        Dict mapping filename to SHA256 checksum.
    
    Raises:
        FileNotFoundError: If checksums file doesn't exist.
        ValueError: If JSON is invalid.
    """
    checksums_path = plan_dir / "plan_view_checksums.json"
    if not checksums_path.exists():
        raise FileNotFoundError(f"plan_view_checksums.json not found in {plan_dir}")
    
    try:
        content = checksums_path.read_text(encoding="utf-8")
        data = json.loads(content)
        if not isinstance(data, dict):
            raise ValueError("checksums file must be a JSON object")
        return data
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise ValueError(f"Invalid JSON in {checksums_path}: {e}")


def verify_view_integrity(plan_dir: Path) -> bool:
    """Verify integrity of plan view files using checksums.
    
    Args:
        plan_dir: Directory containing plan view files.
    
    Returns:
        True if all checksums match, False otherwise.
    
    Note:
        Returns False if any required file is missing.
    """
    try:
        checksums = load_plan_view_checksums(plan_dir)
    except FileNotFoundError:
        return False
    
    from FishBroWFS_V2.control.artifacts import compute_sha256
    
    for filename, expected_hash in checksums.items():
        file_path = plan_dir / filename
        if not file_path.exists():
            return False
        
        try:
            actual_hash = compute_sha256(file_path.read_bytes())
            if actual_hash != expected_hash:
                return False
        except OSError:
            return False
    
    return True


