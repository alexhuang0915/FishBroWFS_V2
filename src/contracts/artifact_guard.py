from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import List, Optional, Literal

class ArtifactKind(Enum):
    FILE = "file"
    DIR_NONEMPTY = "dir_nonempty"

@dataclass
class ArtifactPathSpec:
    relative_path: str
    kind: ArtifactKind
    description: str = ""

@dataclass
class JobArtifactContract:
    job_type: str
    required_paths: List[ArtifactPathSpec]
    root_kind: Literal["run_dir", "shared_dir"] = "run_dir" # 'run_dir' implies job's allocated output dir

def assert_artifacts_present(root: Path, contract: JobArtifactContract) -> List[str]:
    """
    Asserts that all required artifacts in the contract are present in the root directory.
    Returns a list of missing artifact descriptions (empty if all present).
    """
    missing = []
    
    if not root.exists():
        return [f"Root directory does not exist: {root}"]

    for spec in contract.required_paths:
        path = root / spec.relative_path
        
        if spec.kind == ArtifactKind.FILE:
            if not path.is_file():
                missing.append(f"Missing file: {spec.relative_path}")
        elif spec.kind == ArtifactKind.DIR_NONEMPTY:
            if not path.is_dir():
                 missing.append(f"Missing directory: {spec.relative_path}")
            else:
                 # Check if directory is not empty
                 try:
                     if not any(path.iterdir()):
                         missing.append(f"Directory is empty: {spec.relative_path}")
                 except Exception as e:
                     missing.append(f"Failed to access directory {spec.relative_path}: {e}")
    
    return missing

# --- SSOT Registry of Contracts ---

# Bars Build Contract
# Root: cache/shared/{season}/{dataset_id}
CONTRACT_BARS_BUILD = JobArtifactContract(
    job_type="BUILD_BARS",
    root_kind="shared_dir",
    required_paths=[
        ArtifactPathSpec("bars", ArtifactKind.DIR_NONEMPTY, "Bars directory (NPZ files)"),
        ArtifactPathSpec("bars/bars_manifest.json", ArtifactKind.FILE, "Bars manifest"),
    ],
)

# Features Build Contract
# Root: cache/shared/{season}/{dataset_id}
CONTRACT_FEATURES_BUILD = JobArtifactContract(
    job_type="BUILD_FEATURES",
    root_kind="shared_dir",
    required_paths=[
        ArtifactPathSpec("features", ArtifactKind.DIR_NONEMPTY, "Features directory (NPZ files)"),
        ArtifactPathSpec("features/features_manifest.json", ArtifactKind.FILE, "Features manifest")
    ]
)

# 3. Plateau Contract
# Root: outputs/seasons/{season}/{research_run_id}/plateau
CONTRACT_PLATEAU = JobArtifactContract(
    job_type="RUN_PLATEAU_V2",
    root_kind="run_dir",
    required_paths=[
         ArtifactPathSpec("manifest.json", ArtifactKind.FILE, "Plateau manifest"),
         # We found plateau_report.json or similar in discovery
         ArtifactPathSpec("plateau_report.json", ArtifactKind.FILE, "Plateau report file")
    ]
)

def get_contract_for_job(job_type: str, mode: str = "FULL") -> Optional[JobArtifactContract]:
    if job_type == "BUILD_BARS":
        return CONTRACT_BARS_BUILD

    if job_type == "BUILD_FEATURES":
        return CONTRACT_FEATURES_BUILD

    if job_type == "BUILD_DATA":
        if mode in ["FULL", "FEATURES_ONLY"]:
            return CONTRACT_FEATURES_BUILD
        if mode in ["BARS_ONLY"]:
            return CONTRACT_BARS_BUILD
        return None
        
    if job_type == "RUN_PLATEAU_V2":
        return CONTRACT_PLATEAU
        
    return None
