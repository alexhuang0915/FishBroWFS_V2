"""
RunEvidenceReader - Reads artifacts from research runs for portfolio admission.

Single source of truth for locating run outputs and parsing required artifacts.
"""
import json
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Any
import pandas as pd
import numpy as np

from control.paths import get_outputs_root
from contracts.supervisor.evidence_schemas import PolicyCheckBundle


class RunEvidenceReader:
    """Reads evidence artifacts from a research run directory."""
    
    def __init__(self, outputs_root: Optional[Path] = None):
        self.outputs_root = outputs_root or get_outputs_root()
    
    def _resolve_run_dir(self, run_id: str, season: str = "current") -> Path:
        """Resolve the run directory path (SSOT)."""
        # Standard pattern: outputs/seasons/{season}/{run_id}
        return self.outputs_root / "seasons" / season / run_id
    
    def read_policy_check(self, run_id: str, season: str = "current") -> PolicyCheckBundle:
        """
        Read policy_check.json from run evidence.
        
        Raises:
            FileNotFoundError: if policy_check.json does not exist
            ValueError: if JSON is malformed
        """
        run_dir = self._resolve_run_dir(run_id, season)
        policy_path = run_dir / "policy_check.json"
        if not policy_path.exists():
            # Also check in evidence subdirectory (governed handler pattern)
            evidence_path = run_dir / "evidence" / "policy_check.json"
            if evidence_path.exists():
                policy_path = evidence_path
            else:
                raise FileNotFoundError(
                    f"policy_check.json not found for run {run_id} in {run_dir}"
                )
        
        with open(policy_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        # Convert to PolicyCheckBundle (dataclass)
        # Note: PolicyCheckBundle uses dataclasses.asdict for serialization
        # We need to reconstruct the nested objects.
        from dataclasses import asdict
        from contracts.supervisor.evidence_schemas import PolicyCheck
        
        pre_flight = [
            PolicyCheck(**check_data) for check_data in data.get("pre_flight_checks", [])
        ]
        post_flight = [
            PolicyCheck(**check_data) for check_data in data.get("post_flight_checks", [])
        ]
        downstream_admissible = data.get("downstream_admissible", True)
        
        bundle = PolicyCheckBundle(
            pre_flight_checks=pre_flight,
            post_flight_checks=post_flight,
            downstream_admissible=downstream_admissible
        )
        return bundle
    
    def read_score(self, run_id: str, season: str = "current") -> float:
        """
        Read score from report.json (or metrics.json).
        
        Raises:
            FileNotFoundError: if report.json does not exist
            KeyError: if score field missing
        """
        run_dir = self._resolve_run_dir(run_id, season)
        # Try report.json first
        report_path = run_dir / "report.json"
        if report_path.exists():
            with open(report_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            # Look for score in metrics
            if "metrics" in data and "score" in data["metrics"]:
                return float(data["metrics"]["score"])
            # Fallback to net_profit
            if "metrics" in data and "net_profit" in data["metrics"]:
                return float(data["metrics"]["net_profit"])
        
        # Try metrics.json
        metrics_path = run_dir / "metrics.json"
        if metrics_path.exists():
            with open(metrics_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if "score" in data:
                return float(data["score"])
            if "net_profit" in data:
                return float(data["net_profit"])
        
        raise FileNotFoundError(
            f"Could not find score for run {run_id} in {run_dir}"
        )
    
    def read_max_drawdown(self, run_id: str, season: str = "current") -> float:
        """
        Read max drawdown from report.json (or metrics.json).
        
        Returns positive value (e.g., 0.15 for 15% drawdown).
        Raises FileNotFoundError if not found.
        """
        run_dir = self._resolve_run_dir(run_id, season)
        report_path = run_dir / "report.json"
        if report_path.exists():
            with open(report_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if "metrics" in data and "max_dd" in data["metrics"]:
                # max_dd is typically negative; convert to positive magnitude
                dd = float(data["metrics"]["max_dd"])
                return abs(dd)
        
        metrics_path = run_dir / "metrics.json"
        if metrics_path.exists():
            with open(metrics_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if "max_dd" in data:
                return abs(float(data["max_dd"]))
        
        # Fallback: compute from equity.parquet if exists
        equity_path = run_dir / "equity.parquet"
        if equity_path.exists():
            df = pd.read_parquet(equity_path)
            if "equity" in df.columns:
                equity = df["equity"].values
                peak = np.maximum.accumulate(equity)
                drawdown = (equity - peak) / peak
                max_dd = abs(np.min(drawdown))
                return float(max_dd)
        
        raise FileNotFoundError(
            f"Could not find max drawdown for run {run_id} in {run_dir}"
        )
    
    def read_returns_series(self, run_id: str, season: str = "current") -> Tuple[List[str], List[float]]:
        """
        Read daily returns series from equity.parquet.
        
        Returns:
            (dates_utc, returns) where dates_utc are ISO strings,
            returns are daily returns (simple).
        
        Raises:
            FileNotFoundError: if equity.parquet does not exist
            ValueError: if equity data cannot be processed
        """
        run_dir = self._resolve_run_dir(run_id, season)
        equity_path = run_dir / "equity.parquet"
        if not equity_path.exists():
            # Also check in research subdirectory
            research_equity = run_dir / "research" / "equity.parquet"
            if research_equity.exists():
                equity_path = research_equity
            else:
                raise FileNotFoundError(
                    f"equity.parquet not found for run {run_id} in {run_dir}"
                )
        
        df = pd.read_parquet(equity_path)
        # Ensure required columns
        if "ts" not in df.columns or "equity" not in df.columns:
            raise ValueError(
                f"equity.parquet missing 'ts' or 'equity' columns for run {run_id}"
            )
        
        # Sort by timestamp
        df = df.sort_values("ts")
        
        # Compute daily returns (simple)
        equity = df["equity"].values
        returns = np.diff(equity) / equity[:-1]  # (E_t - E_{t-1}) / E_{t-1}
        
        # Dates for returns (align with end of period)
        dates = df["ts"].iloc[1:].tolist()
        # Convert to ISO strings
        dates_utc = [d.isoformat() + "Z" if hasattr(d, 'isoformat') else str(d) for d in dates]
        
        return dates_utc, returns.tolist()
    
    def read_returns_series_if_exists(self, run_id: str, season: str = "current") -> Optional[Tuple[List[str], List[float]]]:
        """Return returns series if equity.parquet exists, else None."""
        try:
            return self.read_returns_series(run_id, season)
        except (FileNotFoundError, ValueError):
            return None
    
    def validate_run_has_required_artifacts(self, run_id: str, season: str = "current") -> List[str]:
        """
        Check which required artifacts are missing.
        
        Returns list of missing artifact descriptions.
        """
        missing = []
        run_dir = self._resolve_run_dir(run_id, season)
        
        # 1) policy_check.json
        policy_path = run_dir / "policy_check.json"
        evidence_path = run_dir / "evidence" / "policy_check.json"
        if not policy_path.exists() and not evidence_path.exists():
            missing.append("policy_check.json")
        
        # 2) score (report.json or metrics.json)
        report_path = run_dir / "report.json"
        metrics_path = run_dir / "metrics.json"
        if not report_path.exists() and not metrics_path.exists():
            missing.append("score/metrics")
        
        # 3) max drawdown (same as above)
        # 4) returns series (equity.parquet)
        equity_path = run_dir / "equity.parquet"
        research_equity = run_dir / "research" / "equity.parquet"
        if not equity_path.exists() and not research_equity.exists():
            missing.append("equity.parquet")
        
        return missing