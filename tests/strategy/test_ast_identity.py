"""Policy tests for AST-based canonical identity (Attack #5).

Tests for determinism, rename invariance, duplicate detection, and
content-addressed strategy identity.
"""

from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
from typing import Dict, Any
import tempfile
import shutil

import pytest

from FishBroWFS_V2.core.ast_identity import (
    ASTCanonicalizer,
    compute_strategy_id_from_source,
    compute_strategy_id_from_function,
    StrategyIdentity,
)
from FishBroWFS_V2.strategy.identity_models import (
    StrategyIdentityModel,
    StrategyMetadata,
    StrategyParamSchema,
    StrategyRegistryEntry,
    StrategyManifest,
)
from FishBroWFS_V2.strategy.registry_builder import RegistryBuilder
from FishBroWFS_V2.strategy.registry import register, clear, get_by_content_id


# Sample strategy source code for testing
SAMPLE_STRATEGY_SOURCE = '''
"""Sample strategy for testing."""

from typing import Dict, Any, Mapping
import numpy as np

from FishBroWFS_V2.engine.types import OrderIntent

def sample_strategy(context: Mapping[str, Any], params: Mapping[str, float]) -> Dict[str, Any]:
    """Sample strategy implementation."""
    features = context.get("features", {})
    bar_index = context.get("bar_index", 0)
    
    # Simple moving average crossover
    sma_fast = features.get("sma_fast", [])
    sma_slow = features.get("sma_slow", [])
    
    if len(sma_fast) < 2 or len(sma_slow) < 2:
        return {"intents": [], "debug": {}}
    
    prev_fast = sma_fast[bar_index - 1]
    prev_slow = sma_slow[bar_index - 1]
    curr_fast = sma_fast[bar_index]
    curr_slow = sma_slow[bar_index]
    
    is_golden_cross = (
        prev_fast <= prev_slow and
        curr_fast > curr_slow
    )
    
    intents = []
    if is_golden_cross:
        intents.append(OrderIntent(
            order_id="test",
            created_bar=bar_index,
            role="ENTRY",
            kind="STOP",
            side="BUY",
            price=float(curr_fast),
            qty=1,
        ))
    
    return {
        "intents": intents,
        "debug": {
            "is_golden_cross": is_golden_cross,
            "sma_fast": float(curr_fast),
            "sma_slow": float(curr_slow),
        }
    }
'''

# Same strategy with different whitespace and comments
SAMPLE_STRATEGY_SOURCE_RENAMED = '''
# Different comments and whitespace
def sample_strategy(context, params):
    """Sample strategy implementation with different formatting."""
    features = context.get("features", {})
    bar_index = context.get("bar_index", 0)
    
    sma_fast = features.get("sma_fast", [])
    sma_slow = features.get("sma_slow", [])
    
    if len(sma_fast) < 2 or len(sma_slow) < 2:
        return {"intents": [], "debug": {}}
    
    prev_fast = sma_fast[bar_index - 1]
    prev_slow = sma_slow[bar_index - 1]
    curr_fast = sma_fast[bar_index]
    curr_slow = sma_slow[bar_index]
    
    is_golden_cross = (
        prev_fast <= prev_slow and
        curr_fast > curr_slow
    )
    
    intents = []
    if is_golden_cross:
        intents.append(OrderIntent(
            order_id="test",
            created_bar=bar_index,
            role="ENTRY",
            kind="STOP",
            side="BUY",
            price=float(curr_fast),
            qty=1,
        ))
    
    return {
        "intents": intents,
        "debug": {
            "is_golden_cross": is_golden_cross,
            "sma_fast": float(curr_fast),
            "sma_slow": float(curr_slow),
        }
    }
'''

