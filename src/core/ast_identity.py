"""AST-based canonical identity for strategies.

Implements content-addressed, deterministic StrategyID derived from strategy's
canonical AST (ast-c14n-v1). This replaces filesystem iteration order, Python
import order, list index/enumerate/incremental counters, filename or class name
as primary key.

Key properties:
1. Deterministic: Same AST → same hash regardless of file location, import order
2. Content-addressed: Hash derived from canonical AST representation
3. Immutable: Strategy identity cannot change without changing its logic
4. Collision-resistant: SHA-256 provides sufficient collision resistance
5. No hash() usage: Uses hashlib.sha256 for deterministic hashing

Algorithm (ast-c14n-v1):
1. Parse source code to AST
2. Canonicalize AST (normalize whitespace, sort dict keys, etc.)
3. Serialize to canonical string representation
4. Compute SHA-256 hash
5. Encode as hex string (StrategyID)
"""

from __future__ import annotations

import ast
import hashlib
import json
import textwrap
from typing import Any, Dict, List, Optional, Union
from pathlib import Path
import inspect


class ASTCanonicalizer:
    """Canonical AST representation for deterministic hashing."""
    
    @staticmethod
    def canonicalize(node: ast.AST) -> Any:
        """Convert AST node to canonical JSON-serializable representation.
        
        Follows ast-c14n-v1 specification:
        1. Sort dictionary keys alphabetically
        2. Normalize numeric literals (float precision)
        3. Remove location information (lineno, col_offset)
        4. Handle special AST nodes consistently
        5. Preserve only semantically relevant information
        """
        if isinstance(node, ast.Module):
            return {
                "type": "Module",
                "body": [ASTCanonicalizer.canonicalize(stmt) for stmt in node.body]
            }
        
        elif isinstance(node, ast.FunctionDef):
            return {
                "type": "FunctionDef",
                "name": node.name,
                "args": ASTCanonicalizer.canonicalize(node.args),
                "body": [ASTCanonicalizer.canonicalize(stmt) for stmt in node.body],
                "decorator_list": [
                    ASTCanonicalizer.canonicalize(decorator) 
                    for decorator in node.decorator_list
                ],
                "returns": (
                    ASTCanonicalizer.canonicalize(node.returns) 
                    if node.returns else None
                )
            }
        
        elif isinstance(node, ast.ClassDef):
            return {
                "type": "ClassDef",
                "name": node.name,
                "bases": [ASTCanonicalizer.canonicalize(base) for base in node.bases],
                "keywords": [
                    ASTCanonicalizer.canonicalize(keyword) 
                    for keyword in node.keywords
                ],
                "body": [ASTCanonicalizer.canonicalize(stmt) for stmt in node.body],
                "decorator_list": [
                    ASTCanonicalizer.canonicalize(decorator) 
                    for decorator in node.decorator_list
                ]
            }
        
        elif isinstance(node, ast.arguments):
            return {
                "type": "arguments",
                "args": [ASTCanonicalizer.canonicalize(arg) for arg in node.args],
                "defaults": [
                    ASTCanonicalizer.canonicalize(default) 
                    for default in node.defaults
                ],
                "vararg": (
                    ASTCanonicalizer.canonicalize(node.vararg) 
                    if node.vararg else None
                ),
                "kwarg": (
                    ASTCanonicalizer.canonicalize(node.kwarg) 
                    if node.kwarg else None
                )
            }
        
        elif isinstance(node, ast.arg):
            return {
                "type": "arg",
                "arg": node.arg,
                "annotation": (
                    ASTCanonicalizer.canonicalize(node.annotation) 
                    if node.annotation else None
                )
            }
        
        elif isinstance(node, ast.Name):
            return {
                "type": "Name",
                "id": node.id,
                "ctx": node.ctx.__class__.__name__
            }
        
        elif isinstance(node, ast.Attribute):
            return {
                "type": "Attribute",
                "value": ASTCanonicalizer.canonicalize(node.value),
                "attr": node.attr,
                "ctx": node.ctx.__class__.__name__
            }
        
        elif isinstance(node, ast.Constant):
            value = node.value
            # Normalize numeric values
            if isinstance(value, float):
                # Use repr to preserve precision but normalize -0.0
                value = float(repr(value))
            elif isinstance(value, complex):
                value = complex(repr(value))
            return {
                "type": "Constant",
                "value": value,
                "kind": getattr(node, 'kind', None)
            }
        
        elif isinstance(node, ast.Dict):
            # Sort dictionary keys for determinism
            keys = [ASTCanonicalizer.canonicalize(k) for k in node.keys]
            values = [ASTCanonicalizer.canonicalize(v) for v in node.values]
            
            # Create list of key-value pairs for sorting
            pairs = list(zip(keys, values))
            # Sort by key representation
            pairs.sort(key=lambda x: json.dumps(x[0], sort_keys=True))
            
            sorted_keys = [k for k, _ in pairs]
            sorted_values = [v for _, v in pairs]
            
            return {
                "type": "Dict",
                "keys": sorted_keys,
                "values": sorted_values
            }
        
        elif isinstance(node, ast.List):
            return {
                "type": "List",
                "elts": [ASTCanonicalizer.canonicalize(elt) for elt in node.elts],
                "ctx": node.ctx.__class__.__name__
            }
        
        elif isinstance(node, ast.Tuple):
            return {
                "type": "Tuple",
                "elts": [ASTCanonicalizer.canonicalize(elt) for elt in node.elts],
                "ctx": node.ctx.__class__.__name__
            }
        
        elif isinstance(node, ast.Set):
            # Sets need special handling for determinism
            elts = [ASTCanonicalizer.canonicalize(elt) for elt in node.elts]
            # Sort by JSON representation
            elts.sort(key=lambda x: json.dumps(x, sort_keys=True))
            return {
                "type": "Set",
                "elts": elts
            }
        
        elif isinstance(node, ast.Call):
            # Sort keywords by argument name for determinism
            keywords = [
                {
                    "arg": kw.arg,
                    "value": ASTCanonicalizer.canonicalize(kw.value)
                }
                for kw in node.keywords
            ]
            keywords.sort(key=lambda x: x["arg"] if x["arg"] else "")
            
            return {
                "type": "Call",
                "func": ASTCanonicalizer.canonicalize(node.func),
                "args": [ASTCanonicalizer.canonicalize(arg) for arg in node.args],
                "keywords": keywords
            }
        
        elif isinstance(node, ast.keyword):
            return {
                "type": "keyword",
                "arg": node.arg,
                "value": ASTCanonicalizer.canonicalize(node.value)
            }
        
        elif isinstance(node, ast.Import):
            # Sort imports by name for determinism
            names = [
                {"name": alias.name, "asname": alias.asname}
                for alias in node.names
            ]
            names.sort(key=lambda x: x["name"])
            return {
                "type": "Import",
                "names": names
            }
        
        elif isinstance(node, ast.ImportFrom):
            # Sort imports by name for determinism
            names = [
                {"name": alias.name, "asname": alias.asname}
                for alias in node.names
            ]
            names.sort(key=lambda x: x["name"])
            return {
                "type": "ImportFrom",
                "module": node.module,
                "names": names,
                "level": node.level
            }
        
        elif isinstance(node, ast.Assign):
            return {
                "type": "Assign",
                "targets": [
                    ASTCanonicalizer.canonicalize(target) 
                    for target in node.targets
                ],
                "value": ASTCanonicalizer.canonicalize(node.value)
            }
        
        elif isinstance(node, ast.Return):
            return {
                "type": "Return",
                "value": (
                    ASTCanonicalizer.canonicalize(node.value) 
                    if node.value else None
                )
            }
        
        elif isinstance(node, ast.If):
            return {
                "type": "If",
                "test": ASTCanonicalizer.canonicalize(node.test),
                "body": [ASTCanonicalizer.canonicalize(stmt) for stmt in node.body],
                "orelse": [ASTCanonicalizer.canonicalize(stmt) for stmt in node.orelse]
            }
        
        elif isinstance(node, ast.BinOp):
            return {
                "type": "BinOp",
                "left": ASTCanonicalizer.canonicalize(node.left),
                "op": node.op.__class__.__name__,
                "right": ASTCanonicalizer.canonicalize(node.right)
            }
        
        elif isinstance(node, ast.UnaryOp):
            return {
                "type": "UnaryOp",
                "op": node.op.__class__.__name__,
                "operand": ASTCanonicalizer.canonicalize(node.operand)
            }
        
        elif isinstance(node, ast.Compare):
            return {
                "type": "Compare",
                "left": ASTCanonicalizer.canonicalize(node.left),
                "ops": [op.__class__.__name__ for op in node.ops],
                "comparators": [
                    ASTCanonicalizer.canonicalize(comp) 
                    for comp in node.comparators
                ]
            }
        
        # Handle expression contexts
        elif isinstance(node, (ast.Load, ast.Store, ast.Del)):
            return {"type": node.__class__.__name__}
        
        # Default fallback: convert node attributes to dict
        else:
            node_type = node.__class__.__name__
            result = {"type": node_type}
            
            # Get public attributes
            for attr_name in dir(node):
                if attr_name.startswith('_'):
                    continue
                if attr_name in ('lineno', 'col_offset', 'end_lineno', 'end_col_offset'):
                    continue
                
                try:
                    attr_value = getattr(node, attr_name)
                except AttributeError:
                    continue
                
                # Skip None values and empty lists
                if attr_value is None:
                    continue
                if isinstance(attr_value, list) and len(attr_value) == 0:
                    continue
                
                # Recursively canonicalize if it's an AST node
                if isinstance(attr_value, ast.AST):
                    result[attr_name] = ASTCanonicalizer.canonicalize(attr_value)
                elif isinstance(attr_value, list) and attr_value and isinstance(attr_value[0], ast.AST):
                    result[attr_name] = [
                        ASTCanonicalizer.canonicalize(item) for item in attr_value
                    ]
                elif isinstance(attr_value, (str, int, float, bool)):
                    result[attr_name] = attr_value
            
            return result
    
    @staticmethod
    def canonical_ast_hash(source_code: str) -> str:
        """Compute canonical hash of source code AST.
        
        Args:
            source_code: Python source code as string
            
        Returns:
            SHA-256 hash hex string (64 characters)
        """
        try:
            tree = ast.parse(source_code)
            canonical = ASTCanonicalizer.canonicalize(tree)
            
            # Convert to canonical JSON string with sorted keys
            canonical_json = json.dumps(
                canonical,
                sort_keys=True,
                separators=(',', ':'),  # No whitespace
                ensure_ascii=False
            )
            
            # Compute SHA-256 hash
            hash_obj = hashlib.sha256(canonical_json.encode('utf-8'))
            return hash_obj.hexdigest()
        
        except (SyntaxError, ValueError) as e:
            raise ValueError(f"Failed to parse or canonicalize source code: {e}")


