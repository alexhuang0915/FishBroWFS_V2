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

# 1. Feature Build Contract
# Root: outputs/shared/{season}/{dataset_id}
CONTRACT_FEATURE_BUILD = JobArtifactContract(
    job_type="BUILD_DATA",
    root_kind="shared_dir",
    required_paths=[
        ArtifactPathSpec("features", ArtifactKind.DIR_NONEMPTY, "Features directory (NPZ files)"),
        ArtifactPathSpec("features/features_manifest.json", ArtifactKind.FILE, "Features manifest")
    ]
)

# 2. Research Contract
# Root: outputs/seasons/{season}/{job_id}
CONTRACT_RESEARCH = JobArtifactContract(
    job_type="RUN_RESEARCH_V2",
    root_kind="run_dir",
    required_paths=[
        ArtifactPathSpec("manifest.json", ArtifactKind.FILE, "Job manifest"),
        ArtifactPathSpec("payload.json", ArtifactKind.FILE, "Input payload"),
        # Note: We check for EITHER plateau_candidates.json OR winners.json in logic if strictly needed,
        # but for contract we might enforce strictly or allowed fallback.
        # User spec says: "research/winners.json OR research/plateau_candidates.json"
        # Since this simple contract checks strict paths, complex OR logic might need handling in handler 
        # OR we define the "Primary" artifact here.
        # Let's enforce the most critical one for V2 research: winners.json was legacy, candidates is new.
        # Discoverty Notes says: "research/winners.json OR research/plateau_candidates.json"
        # We will require at least one of them by checking "research/" is non-empty for now?
        # Better: let's enforce `research/` is non-empty, and maybe specific files if possible.
        # Re-reading user spec: "Usage: research/winners.json (file, or winners_v2)"
        
        # User defined strictness:
        # "research/manifest.json"
        # "research/winners.json" (or equiv) at output root or subdir
        
        # Let's target the research subdirectory which should contain results.
         ArtifactPathSpec("research", ArtifactKind.DIR_NONEMPTY, "Research output directory")
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
    if job_type == "BUILD_DATA":
        if mode in ["FULL", "FEATURES_ONLY"]:
            return CONTRACT_FEATURE_BUILD
        # BARS_ONLY handled by separate logic or we can add CONTRACT_BARS here too
        return None
        
    if job_type == "RUN_RESEARCH_V2":
        return CONTRACT_RESEARCH
        
    if job_type == "RUN_PLATEAU_V2":
        return CONTRACT_PLATEAU
        
    return None