# Different strategy (different logic)
DIFFERENT_STRATEGY_SOURCE = '''
def different_strategy(context, params):
    """Different strategy logic."""
    features = context.get("features", {})
    bar_index = context.get("bar_index", 0)
    
    rsi = features.get("rsi", [])
    if len(rsi) == 0:
        return {"intents": [], "debug": {}}
    
    current_rsi = rsi[bar_index]
    is_oversold = current_rsi < 30
    
    intents = []
    if is_oversold:
        # Different logic, different identity
        intents.append("different")
    
    return {"intents": intents, "debug": {}}
'''


class TestASTCanonicalizer:
    """Tests for AST canonicalization."""
    
    def test_canonicalize_simple_ast(self) -> None:
        """Test canonicalization of simple AST nodes."""
        # Parse simple expression
        source = "x = 1 + 2"
        tree = ast.parse(source)
        
        # Canonicalize
        canonical = ASTCanonicalizer.canonicalize(tree)
        
        # Should be JSON serializable
        json_str = json.dumps(canonical, sort_keys=True)
        assert isinstance(json_str, str)
        
        # Should have deterministic structure
        canonical2 = ASTCanonicalizer.canonicalize(tree)
        assert json.dumps(canonical, sort_keys=True) == json.dumps(canonical2, sort_keys=True)
    
    def test_canonicalize_dict_sorting(self) -> None:
        """Test that dictionary keys are sorted for determinism."""
        source = "d = {'b': 2, 'a': 1, 'c': 3}"
        tree = ast.parse(source)
        
        canonical = ASTCanonicalizer.canonicalize(tree)
        
        # Extract the dict node
        module_body = canonical["body"][0]
        assert module_body["type"] == "Assign"
        dict_node = module_body["value"]
        
        # Keys should be sorted
        assert dict_node["type"] == "Dict"
        keys = [k["value"] for k in dict_node["keys"]]
        assert keys == ["a", "b", "c"]  # Sorted alphabetically
    
    def test_remove_location_info(self) -> None:
        """Test that location information is removed."""
        source = "x = 1"
        tree = ast.parse(source)
        
        # Add dummy location info (not actually in AST, but verify our code doesn't include it)
        canonical = ASTCanonicalizer.canonicalize(tree)
        json_str = json.dumps(canonical, sort_keys=True)
        
        # Should not contain location field names
        assert "lineno" not in json_str
        assert "col_offset" not in json_str
        assert "end_lineno" not in json_str
        assert "end_col_offset" not in json_str


class TestStrategyIdentityDeterminism:
    """Tests for deterministic strategy identity."""
    
    def test_same_source_same_hash(self) -> None:
        """Same source code should produce same hash."""
        hash1 = compute_strategy_id_from_source(SAMPLE_STRATEGY_SOURCE)
        hash2 = compute_strategy_id_from_source(SAMPLE_STRATEGY_SOURCE)
        
        assert hash1 == hash2
        assert len(hash1) == 64  # SHA-256 hex string
        assert all(c in "0123456789abcdef" for c in hash1)
    
    def test_whitespace_invariance(self) -> None:
        """Different whitespace should produce same hash (AST is same)."""
        # Source with extra whitespace
        source_with_spaces = SAMPLE_STRATEGY_SOURCE.replace("\n", "\n\n").replace("    ", "        ")
        hash1 = compute_strategy_id_from_source(SAMPLE_STRATEGY_SOURCE)
        hash2 = compute_strategy_id_from_source(source_with_spaces)
        
        # AST should be the same (whitespace is not part of AST)
        assert hash1 == hash2
    
    def test_comment_invariance(self) -> None:
        """Different comments should produce same hash."""
        source_with_comments = SAMPLE_STRATEGY_SOURCE + "\n# This is a comment\n# Another comment"
        hash1 = compute_strategy_id_from_source(SAMPLE_STRATEGY_SOURCE)
        hash2 = compute_strategy_id_from_source(source_with_comments)
        
        # Comments are not part of AST
        assert hash1 == hash2
    
    def test_rename_invariance(self) -> None:
        """Renaming variables should produce DIFFERENT hash (different AST)."""
        # Create source with renamed variable
        renamed_source = SAMPLE_STRATEGY_SOURCE.replace("sma_fast", "fast_sma").replace("sma_slow", "slow_sma")
        hash1 = compute_strategy_id_from_source(SAMPLE_STRATEGY_SOURCE)
        hash2 = compute_strategy_id_from_source(renamed_source)
        
        # Different variable names = different AST = different hash
        assert hash1 != hash2
    
    def test_different_logic_different_hash(self) -> None:
        """Different strategy logic should produce different hash."""
        hash1 = compute_strategy_id_from_source(SAMPLE_STRATEGY_SOURCE)
        hash2 = compute_strategy_id_from_source(DIFFERENT_STRATEGY_SOURCE)
        
        assert hash1 != hash2
    
    def test_function_identity(self) -> None:
        """Test identity from function object."""
        # Define a test function
        def test_func(context, params):
            return {"intents": [], "debug": {}}
        
        # Compute identity
        identity = StrategyIdentity.from_function(test_func)
        
        assert len(identity.strategy_id) == 64
        assert identity.strategy_id == identity.source_hash
    
    def test_identity_model_validation(self) -> None:
        """Test StrategyIdentityModel validation."""
        # Valid identity
        hash_str = "a" * 64
        identity = StrategyIdentityModel(strategy_id=hash_str, source_hash=hash_str)
        assert identity.strategy_id == hash_str
        
        # Invalid length
        with pytest.raises(ValueError):
            StrategyIdentityModel(strategy_id="short", source_hash=hash_str)
        
        # Invalid hex characters
        with pytest.raises(ValueError):
            StrategyIdentityModel(strategy_id="g" * 64, source_hash=hash_str)