def compute_strategy_id_from_source(source_code: str) -> str:
    """Compute StrategyID from strategy source code.
    
    Args:
        source_code: Strategy function source code
        
    Returns:
        StrategyID (hex string, 64 characters)
    """
    return ASTCanonicalizer.canonical_ast_hash(source_code)


def compute_strategy_id_from_function(func) -> str:
    """Compute StrategyID from strategy function object.
    
    Args:
        func: Strategy function (callable)
        
    Returns:
        StrategyID (hex string, 64 characters)
    """
    try:
        source_code = inspect.getsource(func)
        # Dedent the source code to handle indentation from nested definitions
        dedented_source = textwrap.dedent(source_code)
        return compute_strategy_id_from_source(dedented_source)
    except (OSError, TypeError) as e:
        raise ValueError(f"Failed to get source code for function: {e}")


def compute_strategy_id_from_file(filepath: Union[str, Path]) -> str:
    """Compute StrategyID from strategy source file.
    
    Args:
        filepath: Path to Python source file
        
    Returns:
        StrategyID (hex string, 64 characters)
    """
    path = Path(filepath)
    if not path.exists():
        raise FileNotFoundError(f"Strategy file not found: {filepath}")
    
    source_code = path.read_text(encoding='utf-8')
    return compute_strategy_id_from_source(source_code)


