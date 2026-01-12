"""Input Manifest Generation for Job Auditability.

Generates comprehensive input manifests for job submissions, capturing:
- Dataset information (ID, kind)
- TXT file signatures and status
- Parquet file signatures and status
- Build timestamps
- System snapshot at time of job submission
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional
import hashlib

from control.dataset_descriptor import get_descriptor
from control.utils import compute_file_signature, get_system_snapshot


@dataclass
class FileManifest:
    """Manifest for a single file."""
    path: str
    exists: bool
    size_bytes: int = 0
    mtime_utc: Optional[str] = None
    signature: str = ""
    error: Optional[str] = None


@dataclass
class DatasetManifest:
    """Manifest for a dataset with TXT and Parquet information."""
    # Required fields (no defaults) first
    dataset_id: str
    kind: str
    txt_root: str
    parquet_root: str
    
    # Optional fields with defaults
    txt_files: List[FileManifest] = field(default_factory=list)
    txt_present: bool = False
    txt_total_size_bytes: int = 0
    txt_signature_aggregate: str = ""
    parquet_files: List[FileManifest] = field(default_factory=list)
    parquet_present: bool = False
    parquet_total_size_bytes: int = 0
    parquet_signature_aggregate: str = ""
    up_to_date: bool = False
    bars_count: Optional[int] = None
    schema_ok: Optional[bool] = None
    error: Optional[str] = None


@dataclass
class InputManifest:
    """Complete input manifest for a job submission."""
    # Metadata
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"))
    job_id: Optional[str] = None
    season: str = ""
    
    # Configuration
    config_snapshot: Dict[str, Any] = field(default_factory=dict)
    
    # Data manifests
    data1_manifest: Optional[DatasetManifest] = None
    data2_manifest: Optional[DatasetManifest] = None
    
    # System snapshot (summary)
    system_snapshot_summary: Dict[str, Any] = field(default_factory=dict)
    
    # Audit trail
    manifest_hash: str = ""
    previous_manifest_hash: Optional[str] = None


def create_file_manifest(file_path: str) -> FileManifest:
    """Create manifest for a single file."""
    try:
        p = Path(file_path)
        exists = p.exists()
        
        if not exists:
            return FileManifest(
                path=file_path,
                exists=False,
                size_bytes=0,
                mtime_utc=None,
                signature="",
                error="File not found"
            )
        
        st = p.stat()
        mtime_utc = datetime.fromtimestamp(st.st_mtime, datetime.timezone.utc).isoformat().replace("+00:00", "Z")
        signature = compute_file_signature(p)
        
        return FileManifest(
            path=file_path,
            exists=True,
            size_bytes=int(st.st_size),
            mtime_utc=mtime_utc,
            signature=signature,
            error=""
        )
    except Exception as e:
        return FileManifest(
            path=file_path,
            exists=False,
            size_bytes=0,
            mtime_utc=None,
            signature="",
            error=str(e)
        )


def create_dataset_manifest(dataset_id: str) -> DatasetManifest:
    """Create manifest for a dataset."""
    try:
        descriptor = get_descriptor(dataset_id)
        if descriptor is None:
            return DatasetManifest(
                dataset_id=dataset_id,
                kind="unknown",
                txt_root="",
                parquet_root="",
                error=f"Dataset not found: {dataset_id}"
            )
        
        # Process TXT files
        txt_files = []
        txt_present = True
        txt_total_size = 0
        txt_signatures = []
        
        for txt_path_str in descriptor.txt_required_paths:
            file_manifest = create_file_manifest(txt_path_str)
            txt_files.append(file_manifest)
            
            if not file_manifest.exists:
                txt_present = False
            else:
                txt_total_size += file_manifest.size_bytes
                txt_signatures.append(file_manifest.signature)
        
        # Process Parquet files
        parquet_files = []
        parquet_present = True
        parquet_total_size = 0
        parquet_signatures = []
        
        for parquet_path_str in descriptor.parquet_expected_paths:
            file_manifest = create_file_manifest(parquet_path_str)
            parquet_files.append(file_manifest)
            
            if not file_manifest.exists:
                parquet_present = False
            else:
                parquet_total_size += file_manifest.size_bytes
                parquet_signatures.append(file_manifest.signature)
        
        # Determine up-to-date status
        up_to_date = txt_present and parquet_present
        # Simple heuristic: if both present, assume up-to-date
        # In a real implementation, this would compare timestamps or content hashes
        
        # Try to get bars count from Parquet if available
        bars_count = None
        schema_ok = None
        
        if parquet_present and descriptor.parquet_expected_paths:
            try:
                parquet_path = Path(descriptor.parquet_expected_paths[0])
                if parquet_path.exists():
                    # Quick schema check
                    import pandas as pd
                    df_sample = pd.read_parquet(parquet_path, nrows=1)
                    schema_ok = True
                    
                    # Try to get row count for small files
                    if parquet_path.stat().st_size < 1000000:  # < 1MB
                        df = pd.read_parquet(parquet_path)
                        # Use df.shape[0] or len(df.index) instead of len(df)
                        if hasattr(df, 'shape') and len(df.shape) >= 1:
                            bars_count = df.shape[0]
                        elif hasattr(df, 'index'):
                            bars_count = len(df.index)
                        else:
                            bars_count = len(df)  # fallback
            except Exception:
                schema_ok = False
        
        return DatasetManifest(
            dataset_id=dataset_id,
            kind=descriptor.kind,
            txt_root=descriptor.txt_root,
            txt_files=txt_files,
            txt_present=txt_present,
            txt_total_size_bytes=txt_total_size,
            txt_signature_aggregate="|".join(txt_signatures) if txt_signatures else "none",
            parquet_root=descriptor.parquet_root,
            parquet_files=parquet_files,
            parquet_present=parquet_present,
            parquet_total_size_bytes=parquet_total_size,
            parquet_signature_aggregate="|".join(parquet_signatures) if parquet_signatures else "none",
            up_to_date=up_to_date,
            bars_count=bars_count,
            schema_ok=schema_ok
        )
    except Exception as e:
        return DatasetManifest(
            dataset_id=dataset_id,
            kind="unknown",
            txt_root="",
            parquet_root="",
            error=str(e)
        )


def create_input_manifest(
    job_id: Optional[str],
    season: str,
    config_snapshot: Dict[str, Any],
    data1_dataset_id: str,
    data2_dataset_id: Optional[str] = None,
    previous_manifest_hash: Optional[str] = None
) -> InputManifest:
    """Create complete input manifest for a job submission.
    
    Args:
        job_id: Job ID (if available)
        season: Season identifier
        config_snapshot: Configuration snapshot from make_config_snapshot
        data1_dataset_id: DATA1 dataset ID
        data2_dataset_id: Optional DATA2 dataset ID
        previous_manifest_hash: Optional hash of previous manifest (for chain)
        
    Returns:
        InputManifest with all audit information
    """
    # Create dataset manifests
    data1_manifest = create_dataset_manifest(data1_dataset_id)
    
    data2_manifest = None
    if data2_dataset_id:
        data2_manifest = create_dataset_manifest(data2_dataset_id)
    
    # Get system snapshot summary
    system_snapshot = get_system_snapshot()
    snapshot_summary = {
        "created_at": system_snapshot.created_at.isoformat(),
        "total_datasets": system_snapshot.total_datasets,
        "total_strategies": system_snapshot.total_strategies,
        "notes": system_snapshot.notes[:5],  # First 5 notes
        "error_count": len(system_snapshot.errors)
    }
    
    # Create manifest
    manifest = InputManifest(
        job_id=job_id,
        season=season,
        config_snapshot=config_snapshot,
        data1_manifest=data1_manifest,
        data2_manifest=data2_manifest,
        system_snapshot_summary=snapshot_summary,
        previous_manifest_hash=previous_manifest_hash
    )
    
    # Compute manifest hash
    manifest_dict = asdict(manifest)
    # Remove hash field before computing hash
    manifest_dict.pop("manifest_hash", None)
    
    # Convert to JSON and compute hash
    manifest_json = json.dumps(manifest_dict, sort_keys=True, separators=(',', ':'))
    manifest_hash = hashlib.sha256(manifest_json.encode('utf-8')).hexdigest()[:32]
    
    manifest.manifest_hash = manifest_hash
    
    return manifest


def write_input_manifest(
    manifest: InputManifest,
    output_path: Path
) -> bool:
    """Write input manifest to file.
    
    Args:
        manifest: InputManifest to write
        output_path: Path to write manifest JSON file
        
    Returns:
        True if successful, False otherwise
    """
    try:
        # Ensure parent directory exists
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Convert to dictionary
        manifest_dict = asdict(manifest)
        
        # Write JSON
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(manifest_dict, f, indent=2, ensure_ascii=False)
        
        return True
    except Exception as e:
        print(f"Error writing input manifest: {e}")
        return False


def read_input_manifest(input_path: Path) -> Optional[InputManifest]:
    """Read input manifest from file.
    
    Args:
        input_path: Path to manifest JSON file
        
    Returns:
        InputManifest if successful, None otherwise
    """
    try:
        with open(input_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Reconstruct nested objects
        if data.get('data1_manifest'):
            data1_dict = data['data1_manifest']
            data['data1_manifest'] = DatasetManifest(**data1_dict)
        
        if data.get('data2_manifest'):
            data2_dict = data['data2_manifest']
            data['data2_manifest'] = DatasetManifest(**data2_dict)
        
        return InputManifest(**data)
    except Exception as e:
        print(f"Error reading input manifest: {e}")
        return None


def verify_input_manifest(manifest: InputManifest) -> Dict[str, Any]:
    """Verify input manifest integrity and completeness.
    
    Args:
        manifest: InputManifest to verify
        
    Returns:
        Dictionary with verification results
    """
    results = {
        "valid": True,
        "errors": [],
        "warnings": [],
        "checks": []
    }
    
    # Check timestamp first (warnings)
    try:
        created_at = datetime.fromisoformat(manifest.created_at.replace('Z', '+00:00'))
        age_hours = (datetime.now(timezone.utc) - created_at).total_seconds() / 3600
        if age_hours > 24:
            results["warnings"].append(f"Manifest is {age_hours:.1f} hours old")
    except Exception:
        results["warnings"].append("Invalid timestamp format")
    
    # Check DATA1 manifest (structural errors before hash)
    if not manifest.data1_manifest:
        results["errors"].append("Missing DATA1 manifest")
        results["valid"] = False
    else:
        if not manifest.data1_manifest.txt_present:
            results["warnings"].append(f"DATA1 dataset {manifest.data1_manifest.dataset_id} missing TXT files")
        
        if not manifest.data1_manifest.parquet_present:
            results["warnings"].append(f"DATA1 dataset {manifest.data1_manifest.dataset_id} missing Parquet files")
        
        if manifest.data1_manifest.error:
            results["warnings"].append(f"DATA1 dataset error: {manifest.data1_manifest.error}")
    
    # Check DATA2 manifest if present
    if manifest.data2_manifest:
        if not manifest.data2_manifest.txt_present:
            results["warnings"].append(f"DATA2 dataset {manifest.data2_manifest.dataset_id} missing TXT files")
        
        if not manifest.data2_manifest.parquet_present:
            results["warnings"].append(f"DATA2 dataset {manifest.data2_manifest.dataset_id} missing Parquet files")
        
        if manifest.data2_manifest.error:
            results["warnings"].append(f"DATA2 dataset error: {manifest.data2_manifest.error}")
    
    # Check system snapshot
    if not manifest.system_snapshot_summary:
        results["warnings"].append("System snapshot summary is empty")
    
    # Check manifest hash (after structural checks)
    manifest_dict = asdict(manifest)
    original_hash = manifest_dict.pop("manifest_hash", None)
    
    manifest_json = json.dumps(manifest_dict, sort_keys=True, separators=(',', ':'))
    computed_hash = hashlib.sha256(manifest_json.encode('utf-8')).hexdigest()[:32]
    
    if original_hash != computed_hash:
        results["valid"] = False
        results["errors"].append(f"Manifest hash mismatch: expected {original_hash}, got {computed_hash}")
    else:
        results["checks"].append("Manifest hash verified")
    
    return results