class TestDuplicateDetection:
    """Tests for duplicate strategy detection."""
    
    def test_duplicate_content_different_name(self) -> None:
        """Same content with different names should be detected as duplicate."""
        from FishBroWFS_V2.strategy.spec import StrategySpec
        
        # Create two specs with same function but different names
        def dummy_func(context, params):
            return {"intents": [], "debug": {}}
        
        spec1 = StrategySpec(
            strategy_id="strategy_a",
            version="v1",
            param_schema={},
            defaults={},
            fn=dummy_func
        )
        
        spec2 = StrategySpec(
            strategy_id="strategy_b",  # Different name
            version="v1",
            param_schema={},
            defaults={},
            fn=dummy_func  # Same function
        )
        
        # Clear registry
        clear()
        
        # Register first strategy
        register(spec1)
        
        # Attempt to register second should raise ValueError (duplicate content)
        with pytest.raises(ValueError) as excinfo:
            register(spec2)
        
        assert "duplicate" in str(excinfo.value).lower() or "already registered" in str(excinfo.value).lower()
        
        clear()
    
    def test_same_name_different_content(self) -> None:
        """Same name with different content should raise error."""
        from FishBroWFS_V2.strategy.spec import StrategySpec
        
        # Create two different functions
        def func1(context, params):
            return {"intents": [], "debug": {"func": 1}}
        
        def func2(context, params):
            return {"intents": [], "debug": {"func": 2}}
        
        spec1 = StrategySpec(
            strategy_id="same_name",
            version="v1",
            param_schema={},
            defaults={},
            fn=func1
        )
        
        spec2 = StrategySpec(
            strategy_id="same_name",  # Same name
            version="v1",
            param_schema={},
            defaults={},
            fn=func2  # Different function
        )
        
        clear()
        
        # Register first
        register(spec1)
        
        # Attempt to register second should raise error
        with pytest.raises(ValueError) as excinfo:
            register(spec2)
        
        assert "already registered" in str(excinfo.value).lower()
        
        clear()