class StrategyIdentity:
    """Immutable strategy identity based on canonical AST hash."""
    
    def __init__(self, strategy_id: str, source_hash: Optional[str] = None):
        """Initialize strategy identity.
        
        Args:
            strategy_id: Content-addressed strategy ID (hex string)
            source_hash: Optional source hash for verification
        """
        if not isinstance(strategy_id, str) or len(strategy_id) != 64:
            raise ValueError(
                f"Invalid strategy_id: must be 64-character hex string, got {strategy_id}"
            )
        
        # Validate hex format
        try:
            int(strategy_id, 16)
        except ValueError:
            raise ValueError(f"Invalid strategy_id: not a valid hex string: {strategy_id}")
        
        self._strategy_id = strategy_id
        self._source_hash = source_hash
    
    @property
    def strategy_id(self) -> str:
        """Get the content-addressed strategy ID."""
        return self._strategy_id
    
    @property
    def source_hash(self) -> Optional[str]:
        """Get the source hash (if available)."""
        return self._source_hash
    
    @classmethod
    def from_source(cls, source_code: str) -> StrategyIdentity:
        """Create StrategyIdentity from source code."""
        strategy_id = compute_strategy_id_from_source(source_code)
        return cls(strategy_id, source_hash=strategy_id)
    
    @classmethod
    def from_function(cls, func) -> StrategyIdentity:
        """Create StrategyIdentity from function."""
        strategy_id = compute_strategy_id_from_function(func)
        return cls(strategy_id, source_hash=strategy_id)
    
    @classmethod
    def from_file(cls, filepath: Union[str, Path]) -> StrategyIdentity:
        """Create StrategyIdentity from file."""
        strategy_id = compute_strategy_id_from_file(filepath)
        return cls(strategy_id, source_hash=strategy_id)
    
    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, StrategyIdentity):
            return False
        return self._strategy_id == other._strategy_id
    
    def __hash__(self) -> int:
        # Use integer representation of first 16 chars for hash
        return int(self._strategy_id[:16], 16)
    
    def __repr__(self) -> str:
        return f"StrategyIdentity(strategy_id={self._strategy_id[:16]}...)"
    
    def __str__(self) -> str:
        return self._strategy_id