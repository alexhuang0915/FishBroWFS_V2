"""Registry builder for StrategyManifest.json generation.

Implements deterministic, content-addressed strategy registry building
that replaces filesystem iteration order, Python import order, list
index/enumerate/incremental counters, filename or class name as primary key.

Key features:
1. Deterministic scanning: Strategies discovered in deterministic order
2. Content-addressed identity: StrategyID derived from canonical AST
3. Duplicate detection: Detect identical strategies with different names
4. Manifest generation: Create StrategyManifest.json with sorted entries
"""

from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple
import importlib.util
import sys

from FishBroWFS_V2.strategy.identity_models import (
    StrategyIdentityModel,
    StrategyMetadata,
    StrategyParamSchema,
    StrategyRegistryEntry,
    StrategyManifest,
)
from FishBroWFS_V2.core.ast_identity import (
    compute_strategy_id_from_file,
    compute_strategy_id_from_source,
)


class StrategyDiscovery:
    """Discover strategy files and extract strategy specifications."""
    
    def __init__(self, search_paths: List[Path]):
        """Initialize strategy discovery.
        
        Args:
            search_paths: List of directories to search for strategy files
        """
        self.search_paths = search_paths
        self._strategy_files: List[Path] = []
    
    def discover_strategy_files(self) -> List[Path]:
        """Discover all Python files that might contain strategies.
        
        Returns:
            List of Python file paths, sorted deterministically
        """
        strategy_files = []
        
        for search_path in self.search_paths:
            if not search_path.exists():
                continue
            
            # Recursively find all .py files
            for py_file in search_path.rglob("*.py"):
                # Skip __pycache__ and test files
                if "__pycache__" in str(py_file) or "test_" in py_file.name:
                    continue
                
                strategy_files.append(py_file)
        
        # Sort deterministically by absolute path
        strategy_files.sort(key=lambda p: str(p.absolute()))
        self._strategy_files = strategy_files
        return strategy_files
    
    def extract_strategy_from_file(self, filepath: Path) -> Optional[StrategyRegistryEntry]:
        """Extract strategy specification from a Python file.
        
        Args:
            filepath: Path to Python file
            
        Returns:
            StrategyRegistryEntry if file contains a valid strategy, None otherwise
        """
        try:
            # Parse the file to find strategy definitions
            source_code = filepath.read_text(encoding='utf-8')
            tree = ast.parse(source_code)
            
            # Look for StrategySpec definitions
            strategy_specs = self._find_strategy_specs(tree, source_code, filepath)
            
            if not strategy_specs:
                return None
            
            # For now, take the first strategy spec found
            # In the future, we might want to handle multiple strategies per file
            spec_name, spec_dict = strategy_specs[0]
            
            # Compute content-addressed identity
            content_id = compute_strategy_id_from_file(filepath)
            identity = StrategyIdentityModel(
                strategy_id=content_id,
                source_hash=content_id
            )
            
            # Extract metadata
            metadata = StrategyMetadata(
                name=spec_dict.get("strategy_id", filepath.stem),
                version=spec_dict.get("version", "v1"),
                description=f"Strategy from {filepath.name}",
                author="FishBroWFS_V2",
                tags=["discovered"]
            )
            
            # Extract parameter schema
            param_schema = StrategyParamSchema(
                param_schema=spec_dict.get("param_schema", {}),
                defaults=spec_dict.get("defaults", {})
            )
            
            return StrategyRegistryEntry(
                identity=identity,
                metadata=metadata,
                param_schema=param_schema,
                fn=None  # Function not available without importing
            )
            
        except (SyntaxError, ValueError, OSError) as e:
            # Skip files with errors
            return None
    
    def _find_strategy_specs(
        self, 
        tree: ast.AST, 
        source_code: str,
        filepath: Path
    ) -> List[Tuple[str, Dict]]:
        """Find StrategySpec definitions in AST.
        
        Args:
            tree: AST parsed from source code
            source_code: Original source code
            filepath: Path to source file
            
        Returns:
            List of (variable_name, spec_dict) tuples
        """
        specs = []
        
        for node in ast.walk(tree):
            # Look for assignments like SPEC = StrategySpec(...)
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        var_name = target.id
                        # Check if assignment is to a variable that might be a strategy spec
                        if var_name.isupper():  # Convention: constants are uppercase
                            # Try to extract the StrategySpec constructor call
                            spec_dict = self._extract_strategy_spec(node.value)
                            if spec_dict:
                                specs.append((var_name, spec_dict))
        
        return specs
    
    def _extract_strategy_spec(self, node: ast.AST) -> Optional[Dict]:
        """Extract strategy specification from AST node.
        
        Args:
            node: AST node (should be a Call to StrategySpec)
            
        Returns:
            Dictionary with strategy spec fields, or None if not a StrategySpec
        """
        if not isinstance(node, ast.Call):
            return None
        
        # Check if this is a StrategySpec constructor call
        func_name = self._get_function_name(node.func)
        if func_name != "StrategySpec":
            return None
        
        # Extract keyword arguments
        spec_dict = {}
        
        # Handle positional arguments (strategy_id, version, param_schema, defaults, fn)
        if len(node.args) >= 1:
            spec_dict["strategy_id"] = self._extract_constant(node.args[0])
        if len(node.args) >= 2:
            spec_dict["version"] = self._extract_constant(node.args[1])
        if len(node.args) >= 3:
            spec_dict["param_schema"] = self._extract_dict(node.args[2])
        if len(node.args) >= 4:
            spec_dict["defaults"] = self._extract_dict(node.args[3])
        # fn (5th arg) is a function reference, not extractable without importing
        
        # Handle keyword arguments
        for kw in node.keywords:
            if kw.arg in ["strategy_id", "version", "param_schema", "defaults", "content_id"]:
                if kw.arg in ["param_schema", "defaults"]:
                    spec_dict[kw.arg] = self._extract_dict(kw.value)
                else:
                    spec_dict[kw.arg] = self._extract_constant(kw.value)
        
        return spec_dict if spec_dict else None
    
    def _get_function_name(self, node: ast.AST) -> str:
        """Get function name from AST node."""
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            return node.attr
        elif isinstance(node, ast.Call):
            return self._get_function_name(node.func)
        return ""
    
    def _extract_constant(self, node: ast.AST) -> Optional[str]:
        """Extract constant value from AST node."""
        if isinstance(node, ast.Constant):
            return str(node.value)
        elif isinstance(node, ast.Str):  # Python < 3.8
            return node.s
        elif isinstance(node, ast.Num):  # Python < 3.8
            return str(node.n)
        elif isinstance(node, ast.NameConstant):  # Python < 3.8
            return str(node.value)
        return None
    
    def _extract_dict(self, node: ast.AST) -> Dict:
        """Extract dictionary from AST node."""
        if isinstance(node, ast.Dict):
            result = {}
            for key, value in zip(node.keys, node.values):
                key_str = self._extract_constant(key)
                if key_str is not None:
                    # Try to extract value as constant or dict
                    val = self._extract_constant(value)
                    if val is None:
                        val = self._extract_dict(value)
                    if val is not None:
                        result[key_str] = val
            return result
        return {}