class TestRegistryBuilderDeterminism:
    """Tests for deterministic registry building."""
    
    def test_manifest_deterministic_ordering(self) -> None:
        """Test that manifest entries are sorted deterministically."""
        # Create multiple registry entries with different IDs
        entries = []
        for i in range(5):
            hash_str = hashlib.sha256(f"strategy_{i}".encode()).hexdigest()
            identity = StrategyIdentityModel(strategy_id=hash_str, source_hash=hash_str)
            metadata = StrategyMetadata(
                name=f"strategy_{i}",
                version="v1",
                description=f"Strategy {i}"
            )
            param_schema = StrategyParamSchema(
                param_schema={},
                defaults={}
            )
            entry = StrategyRegistryEntry(
                identity=identity,
                metadata=metadata,
                param_schema=param_schema
            )
            entries.append(entry)
        
        # Shuffle entries
        import random
        shuffled = entries.copy()
        random.shuffle(shuffled)
        
        # Create manifest from shuffled entries
        manifest = StrategyManifest(strategies=shuffled)
        
        # Entries should be sorted by strategy_id
        strategy_ids = [entry.strategy_id for entry in manifest.strategies]
        assert strategy_ids == sorted(strategy_ids)
    
    def test_manifest_json_deterministic(self) -> None:
        """Test that manifest JSON is deterministic."""
        # Create a simple manifest
        hash_str = "a" * 64
        identity = StrategyIdentityModel(strategy_id=hash_str, source_hash=hash_str)
        metadata = StrategyMetadata(name="test", version="v1", description="Test")
        param_schema = StrategyParamSchema(param_schema={}, defaults={})
        entry = StrategyRegistryEntry(
            identity=identity,
            metadata=metadata,
            param_schema=param_schema
        )
        
        manifest = StrategyManifest(strategies=[entry])
        
        # Generate JSON multiple times
        json1 = manifest.to_json()
        json2 = manifest.to_json()
        
        # Should be identical
        assert json1 == json2
        
        # Parse and compare
        data1 = json.loads(json1)
        data2 = json.loads(json2)
        assert data1 == data2
    
    def test_content_addressed_lookup(self) -> None:
        """Test lookup by content-addressed ID."""
        from FishBroWFS_V2.strategy.spec import StrategySpec
        
        def dummy_func(context, params):
            return {"intents": [], "debug": {}}
        
        spec = StrategySpec(
            strategy_id="test_strategy",
            version="v1",
            param_schema={},
            defaults={},
            fn=dummy_func
        )
        
        clear()
        register(spec)
        
        # Get content_id
        content_id = spec.immutable_id
        
        # Lookup by content_id
        found_spec = get_by_content_id(content_id)
        assert found_spec.strategy_id == "test_strategy"
        
        clear()


class TestFileBasedIdentity:
    """Tests for file-based strategy identity."""
    
    def test_file_identity_deterministic(self, tmp_path: Path) -> None:
        """Test that file identity is deterministic."""
        # Create a strategy file
        strategy_file = tmp_path / "test_strategy.py"
        strategy_file.write_text(SAMPLE_STRATEGY_SOURCE)
        
        # Compute identity multiple times
        from FishBroWFS_V2.core.ast_identity import compute_strategy_id_from_file
        
        hash1 = compute_strategy_id_from_file(strategy_file)
        hash2 = compute_strategy_id_from_file(strategy_file)
        
        assert hash1 == hash2
        assert len(hash1) == 64
    
    def test_file_rename_invariance(self, tmp_path: Path) -> None:
        """Test that renaming file doesn't change identity."""
        # Create strategy file
        strategy_file1 = tmp_path / "strategy_a.py"
        strategy_file1.write_text(SAMPLE_STRATEGY_SOURCE)
        
        # Create same content in different file
        strategy_file2 = tmp_path / "strategy_b.py"
        strategy_file2.write_text(SAMPLE_STRATEGY_SOURCE)
        
        from FishBroWFS_V2.core.ast_identity import compute_strategy_id_from_file
        
        hash1 = compute_strategy_id_from_file(strategy_file1)
        hash2 = compute_strategy_id_from_file(strategy_file2)
        
        # Same content, different filename = same hash
        assert hash1 == hash2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])