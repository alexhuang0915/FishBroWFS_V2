"""
WizardBridge - Single audited gateway for Wizard pages to access backend capabilities.

Wizard pages must ONLY call methods on this class; no migrate_ui_imports() usage in pages.
This eliminates "whack-a-mole" NameErrors by providing a stable, validated contract.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Tuple, Optional
import logging

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class WizardBridgeDiagnostics:
    """Diagnostics about WizardBridge configuration."""
    ok: bool
    missing: Tuple[str, ...]
    available: Tuple[str, ...]
    note: str


class WizardBridgeError(RuntimeError):
    """Raised when WizardBridge is misconfigured or missing required functions."""
    pass


class WizardBridge:
    """
    Single audited gateway for Wizard pages to access backend capabilities via UI bridge.
    
    Wizard pages must ONLY call methods on this class; no migrate_ui_imports() usage in pages.
    """

    # CRITICAL: these are the names expected to be provided by migrate_ui_imports()
    REQUIRED_FUNCS: Tuple[str, ...] = (
        "get_dataset_catalog",
        "get_strategy_catalog",
        # include more now to prevent future whack-a-mole;
        # if any are not available yet, implement stubs in bridge and remove from REQUIRED_FUNCS until ready.
        # "get_governance_status",
        # "get_worker_status",
        # "list_seasons",
        # "submit_research_job",
    )

    def __init__(self, funcs: Dict[str, Callable[..., Any]]):
        """
        Initialize with a dictionary of function names to callables.
        
        Args:
            funcs: Dictionary mapping function names to callables.
                   Must contain all REQUIRED_FUNCS.
        """
        self._funcs = funcs
        self._diag = self._validate()

    @classmethod
    def create_default(cls) -> "WizardBridge":
        """
        Obtain callable map from migrate_ui_imports() ONCE and validate required funcs.
        
        Must be safe at runtime (page render), and must not create UI elements.
        
        Returns:
            WizardBridge instance with validated functions.
            
        Raises:
            WizardBridgeError: If required functions are missing.
        """
        from FishBroWFS_V2.gui.adapters.ui_bridge import migrate_ui_imports
        
        # Create a temporary dict to collect functions
        temp_globals: Dict[str, Any] = {}
        
        # Call migrate_ui_imports with our temp dict
        # Note: migrate_ui_imports modifies the dict in place
        migrate_ui_imports(temp_globals)
        
        # Extract callable functions
        funcs = {}
        for name, obj in temp_globals.items():
            if callable(obj):
                funcs[name] = obj
        
        return cls(funcs)

    def diagnostics(self) -> WizardBridgeDiagnostics:
        """Get diagnostics about the bridge configuration."""
        return self._diag

    def _validate(self) -> WizardBridgeDiagnostics:
        """Validate that all required functions are present and callable."""
        available = tuple(sorted(k for k, v in self._funcs.items() if callable(v)))
        missing = tuple(sorted(k for k in self.REQUIRED_FUNCS
                              if k not in self._funcs or not callable(self._funcs.get(k))))
        ok = len(missing) == 0
        note = "ok" if ok else "missing required wizard bridge functions"
        
        # Only fail-fast if we have some functions but missing required ones
        # Allow empty funcs dict for graceful degradation
        if not ok and self._funcs:
            # Fail-fast: make misconfiguration obvious (no silent 500 later).
            raise WizardBridgeError(
                f"WizardBridge misconfigured; missing: {missing}. "
                f"Available: {available}"
            )
        
        return WizardBridgeDiagnostics(ok=ok, missing=missing, available=available, note=note)

    # --- Public Wizard APIs (stable contract) ---

    def get_dataset_options(self) -> List[Tuple[str, str]]:
        """
        Return deterministic list of (value, label) for dataset selection.
        
        Must never raise; on error returns [] and logs exception.
        
        Returns:
            List of (dataset_id, label) tuples sorted by dataset_id.
        """
        try:
            get_dataset_catalog = self._funcs["get_dataset_catalog"]
            catalog = get_dataset_catalog()
            # Accept common catalog shapes:
            # - dict-like mapping id->descriptor
            # - object with .datasets or .items()
            ids = self._extract_ids(catalog)
            opts = [(i, i) for i in sorted(ids)]
            return opts
        except Exception:
            logger.exception("WizardBridge.get_dataset_options failed")
            return []

    def get_strategy_options(self) -> List[Tuple[str, str]]:
        """
        Return deterministic list of (value, label) for strategy selection.
        
        Must never raise; on error returns [] and logs exception.
        
        Returns:
            List of (strategy_id, label) tuples sorted by strategy_id.
        """
        try:
            get_strategy_catalog = self._funcs["get_strategy_catalog"]
            catalog = get_strategy_catalog()
            ids = self._extract_ids(catalog)
            opts = [(i, i) for i in sorted(ids)]
            return opts
        except Exception:
            logger.exception("WizardBridge.get_strategy_options failed")
            return []

    @staticmethod
    def _extract_ids(catalog: Any) -> List[str]:
        """
        Heuristic extractor for IDs from common catalog shapes.
        
        Keep it simple and deterministic. Never raise.
        
        Args:
            catalog: Catalog object (dict, object with attributes, etc.)
            
        Returns:
            List of string IDs.
        """
        if catalog is None:
            return []
        
        try:
            # dict mapping id->something
            if isinstance(catalog, dict):
                return [str(k) for k in catalog.keys()]
            
            # pydantic / dataclass with attribute commonly used
            for attr in ("datasets", "strategies", "items"):
                if hasattr(catalog, attr):
                    obj = getattr(catalog, attr)
                    if isinstance(obj, dict):
                        return [str(k) for k in obj.keys()]
                    if isinstance(obj, (list, tuple)):
                        # list of descriptors or IDs
                        out = []
                        for x in obj:
                            if isinstance(x, str):
                                out.append(x)
                            elif hasattr(x, "id"):
                                out.append(str(getattr(x, "id")))
                            elif hasattr(x, "strategy_id"):
                                out.append(str(getattr(x, "strategy_id")))
                            elif hasattr(x, "dataset_id"):
                                out.append(str(getattr(x, "dataset_id")))
                        return out
            
            # generic iterable of keys
            if hasattr(catalog, "keys"):
                return [str(k) for k in catalog.keys()]
                
        except Exception:
            # Swallow any extraction errors and return empty list
            return []
        
        return []

    # --- Optional: Direct access to bridge functions (for compatibility) ---
    
    def get_function(self, name: str) -> Optional[Callable[..., Any]]:
        """
        Get a function by name from the bridge.
        
        Use sparingly; prefer the typed methods above.
        """
        return self._funcs.get(name)
    
    def has_function(self, name: str) -> bool:
        """Check if a function is available in the bridge."""
        return name in self._funcs and callable(self._funcs[name])


# Convenience function for wizard pages
def get_wizard_bridge() -> WizardBridge:
    """
    Get or create a WizardBridge instance.
    
    This is the main entry point for wizard pages.
    
    Returns:
        WizardBridge instance, or None if creation fails.
    """
    try:
        return WizardBridge.create_default()
    except WizardBridgeError as e:
        logger.exception("Failed to create WizardBridge")
        # Return a minimal bridge with empty funcs for graceful degradation
        return WizardBridge({})
    except Exception as e:
        logger.exception("Unexpected error creating WizardBridge")
        return WizardBridge({})