"""Dataset Catalog for M1 Wizard.

Provides dataset listing and filtering capabilities for the wizard UI.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import List, Optional

from FishBroWFS_V2.data.dataset_registry import DatasetIndex, DatasetRecord


class DatasetCatalog:
    """Catalog for available datasets."""
    
    def __init__(self, index_path: Optional[Path] = None):
        """Initialize catalog with dataset index.
        
        Args:
            index_path: Path to dataset index JSON file. If None, uses default.
        """
        self.index_path = index_path or Path("outputs/datasets/datasets_index.json")
        self._index: Optional[DatasetIndex] = None
    
    def load_index(self) -> DatasetIndex:
        """Load dataset index from file."""
        if not self.index_path.exists():
            raise FileNotFoundError(
                f"Dataset index not found at {self.index_path}. "
                "Please run: python scripts/build_dataset_registry.py"
            )
        
        data = json.loads(self.index_path.read_text(encoding="utf-8"))
        self._index = DatasetIndex.model_validate(data)
        return self._index
    
    @property
    def index(self) -> DatasetIndex:
        """Get dataset index (loads if not already loaded)."""
        if self._index is None:
            self.load_index()
        return self._index
    
    def list_datasets(self) -> List[DatasetRecord]:
        """List all available datasets."""
        return self.index.datasets
    
    def get_dataset(self, dataset_id: str) -> Optional[DatasetRecord]:
        """Get dataset by ID."""
        for dataset in self.index.datasets:
            if dataset.id == dataset_id:
                return dataset
        return None
    
    def filter_by_symbol(self, symbol: str) -> List[DatasetRecord]:
        """Filter datasets by symbol."""
        return [d for d in self.index.datasets if d.symbol == symbol]
    
    def filter_by_timeframe(self, timeframe: str) -> List[DatasetRecord]:
        """Filter datasets by timeframe."""
        return [d for d in self.index.datasets if d.timeframe == timeframe]
    
    def filter_by_exchange(self, exchange: str) -> List[DatasetRecord]:
        """Filter datasets by exchange."""
        return [d for d in self.index.datasets if d.exchange == exchange]
    
    def get_unique_symbols(self) -> List[str]:
        """Get list of unique symbols."""
        return sorted({d.symbol for d in self.index.datasets})
    
    def get_unique_timeframes(self) -> List[str]:
        """Get list of unique timeframes."""
        return sorted({d.timeframe for d in self.index.datasets})
    
    def get_unique_exchanges(self) -> List[str]:
        """Get list of unique exchanges."""
        return sorted({d.exchange for d in self.index.datasets})
    
    def validate_dataset_selection(
        self,
        dataset_id: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> bool:
        """Validate dataset selection with optional date range.
        
        Args:
            dataset_id: Dataset ID to validate
            start_date: Optional start date (YYYY-MM-DD)
            end_date: Optional end date (YYYY-MM-DD)
            
        Returns:
            True if valid, False otherwise
        """
        dataset = self.get_dataset(dataset_id)
        if dataset is None:
            return False
        
        # TODO: Add date range validation if needed
        return True
    
    def list_dataset_ids(self) -> List[str]:
        """Get list of all dataset IDs.
        
        Returns:
            List of dataset IDs sorted alphabetically
        """
        return sorted([d.id for d in self.index.datasets])
    
    def describe_dataset(self, dataset_id: str) -> Optional[DatasetRecord]:
        """Get dataset descriptor by ID.
        
        Args:
            dataset_id: Dataset ID to describe
            
        Returns:
            DatasetRecord if found, None otherwise
        """
        return self.get_dataset(dataset_id)


# Singleton instance for easy access
_catalog_instance: Optional[DatasetCatalog] = None

def get_dataset_catalog() -> DatasetCatalog:
    """Get singleton dataset catalog instance."""
    global _catalog_instance
    if _catalog_instance is None:
        _catalog_instance = DatasetCatalog()
    return _catalog_instance


# Public API functions for registry access
def list_dataset_ids() -> List[str]:
    """Public API: Get list of all dataset IDs.
    
    Returns:
        List of dataset IDs sorted alphabetically
    """
    catalog = get_dataset_catalog()
    return catalog.list_dataset_ids()


def describe_dataset(dataset_id: str) -> Optional[DatasetRecord]:
    """Public API: Get dataset descriptor by ID.
    
    Args:
        dataset_id: Dataset ID to describe
        
    Returns:
        DatasetRecord if found, None otherwise
    """
    catalog = get_dataset_catalog()
    return catalog.describe_dataset(dataset_id)