"""Data ingest module - Raw means RAW.

Phase 6.5 Data Ingest v1: Immutable, extremely stupid raw data ingestion.
"""

from data.cache import CachePaths, cache_paths, read_parquet_cache, write_parquet_cache
from data.fingerprint import DataFingerprint, compute_txt_fingerprint
from data.raw_ingest import IngestPolicy, RawIngestResult, ingest_raw_txt

__all__ = [
    "IngestPolicy",
    "RawIngestResult",
    "ingest_raw_txt",
    "DataFingerprint",
    "compute_txt_fingerprint",
    "CachePaths",
    "cache_paths",
    "write_parquet_cache",
    "read_parquet_cache",
]
