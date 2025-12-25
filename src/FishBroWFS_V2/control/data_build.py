"""TXT to Parquet Build Pipeline.

Provides deterministic conversion of raw TXT files to Parquet format
for backtest performance and schema stability.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any
import pandas as pd

from FishBroWFS_V2.data.raw_ingest import ingest_raw_txt, RawIngestResult


@dataclass(frozen=True)
class BuildParquetRequest:
    """Request to build Parquet from TXT."""
    dataset_id: str
    force: bool               # rebuild even if up-to-date
    deep_validate: bool       # optional schema validation after build
    reason: str               # for audit/logging


@dataclass(frozen=True)
class BuildParquetResult:
    """Result of Parquet build operation."""
    ok: bool
    dataset_id: str
    started_utc: str
    finished_utc: str
    txt_signature: str
    parquet_signature: str
    parquet_paths: List[str]
    rows_written: Optional[int]
    notes: List[str]
    error: Optional[str]


def _compute_file_signature(file_path: Path, max_size_mb: int = 50) -> str:
    """Compute signature for a file.
    
    For small files (< max_size_mb): compute sha256
    For large files: use stat-hash (path + size + mtime)
    """
    try:
        if not file_path.exists():
            return "missing"
        
        stat = file_path.stat()
        file_size_mb = stat.st_size / (1024 * 1024)
        
        if file_size_mb < max_size_mb:
            # Small file: compute actual hash
            hasher = hashlib.sha256()
            with open(file_path, 'rb') as f:
                # Read in chunks to handle large files
                chunk_size = 8192
                while chunk := f.read(chunk_size):
                    hasher.update(chunk)
            return f"sha256:{hasher.hexdigest()[:16]}"
        else:
            # Large file: use stat-hash
            return f"stat:{file_path.name}:{stat.st_size}:{stat.st_mtime}"
    except Exception as e:
        return f"error:{str(e)[:50]}"


def _get_txt_files_for_dataset(dataset_id: str) -> List[Path]:
    """Get TXT files required for a dataset.
    
    This is a placeholder implementation. In a real system, this would
    look up the dataset descriptor to find TXT source paths.
    
    For now, we'll use a simple mapping based on dataset ID pattern.
    """
    # Simple mapping: dataset_id -> txt file pattern
    # In a real implementation, this would come from dataset registry
    base_dir = Path("data/raw")
    
    # Extract symbol from dataset_id (simplified)
    parts = dataset_id.split('_')
    if len(parts) >= 2 and '.' in parts[0]:
        symbol = parts[0].split('.')[1]  # e.g., "CME.MNQ" -> "MNQ"
    else:
        symbol = "unknown"
    
    # Look for TXT files
    txt_files = []
    if base_dir.exists():
        for txt_path in base_dir.glob(f"**/*{symbol}*.txt"):
            txt_files.append(txt_path)
    
    # If no files found, create a dummy path for testing
    if not txt_files:
        dummy_path = base_dir / f"{dataset_id}.txt"
        txt_files.append(dummy_path)
    
    return txt_files


def _get_parquet_output_path(dataset_id: str) -> Path:
    """Get output path for Parquet files.
    
    Deterministic output paths inside dataset-managed folder.
    """
    # Create parquet directory structure
    parquet_root = Path("outputs/parquet")
    
    # Clean dataset_id for filesystem
    safe_id = dataset_id.replace('/', '_').replace('\\', '_').replace(':', '_')
    
    # Create partitioned structure: parquet/<dataset_id>/data.parquet
    output_dir = parquet_root / safe_id
    output_dir.mkdir(parents=True, exist_ok=True)
    
    return output_dir / "data.parquet"


def _build_parquet_from_txt_impl(
    txt_files: List[Path],
    parquet_path: Path,
    force: bool,
    deep_validate: bool
) -> BuildParquetResult:
    """Core implementation of TXT to Parquet conversion."""
    started_utc = datetime.utcnow().isoformat() + "Z"
    notes = []
    
    try:
        # 1. Check if TXT files exist
        missing_txt = [str(p) for p in txt_files if not p.exists()]
        if missing_txt:
            return BuildParquetResult(
                ok=False,
                dataset_id="unknown",
                started_utc=started_utc,
                finished_utc=datetime.utcnow().isoformat() + "Z",
                txt_signature="",
                parquet_signature="",
                parquet_paths=[],
                rows_written=None,
                notes=notes,
                error=f"Missing TXT files: {missing_txt}"
            )
        
        # 2. Compute TXT signature
        txt_signatures = []
        for txt_file in txt_files:
            sig = _compute_file_signature(txt_file)
            txt_signatures.append(f"{txt_file.name}:{sig}")
        txt_signature = "|".join(txt_signatures)
        
        # 3. Check if Parquet already exists and is up-to-date
        parquet_exists = parquet_path.exists()
        parquet_signature = ""
        
        if parquet_exists:
            parquet_signature = _compute_file_signature(parquet_path)
            # Simple up-to-date check: compare signatures
            # In a real implementation, this would compare metadata
            if not force:
                # Check if we should skip rebuild
                notes.append(f"Parquet exists at {parquet_path}")
                # For now, we'll always rebuild if force=False but parquet exists
                # In a real system, we'd compare content hashes
        
        # 4. Ingest TXT files
        all_dfs = []
        for txt_file in txt_files:
            try:
                result: RawIngestResult = ingest_raw_txt(txt_file)
                df = result.df
                
                # Convert ts_str to datetime
                df['timestamp'] = pd.to_datetime(df['ts_str'], format='%Y/%m/%d %H:%M:%S', errors='coerce')
                df = df.drop(columns=['ts_str'])
                
                # Reorder columns
                df = df[['timestamp', 'open', 'high', 'low', 'close', 'volume']]
                
                all_dfs.append(df)
                notes.append(f"Ingested {txt_file.name}: {len(df)} rows")
            except Exception as e:
                return BuildParquetResult(
                    ok=False,
                    dataset_id="unknown",
                    started_utc=started_utc,
                    finished_utc=datetime.utcnow().isoformat() + "Z",
                    txt_signature=txt_signature,
                    parquet_signature=parquet_signature,
                    parquet_paths=[],
                    rows_written=None,
                    notes=notes,
                    error=f"Failed to ingest {txt_file}: {e}"
                )
        
        # 5. Combine DataFrames
        if not all_dfs:
            return BuildParquetResult(
                ok=False,
                dataset_id="unknown",
                started_utc=started_utc,
                finished_utc=datetime.utcnow().isoformat() + "Z",
                txt_signature=txt_signature,
                parquet_signature=parquet_signature,
                parquet_paths=[],
                rows_written=None,
                notes=notes,
                error="No data ingested from TXT files"
            )
        
        combined_df = pd.concat(all_dfs, ignore_index=True)
        
        # 6. Sort by timestamp
        combined_df = combined_df.sort_values('timestamp')
        
        # 7. Write to Parquet with atomic safety
        temp_dir = tempfile.mkdtemp(prefix="parquet_build_")
        try:
            temp_path = Path(temp_dir) / "temp.parquet"
            combined_df.to_parquet(
                temp_path,
                engine='pyarrow',
                compression='snappy',
                index=False
            )
            
            # Atomic rename
            parquet_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(temp_path), str(parquet_path))
            
            notes.append(f"Written Parquet to {parquet_path}")
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)
        
        # 8. Compute new Parquet signature
        new_parquet_signature = _compute_file_signature(parquet_path)
        
        # 9. Deep validation if requested
        if deep_validate:
            try:
                # Read back and validate schema
                validate_df = pd.read_parquet(parquet_path)
                expected_cols = ['timestamp', 'open', 'high', 'low', 'close', 'volume']
                if list(validate_df.columns) != expected_cols:
                    notes.append(f"Warning: Schema mismatch. Expected {expected_cols}, got {list(validate_df.columns)}")
                else:
                    notes.append("Deep validation passed")
            except Exception as e:
                notes.append(f"Deep validation warning: {e}")
        
        finished_utc = datetime.utcnow().isoformat() + "Z"
        
        return BuildParquetResult(
            ok=True,
            dataset_id="unknown",
            started_utc=started_utc,
            finished_utc=finished_utc,
            txt_signature=txt_signature,
            parquet_signature=new_parquet_signature,
            parquet_paths=[str(parquet_path)],
            rows_written=len(combined_df),
            notes=notes,
            error=None
        )
        
    except Exception as e:
        finished_utc = datetime.utcnow().isoformat() + "Z"
        return BuildParquetResult(
            ok=False,
            dataset_id="unknown",
            started_utc=started_utc,
            finished_utc=finished_utc,
            txt_signature="",
            parquet_signature="",
            parquet_paths=[],
            rows_written=None,
            notes=notes,
            error=f"Build failed: {e}"
        )


def build_parquet_from_txt(req: BuildParquetRequest) -> BuildParquetResult:
    """Convert raw TXT to Parquet for the given dataset_id.
    
    Requirements:
    - Deterministic output paths inside dataset-managed folder
    - Safe atomic writes: write to temp then rename
    - Up-to-date logic:
        - compute txt_signature (stat-hash or partial hash) from required TXT files
        - compute existing parquet_signature (from parquet files or metadata)
        - if not force and signatures match => no-op but ok=True
    - Must never mutate season artifacts.
    """
    # Get TXT files for dataset
    txt_files = _get_txt_files_for_dataset(req.dataset_id)
    
    # Get output path
    parquet_path = _get_parquet_output_path(req.dataset_id)
    
    # Update result with actual dataset_id
    result = _build_parquet_from_txt_impl(txt_files, parquet_path, req.force, req.deep_validate)
    
    # Create a new result with the correct dataset_id
    return BuildParquetResult(
        ok=result.ok,
        dataset_id=req.dataset_id,
        started_utc=result.started_utc,
        finished_utc=result.finished_utc,
        txt_signature=result.txt_signature,
        parquet_signature=result.parquet_signature,
        parquet_paths=result.parquet_paths,
        rows_written=result.rows_written,
        notes=result.notes,
        error=result.error
    )


# Simple test function
def test_build_parquet() -> None:
    """Test the build_parquet_from_txt function."""
    print("Testing build_parquet_from_txt...")
    
    # Create a dummy request
    req = BuildParquetRequest(
        dataset_id="test_dataset",
        force=True,
        deep_validate=False,
        reason="test"
    )
    
    result = build_parquet_from_txt(req)
    print(f"Result: {result.ok}")
    print(f"Notes: {result.notes}")
    if result.error:
        print(f"Error: {result.error}")


if __name__ == "__main__":
    test_build_parquet()