class RegistryBuilder:
    """Build strategy registry with content-addressed identity."""
    
    def __init__(self, search_paths: Optional[List[Path]] = None):
        """Initialize registry builder.
        
        Args:
            search_paths: List of directories to search for strategies.
                         If None, uses default strategy directories.
        """
        if search_paths is None:
            # Default search paths
            base_dir = Path(__file__).parent.parent.parent
            self.search_paths = [
                base_dir / "strategy" / "builtin",
                base_dir / "strategy",
            ]
        else:
            self.search_paths = search_paths
        
        self.discovery = StrategyDiscovery(self.search_paths)
        self.manifest: Optional[StrategyManifest] = None
    
    def build_registry(self) -> StrategyManifest:
        """Build strategy registry from discovered files.
        
        Returns:
            StrategyManifest with all discovered strategies
        """
        # Discover strategy files
        strategy_files = self.discovery.discover_strategy_files()
        
        # Extract strategies from files
        entries = []
        content_ids: Set[str] = set()
        strategy_names: Set[str] = set()
        
        for filepath in strategy_files:
            entry = self.discovery.extract_strategy_from_file(filepath)
            if entry is None:
                continue
            
            # Check for duplicate content (different names, same logic)
            if entry.strategy_id in content_ids:
                print(f"Warning: Duplicate content detected for {entry.metadata.name}")
                continue
            
            # Check for duplicate names (different content, same name)
            if entry.metadata.name in strategy_names:
                print(f"Warning: Duplicate name detected: {entry.metadata.name}")
                continue
            
            content_ids.add(entry.strategy_id)
            strategy_names.add(entry.metadata.name)
            entries.append(entry)
        
        # Create manifest
        self.manifest = StrategyManifest(strategies=entries)
        return self.manifest
    
    def save_manifest(self, output_path: Path) -> None:
        """Save strategy manifest to file.
        
        Args:
            output_path: Path to save StrategyManifest.json
        """
        if self.manifest is None:
            self.build_registry()
        
        self.manifest.save(output_path)
        print(f"Strategy manifest saved to {output_path}")
        print(f"Total strategies: {len(self.manifest.strategies)}")
    
    def load_builtin_strategies(self) -> None:
        """Load built-in strategies into the runtime registry.
        
        This is a convenience method that loads strategies using the
        existing registry API while ensuring content-addressed identity.
        """
        from FishBroWFS_V2.strategy.registry import load_builtin_strategies as load_builtin
        load_builtin()
        
        # Verify that loaded strategies have content-addressed IDs
        from FishBroWFS_V2.strategy.registry import list_strategies
        strategies = list_strategies()
        
        for spec in strategies:
            if not spec.content_id or spec.content_id == "":
                print(f"Warning: Strategy '{spec.strategy_id}' missing content_id")
            else:
                print(f"Strategy '{spec.strategy_id}' has content_id: {spec.content_id[:16]}...")


def build_and_save_manifest(
    output_dir: Optional[Path] = None,
    filename: str = "StrategyManifest.json"
) -> Path:
    """Convenience function to build and save strategy manifest.
    
    Args:
        output_dir: Directory to save manifest (default: current directory)
        filename: Manifest filename
        
    Returns:
        Path to saved manifest file
    """
    if output_dir is None:
        output_dir = Path.cwd()
    
    output_path = output_dir / filename
    
    builder = RegistryBuilder()
    builder.save_manifest(output_path)
    
    return output_path


if __name__ == "__main__":
    # Command-line interface
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Build strategy registry with content-addressed identity"
    )
    parser.add_argument(
        "--output", "-o",
        type=Path,
        default=Path.cwd() / "StrategyManifest.json",
        help="Output path for StrategyManifest.json"
    )
    parser.add_argument(
        "--load-builtin",
        action="store_true",
        help="Load built-in strategies into runtime registry"
    )
    
    args = parser.parse_args()
    
    if args.load_builtin:
        builder = RegistryBuilder()
        builder.load_builtin_strategies()
    
    # Always build and save manifest
    build_and_save_manifest(args.output.parent, args.output.name)