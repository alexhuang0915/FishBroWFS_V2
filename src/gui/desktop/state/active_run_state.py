"""
Minimal shared state model for ACTIVE_RUN across desktop tabs.

Provides a lightweight singleton for sharing the currently selected run
between Operation tab and Report tab (and potentially other tabs).
"""

from __future__ import annotations
from pathlib import Path
from typing import Optional, Dict, Any, Tuple
import json
import logging

logger = logging.getLogger(__name__)


class RunStatus:
    """Run status classification."""
    NONE = "NONE"           # No run dir or no metrics.json
    PARTIAL = "PARTIAL"     # metrics.json exists (KPI must show) even if other artifacts missing
    READY = "READY"         # metrics + at least one of (equity.parquet / trades.parquet / report.json) exists and loads
    VERIFIED = "VERIFIED"   # READY + audit/policy pass (future; can remain stubbed)


class ActiveRunState:
    """
    Singleton state holder for the currently active run.
    
    This provides a simple, thread-safe way for multiple tabs to read
    the same active run information without complex dependency injection.
    """
    
    _instance: Optional[ActiveRunState] = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self._run_dir: Optional[Path] = None
        self._season: Optional[str] = None
        self._run_name: Optional[str] = None
        self._status: str = RunStatus.NONE
        self._diagnostics: Dict[str, Any] = {}
        self._metrics: Dict[str, Any] = {}
        self._policy_info: Optional[Dict[str, Any]] = None
        self._policy_registry: list[Dict[str, Any]] = []
        
        self._initialized = True
    
    def set_active_run(self, run_dir: Path, season: str, run_name: str) -> None:
        """Set the active run and classify its status."""
        self._run_dir = run_dir
        self._season = season
        self._run_name = run_name
        
        # Classify the run
        self._status, self._diagnostics = self.classify_run_dir(run_dir)
        
        # Load metrics if available
        self._metrics = {}
        if self._status != RunStatus.NONE:
            metrics_path = run_dir / "metrics.json"
            if metrics_path.exists():
                try:
                    with open(metrics_path, "r", encoding="utf-8") as f:
                        self._metrics = json.load(f)
                except Exception as e:
                    logger.warning(f"Failed to load metrics.json from {run_dir}: {e}")
        self._policy_info = self._load_policy_info(run_dir)
    
    def clear_active_run(self) -> None:
        """Clear the active run (set to NONE state)."""
        self._run_dir = None
        self._season = None
        self._run_name = None
        self._status = RunStatus.NONE
        self._diagnostics = {}
        self._metrics = {}
        self._policy_info = None
    
    @staticmethod
    def classify_run_dir(run_dir: Path) -> Tuple[str, Dict[str, Any]]:
        """
        Classify a run directory into one of the status states.
        
        Returns:
            Tuple of (status, diagnostics) where diagnostics contains
            details about which files exist and their states.
        """
        if not run_dir.exists():
            return RunStatus.NONE, {"reason": "run_dir_does_not_exist"}
        
        # Check for metrics.json
        metrics_path = run_dir / "metrics.json"
        if not metrics_path.exists():
            return RunStatus.NONE, {"reason": "metrics_json_missing"}
        
        # Try to load metrics.json to ensure it's valid
        try:
            with open(metrics_path, "r", encoding="utf-8") as f:
                json.load(f)  # Just validate JSON, don't store here
        except Exception as e:
            return RunStatus.NONE, {"reason": "metrics_json_invalid", "error": str(e)}
        
        # At this point we have a valid metrics.json -> PARTIAL at minimum
        diagnostics = {
            "metrics_json": "READY",
            "manifest_json": "MISSING",
            "run_record_json": "MISSING",
            "equity_parquet": "MISSING",
            "trades_parquet": "MISSING",
            "report_json": "MISSING",
            "governance_summary_json": "MISSING",
            "scoring_breakdown_json": "MISSING",
        }
        
        # Check other files
        if (run_dir / "manifest.json").exists():
            diagnostics["manifest_json"] = "READY"
        
        if (run_dir / "run_record.json").exists():
            diagnostics["run_record_json"] = "READY"

        if (run_dir / "governance_summary.json").exists():
            diagnostics["governance_summary_json"] = "READY"

        if (run_dir / "scoring_breakdown.json").exists():
            diagnostics["scoring_breakdown_json"] = "READY"
        
        # Check parquet files (with size check)
        equity_path = run_dir / "equity.parquet"
        if equity_path.exists():
            diagnostics["equity_parquet"] = "READY" if equity_path.stat().st_size > 0 else "EMPTY"
        
        trades_path = run_dir / "trades.parquet"
        if trades_path.exists():
            diagnostics["trades_parquet"] = "READY" if trades_path.stat().st_size > 0 else "EMPTY"
        
        if (run_dir / "report.json").exists():
            diagnostics["report_json"] = "READY"
        
        # Determine if READY (has at least one of equity/trades/report)
        has_ready_artifact = (
            diagnostics["equity_parquet"] == "READY" or
            diagnostics["trades_parquet"] == "READY" or
            diagnostics["report_json"] == "READY"
        )
        
        if has_ready_artifact:
            return RunStatus.READY, diagnostics
        else:
            return RunStatus.PARTIAL, diagnostics

    def _load_policy_info(self, run_dir: Path) -> Optional[Dict[str, Any]]:
        """Load policy metadata from governance_summary.json if available."""
        summary_path = run_dir / "governance_summary.json"
        if not summary_path.exists():
            return None
        try:
            with open(summary_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            policy_block = data.get("policy")
            if isinstance(policy_block, dict):
                return dict(policy_block)
        except Exception as e:
            logger.warning(f"Failed to load policy info from {summary_path}: {e}")
        return None
    
    @property
    def run_dir(self) -> Optional[Path]:
        return self._run_dir
    
    @property
    def season(self) -> Optional[str]:
        return self._season
    
    @property
    def run_name(self) -> Optional[str]:
        return self._run_name
    
    @property
    def status(self) -> str:
        return self._status
    
    @property
    def diagnostics(self) -> Dict[str, Any]:
        return self._diagnostics.copy()  # Return copy to prevent mutation
    
    @property
    def metrics(self) -> Dict[str, Any]:
        return self._metrics.copy()  # Return copy to prevent mutation
    
    @property
    def has_metrics(self) -> bool:
        return bool(self._metrics)

    @property
    def policy_info(self) -> Optional[Dict[str, Any]]:
        return dict(self._policy_info) if self._policy_info else None

    def set_policy_registry(self, entries: list[Dict[str, Any]]) -> None:
        """Store WFS policy registry entries for UI previews."""
        self._policy_registry = list(entries) if entries else []

    @property
    def policy_registry(self) -> list[Dict[str, Any]]:
        return list(self._policy_registry)

    def get_policy_entry(self, selector: str) -> Optional[Dict[str, Any]]:
        for entry in self._policy_registry:
            if entry.get("selector") == selector:
                return entry
        return None

    def default_policy_entry(self) -> Optional[Dict[str, Any]]:
        return self.get_policy_entry("default")
    
    def get_artifact_status(self, artifact_name: str) -> str:
        """Get the status of a specific artifact."""
        return self._diagnostics.get(f"{artifact_name}", "UNKNOWN")


# Global singleton instance
active_run_state = ActiveRunState()