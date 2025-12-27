"""Dataset Descriptor with TXT and Parquet locations.

Extends the basic DatasetRecord with information about
raw TXT sources and derived Parquet outputs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Dict, Any

from data.dataset_registry import DatasetRecord


@dataclass(frozen=True)
class DatasetDescriptor:
    """Extended dataset descriptor with TXT and Parquet information."""
    
    # Core dataset info
    dataset_id: str
    base_record: DatasetRecord
    
    # TXT source information
    txt_root: str
    txt_required_paths: List[str]
    
    # Parquet output information
    parquet_root: str
    parquet_expected_paths: List[str]
    
    # Metadata
    kind: str = "unknown"
    notes: List[str] = field(default_factory=list)
    
    @property
    def symbol(self) -> str:
        """Get symbol from base record."""
        return self.base_record.symbol
    
    @property
    def exchange(self) -> str:
        """Get exchange from base record."""
        return self.base_record.exchange
    
    @property
    def timeframe(self) -> str:
        """Get timeframe from base record."""
        return self.base_record.timeframe
    
    @property
    def path(self) -> str:
        """Get path from base record."""
        return self.base_record.path
    
    @property
    def start_date(self) -> str:
        """Get start date from base record."""
        return self.base_record.start_date.isoformat()
    
    @property
    def end_date(self) -> str:
        """Get end date from base record."""
        return self.base_record.end_date.isoformat()


def create_descriptor_from_record(record: DatasetRecord) -> DatasetDescriptor:
    """Create a DatasetDescriptor from a DatasetRecord.
    
    This is a placeholder implementation that infers TXT and Parquet
    paths based on the dataset ID and record information.
    
    In a real system, this would come from a configuration file or
    database lookup.
    """
    dataset_id = record.id
    
    # Infer TXT root and paths based on dataset ID pattern
    # Example: "CME.MNQ.60m.2020-2024" -> data/raw/CME/MNQ/*.txt
    parts = dataset_id.split('.')
    if len(parts) >= 2:
        exchange = parts[0]
        symbol = parts[1]
        txt_root = f"data/raw/{exchange}/{symbol}"
        txt_required_paths = [
            f"{txt_root}/daily.txt",
            f"{txt_root}/intraday.txt"
        ]
    else:
        txt_root = f"data/raw/{dataset_id}"
        txt_required_paths = [f"{txt_root}/data.txt"]
    
    # Parquet output paths
    # Use outputs/parquet/<dataset_id>/data.parquet
    safe_id = dataset_id.replace('/', '_').replace('\\', '_').replace(':', '_')
    parquet_root = f"outputs/parquet/{safe_id}"
    parquet_expected_paths = [
        f"{parquet_root}/data.parquet"
    ]
    
    # Determine kind based on timeframe
    timeframe = record.timeframe
    if timeframe.endswith('m'):
        kind = "intraday"
    elif timeframe.endswith('D'):
        kind = "daily"
    else:
        kind = "unknown"
    
    return DatasetDescriptor(
        dataset_id=dataset_id,
        base_record=record,
        txt_root=txt_root,
        txt_required_paths=txt_required_paths,
        parquet_root=parquet_root,
        parquet_expected_paths=parquet_expected_paths,
        kind=kind,
        notes=["Auto-generated descriptor"]
    )


def get_descriptor(dataset_id: str) -> Optional[DatasetDescriptor]:
    """Get dataset descriptor by ID.
    
    Args:
        dataset_id: Dataset ID to look up
        
    Returns:
        DatasetDescriptor if found, None otherwise
    """
    from control.dataset_catalog import describe_dataset
    
    record = describe_dataset(dataset_id)
    if record is None:
        return None
    
    return create_descriptor_from_record(record)


def list_descriptors() -> List[DatasetDescriptor]:
    """List all dataset descriptors.
    
    Returns:
        List of all DatasetDescriptor objects
    """
    from control.dataset_catalog import list_datasets
    
    records = list_datasets()
    return [create_descriptor_from_record(record) for record in records]


# Test function
def test_descriptor() -> None:
    """Test the descriptor functionality."""
    print("Testing DatasetDescriptor...")
    
    # Get a sample dataset record
    from control.dataset_catalog import list_datasets
    
    records = list_datasets()
    if records:
        record = records[0]
        descriptor = create_descriptor_from_record(record)
        
        print(f"Dataset ID: {descriptor.dataset_id}")
        print(f"TXT root: {descriptor.txt_root}")
        print(f"TXT paths: {descriptor.txt_required_paths}")
        print(f"Parquet root: {descriptor.parquet_root}")
        print(f"Parquet paths: {descriptor.parquet_expected_paths}")
        print(f"Kind: {descriptor.kind}")
    else:
        print("No datasets found")


if __name__ == "__main__":
    test_descriptor()