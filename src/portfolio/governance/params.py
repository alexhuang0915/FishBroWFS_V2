"""
Load governance parameters from a JSON file (single source of truth).
"""
import json
import os
from pathlib import Path
from typing import Optional

from ..models.governance_models import GovernanceParams


# Default path relative to repo root
_DEFAULT_PATH = Path("configs/portfolio/governance_params.json")


def load_governance_params(path: Optional[str] = None) -> GovernanceParams:
    """
    Load governance parameters from a JSON file.

    Search order:
      1. Explicit `path` argument (if provided)
      2. Environment variable FISHBRO_PORTFOLIO_PARAMS
      3. Default path `configs/portfolio/governance_params.json`

    Raises FileNotFoundError if the file does not exist.
    Raises ValidationError if the JSON does not conform to GovernanceParams.
    """
    # Determine which file to load
    file_path: Optional[Path] = None
    if path is not None:
        file_path = Path(path)
    else:
        env_path = os.getenv("FISHBRO_PORTFOLIO_PARAMS")
        if env_path:
            file_path = Path(env_path)
        else:
            file_path = _DEFAULT_PATH

    # Resolve relative to repo root (current working directory)
    file_path = file_path.resolve()
    if not file_path.exists():
        raise FileNotFoundError(
            f"Governance parameters file not found: {file_path}\n"
            f"Please create it or set FISHBRO_PORTFOLIO_PARAMS environment variable."
        )

    # Load and parse
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Validate via Pydantic
    return GovernanceParams(**data)


def create_default_params_file(target_path: Optional[Path] = None) -> Path:
    """
    Write a default governance parameters JSON file.

    Useful for bootstrapping a new deployment.
    Returns the path written.
    """
    if target_path is None:
        target_path = _DEFAULT_PATH

    target_path.parent.mkdir(parents=True, exist_ok=True)

    default = GovernanceParams()
    # Convert to dict and then to JSON with sorted keys for readability
    data = default.model_dump(mode="json")
    with open(target_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, sort_keys=True)

    return target_path