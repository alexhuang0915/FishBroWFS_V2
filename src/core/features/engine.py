"""
Feature Engine (Layer 1).

Executes declarative FeatureDefinitions against DataSnapshots.
"""

from __future__ import annotations

import pandas as pd
import importlib
from typing import List
from contracts.data_models import DataSnapshot
from contracts.feature import FeatureDefinition

class FeatureEngine:
    """
    The Factory that turns Raw Data into Feature Matrices.
    """
    
    def __init__(self):
        self._cache = {}  # Simple in-memory cache for now
        
    def calculate(self, 
                  snapshot: DataSnapshot, 
                  features: List[FeatureDefinition]) -> pd.DataFrame:
        """
        Calculate a set of features for a given snapshot.
        Returns a single DataFrame with strict index alignment.
        """
        # 1. Load Data
        df_bars = load_snapshot_as_df(snapshot)
        
        results = []
        
        # 2. Compute each feature
        for feat in features:
            handler = self._resolve_handler(feat.handler_path)
            
            try:
                # Execute pure function
                df_feat = handler(df_bars, feat.params)
                results.append(df_feat)
            except Exception as e:
                raise RuntimeError(f"Failed to compute feature {feat.feature_id}: {e}")
                
        if not results:
            return pd.DataFrame(index=df_bars.index)
            
        # 3. Concatenate all features
        final_df = pd.concat(results, axis=1)
        
        # trim to original data range if features created NaNs at start (warming up)
        # But we keep alignment with bar data
        return final_df

    def _resolve_handler(self, handler_path: str):
        """Dynamically import the handler."""
        module_name, func_name = handler_path.rsplit(".", 1)
        module = importlib.import_module(module_name)
        return getattr(module, func_name)

# Quick utility to load dataframe from snapshot (for prototype)
def load_snapshot_as_df(snapshot: DataSnapshot) -> pd.DataFrame:
    path = snapshot.source_uri.replace("file://", "")
    df = pd.read_csv(path)
    # Standardize columns
    df.rename(columns={
        "Date": "timestamp", 
        "Open": "open", "High": "high", "Low": "low", "Close": "close", "Volume": "volume"
    }, inplace=True)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df.set_index("timestamp", inplace=True)
    df.sort_index(inplace=True)
    return df
