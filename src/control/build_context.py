from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional, Literal


BuildMode = Literal["FULL", "INCREMENTAL"]


@dataclass(frozen=True, slots=True)
class BuildContext:
    """
    Contract-only build context.

    Rules:
    - resolver / runner 不得自行尋找 txt
    - txt_path 必須由 caller 提供
    - 不做任何 filesystem 掃描
    """

    txt_path: Path
    mode: BuildMode
    outputs_root: Path
    build_bars_if_missing: bool = False

    season: str = ""
    dataset_id: str = ""
    strategy_id: str = ""
    config_snapshot: Optional[dict[str, Any]] = None
    config_hash: str = ""
    created_by: str = "b5c"
    data_fingerprint_sha1: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "txt_path", Path(self.txt_path))
        object.__setattr__(self, "outputs_root", Path(self.outputs_root))

        if self.mode not in ("FULL", "INCREMENTAL"):
            raise ValueError(f"Invalid mode: {self.mode}")

        if not self.txt_path.exists():
            raise FileNotFoundError(f"txt_path 不存在: {self.txt_path}")

        if self.txt_path.suffix.lower() != ".txt":
            raise ValueError("txt_path must be a .txt file")

    def ensure_config_snapshot(self) -> dict[str, Any]:
        return self.config_snapshot or {}

    def to_build_shared_kwargs(self) -> dict[str, Any]:
        """Return kwargs suitable for build_shared."""
        return {
            "txt_path": self.txt_path,
            "mode": self.mode,
            "outputs_root": self.outputs_root,
            "save_fingerprint": True,
            "generated_at_utc": None,
            "build_bars": self.build_bars_if_missing,
            "build_features": False,  # will be overridden by caller
            "feature_registry": None,
            "tfs": [15, 30, 60, 120, 240],
        }
