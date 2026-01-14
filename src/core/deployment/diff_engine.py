"""
Diff Engine for Replay/Compare UX v1 (Read-only Audit Diff for Deployment Bundles).

Deterministic diff engine for comparing deployment bundles with:
- No metric leakage (Hybrid BC v1.1 Layer1/Layer2 compliance)
- Deterministic output (same inputs → same diff)
- Structured diff with actionable insights
- Read-only operation (no writes to outputs/)

Key principles:
1. Deterministic: Sort all keys, use canonical JSON for comparison
2. No metrics: Redact prohibited keywords (net, pnl, sharpe, mdd, etc.)
3. Structured: Return actionable diff categories (added, removed, changed)
4. Read-only: Only reads from bundles, writes only to evidence folder
"""

from __future__ import annotations

import json
import logging
import hashlib
from pathlib import Path
from typing import Dict, List, Optional, Any, Union, Tuple, Set
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field

from ..paths import get_outputs_root
from control.artifacts import canonical_json_bytes, compute_sha256
from contracts.portfolio.gate_summary_schemas import GateSummaryV1, GateItemV1, GateStatus

logger = logging.getLogger(__name__)


# ============================================================================
# Data Models for Diff Engine
# ============================================================================

class DiffType(str, Enum):
    """Types of differences detected."""
    ADDED = "added"
    REMOVED = "removed"
    CHANGED = "changed"
    UNCHANGED = "unchanged"


class DiffItemV1(BaseModel):
    """A single difference item."""
    diff_type: DiffType
    path: str  # JSON path or file path
    key: str  # Field name or identifier
    value_a: Optional[Any] = None
    value_b: Optional[Any] = None
    description: str = ""
    
    class Config:
        json_encoders = {Enum: lambda e: e.value}


class DiffCategoryV1(BaseModel):
    """Category of differences."""
    category: str  # "metadata", "artifacts", "gate_summary", "strategy_report", etc.
    items: List[DiffItemV1] = Field(default_factory=list)
    count: int = 0
    
    class Config:
        json_encoders = {Enum: lambda e: e.value}


class DiffReportV1(BaseModel):
    """Complete diff report for two deployment bundles."""
    report_id: str
    compared_at: str
    bundle_a_path: str
    bundle_b_path: str
    bundle_a_deployment_id: Optional[str] = None
    bundle_b_deployment_id: Optional[str] = None
    bundle_a_job_id: Optional[str] = None
    bundle_b_job_id: Optional[str] = None
    
    # Diff summary
    total_differences: int = 0
    categories: List[DiffCategoryV1] = Field(default_factory=list)
    
    # Validation status
    bundle_a_valid: bool = False
    bundle_b_valid: bool = False
    validation_errors: List[str] = Field(default_factory=list)
    
    # Deterministic hash of diff report (excluding this field)
    diff_hash: str = ""
    
    class Config:
        json_encoders = {Enum: lambda e: e.value}


# ============================================================================
# Metric Leakage Prevention
# ============================================================================

class MetricRedactor:
    """Redacts metric-related fields to prevent leakage (Hybrid BC v1.1)."""
    
    # Prohibited metric keywords (Layer1/Layer2 must not contain these)
    PROHIBITED_KEYWORDS = {
        "net", "pnl", "profit", "loss", "sharpe", "mdd", "max_drawdown",
        "return", "returns", "performance", "metric", "metrics",
        "win_rate", "loss_rate", "avg_win", "avg_loss", "profit_factor",
        "expectancy", "risk_reward", "calmar", "sortino", "omega",
        "var", "value_at_risk", "cvar", "conditional_var",
        "volatility", "std", "standard_deviation", "variance",
        "skewness", "kurtosis", "alpha", "beta", "information_ratio",
        "treynor", "jensen", "appraisal", "tracking_error",
        "ulcer", "ulcer_index", "pain_index", "pain_ratio",
        "recovery_factor", "risk_adjusted_return", "mar",
        "k_ratio", "burke_ratio", "sterling_ratio", "gain_to_pain",
        "profit_to_max_drawdown", "cagr", "compound_annual_growth",
        "total_return", "cumulative_return", "excess_return",
        "benchmark_return", "relative_return", "absolute_return",
    }
    
    @classmethod
    def should_redact_key(cls, key: str) -> bool:
        """Check if a key should be redacted."""
        key_lower = key.lower()
        for prohibited in cls.PROHIBITED_KEYWORDS:
            if prohibited in key_lower:
                return True
        return False
    
    @classmethod
    def redact_value(cls, value: Any) -> Any:
        """Redact a value (replace with placeholder)."""
        if isinstance(value, (int, float)):
            return "[REDACTED:METRIC]"
        elif isinstance(value, str):
            return "[REDACTED:METRIC]"
        elif isinstance(value, dict):
            return {"_redacted": "metric_data"}
        elif isinstance(value, list):
            return ["[REDACTED:METRIC]"]
        else:
            return "[REDACTED:METRIC]"
    
    @classmethod
    def redact_dict(cls, data: Dict[str, Any]) -> Dict[str, Any]:
        """Recursively redact metric-related fields from a dict."""
        if not isinstance(data, dict):
            return data
        
        redacted = {}
        for key, value in data.items():
            if cls.should_redact_key(key):
                redacted[key] = cls.redact_value(value)
            elif isinstance(value, dict):
                redacted[key] = cls.redact_dict(value)
            elif isinstance(value, list):
                redacted[key] = [cls.redact_dict(item) if isinstance(item, dict) else 
                                (cls.redact_value(item) if cls._is_metric_list_item(key, item) else item)
                                for item in value]
            else:
                redacted[key] = value
        
        return redacted
    
    @classmethod
    def _is_metric_list_item(cls, parent_key: str, item: Any) -> bool:
        """Check if a list item should be redacted."""
        if isinstance(item, (int, float)):
            # Numeric items under metric-suspicious keys
            return cls.should_redact_key(parent_key)
        return False


# ============================================================================
# Diff Engine
# ============================================================================

class DiffEngine:
    """Deterministic diff engine for deployment bundles (no metric leakage)."""
    
    def __init__(
        self,
        outputs_root: Optional[Path] = None,
        redact_metrics: bool = True,
    ):
        self.outputs_root = (outputs_root or get_outputs_root()).resolve()
        self.redact_metrics = redact_metrics
        logger.info(f"DiffEngine initialized with outputs_root: {self.outputs_root}")
        logger.info(f"Metric redaction: {redact_metrics}")
    
    def compute_diff_hash(self, diff_report: DiffReportV1) -> str:
        """Compute deterministic hash of diff report (excluding hash field)."""
        report_dict = diff_report.model_dump()
        report_dict["diff_hash"] = ""
        
        # Sort categories and items for deterministic ordering
        if "categories" in report_dict:
            for category in report_dict["categories"]:
                if "items" in category:
                    category["items"] = sorted(
                        category["items"],
                        key=lambda x: (x.get("path", ""), x.get("key", ""))
                    )
            report_dict["categories"] = sorted(
                report_dict["categories"],
                key=lambda x: x.get("category", "")
            )
        
        canonical_bytes = canonical_json_bytes(report_dict)
        return compute_sha256(canonical_bytes)
    
    def compare_dicts(
        self,
        dict_a: Dict[str, Any],
        dict_b: Dict[str, Any],
        path: str = "",
    ) -> List[DiffItemV1]:
        """Compare two dictionaries recursively."""
        diffs = []
        
        # Get all keys from both dicts
        all_keys = set(dict_a.keys()) | set(dict_b.keys())
        
        for key in sorted(all_keys):  # Deterministic ordering
            current_path = f"{path}.{key}" if path else key
            
            if key in dict_a and key not in dict_b:
                # Key removed
                diffs.append(DiffItemV1(
                    diff_type=DiffType.REMOVED,
                    path=current_path,
                    key=key,
                    value_a=dict_a[key],
                    description=f"Key '{key}' removed",
                ))
            
            elif key not in dict_a and key in dict_b:
                # Key added
                diffs.append(DiffItemV1(
                    diff_type=DiffType.ADDED,
                    path=current_path,
                    key=key,
                    value_b=dict_b[key],
                    description=f"Key '{key}' added",
                ))
            
            else:
                # Key exists in both, compare values
                value_a = dict_a[key]
                value_b = dict_b[key]
                
                if isinstance(value_a, dict) and isinstance(value_b, dict):
                    # Recursively compare nested dicts
                    nested_diffs = self.compare_dicts(value_a, value_b, current_path)
                    diffs.extend(nested_diffs)
                
                elif isinstance(value_a, list) and isinstance(value_b, list):
                    # Compare lists
                    list_diffs = self.compare_lists(value_a, value_b, current_path)
                    diffs.extend(list_diffs)
                
                elif value_a != value_b:
                    # Simple value changed
                    diffs.append(DiffItemV1(
                        diff_type=DiffType.CHANGED,
                        path=current_path,
                        key=key,
                        value_a=value_a,
                        value_b=value_b,
                        description=f"Value changed for '{key}'",
                    ))
        
        return diffs
    
    def compare_lists(
        self,
        list_a: List[Any],
        list_b: List[Any],
        path: str = "",
    ) -> List[DiffItemV1]:
        """Compare two lists (simple element-by-element comparison)."""
        diffs = []
        
        # Compare lengths
        if len(list_a) != len(list_b):
            diffs.append(DiffItemV1(
                diff_type=DiffType.CHANGED,
                path=path,
                key="length",
                value_a=len(list_a),
                value_b=len(list_b),
                description=f"List length changed from {len(list_a)} to {len(list_b)}",
            ))
        
        # Compare elements (up to min length)
        min_len = min(len(list_a), len(list_b))
        for i in range(min_len):
            elem_a = list_a[i]
            elem_b = list_b[i]
            
            if isinstance(elem_a, dict) and isinstance(elem_b, dict):
                # Compare dict elements
                elem_path = f"{path}[{i}]"
                nested_diffs = self.compare_dicts(elem_a, elem_b, elem_path)
                diffs.extend(nested_diffs)
            
            elif elem_a != elem_b:
                # Simple element changed
                diffs.append(DiffItemV1(
                    diff_type=DiffType.CHANGED,
                    path=f"{path}[{i}]",
                    key=f"element_{i}",
                    value_a=elem_a,
                    value_b=elem_b,
                    description=f"Element {i} changed",
                ))
        
        return diffs
    
    def compare_gate_summaries(
        self,
        gate_a: GateSummaryV1,
        gate_b: GateSummaryV1,
    ) -> DiffCategoryV1:
        """Compare two gate summaries (deterministic, no metrics)."""
        category = DiffCategoryV1(category="gate_summary")
        
        # Compare overall status
        if gate_a.overall_status != gate_b.overall_status:
            category.items.append(DiffItemV1(
                diff_type=DiffType.CHANGED,
                path="gate_summary.overall_status",
                key="overall_status",
                value_a=gate_a.overall_status.value,
                value_b=gate_b.overall_status.value,
                description=f"Overall gate status changed from {gate_a.overall_status.value} to {gate_b.overall_status.value}",
            ))
        
        # Compare overall message
        if gate_a.overall_message != gate_b.overall_message:
            category.items.append(DiffItemV1(
                diff_type=DiffType.CHANGED,
                path="gate_summary.overall_message",
                key="overall_message",
                value_a=gate_a.overall_message,
                value_b=gate_b.overall_message,
                description="Overall gate message changed",
            ))
        
        # Compare counts
        if gate_a.counts != gate_b.counts:
            for status_key in ["pass", "warn", "reject", "skip", "unknown"]:
                count_a = gate_a.counts.get(status_key, 0)
                count_b = gate_b.counts.get(status_key, 0)
                
                if count_a != count_b:
                    category.items.append(DiffItemV1(
                        diff_type=DiffType.CHANGED,
                        path=f"gate_summary.counts.{status_key}",
                        key=status_key,
                        value_a=count_a,
                        value_b=count_b,
                        description=f"{status_key} count changed from {count_a} to {count_b}",
                    ))
        
        # Compare individual gates
        gates_a_by_id = {gate.gate_id: gate for gate in gate_a.gates}
        gates_b_by_id = {gate.gate_id: gate for gate in gate_b.gates}
        
        all_gate_ids = set(gates_a_by_id.keys()) | set(gates_b_by_id.keys())
        
        for gate_id in sorted(all_gate_ids):  # Deterministic ordering
            gate_a = gates_a_by_id.get(gate_id)
            gate_b = gates_b_by_id.get(gate_id)
            
            if gate_a and not gate_b:
                # Gate removed
                category.items.append(DiffItemV1(
                    diff_type=DiffType.REMOVED,
                    path=f"gate_summary.gates.{gate_id}",
                    key=gate_id,
                    value_a=gate_a.gate_name,
                    description=f"Gate '{gate_a.gate_name}' ({gate_id}) removed",
                ))
            
            elif not gate_a and gate_b:
                # Gate added
                category.items.append(DiffItemV1(
                    diff_type=DiffType.ADDED,
                    path=f"gate_summary.gates.{gate_id}",
                    key=gate_id,
                    value_b=gate_b.gate_name,
                    description=f"Gate '{gate_b.gate_name}' ({gate_id}) added",
                ))
            
            else:
                # Gate exists in both, compare details
                if gate_a.status != gate_b.status:
                    category.items.append(DiffItemV1(
                        diff_type=DiffType.CHANGED,
                        path=f"gate_summary.gates.{gate_id}.status",
                        key="status",
                        value_a=gate_a.status.value,
                        value_b=gate_b.status.value,
                        description=f"Gate '{gate_a.gate_name}' status changed from {gate_a.status.value} to {gate_b.status.value}",
                    ))
                
                if gate_a.message != gate_b.message:
                    category.items.append(DiffItemV1(
                        diff_type=DiffType.CHANGED,
                        path=f"gate_summary.gates.{gate_id}.message",
                        key="message",
                        value_a=gate_a.message,
                        value_b=gate_b.message,
                        description=f"Gate '{gate_a.gate_name}' message changed",
                    ))
        
        category.count = len(category.items)
        return category
    
    def compare_artifacts(
        self,
        artifacts_a: List[Dict[str, Any]],
        artifacts_b: List[Dict[str, Any]],
    ) -> DiffCategoryV1:
        """Compare artifact lists from two bundles."""
        category = DiffCategoryV1(category="artifacts")
        
        artifacts_a_by_id = {a.get("artifact_id"): a for a in artifacts_a}
        artifacts_b_by_id = {a.get("artifact_id"): a for a in artifacts_b}
        
        all_artifact_ids = set(artifacts_a_by_id.keys()) | set(artifacts_b_by_id.keys())
        
        for artifact_id in sorted(all_artifact_ids):
            artifact_a = artifacts_a_by_id.get(artifact_id)
            artifact_b = artifacts_b_by_id.get(artifact_id)
            
            if artifact_a and not artifact_b:
                # Artifact removed
                category.items.append(DiffItemV1(
                    diff_type=DiffType.REMOVED,
                    path=f"artifacts.{artifact_id}",
                    key=artifact_id,
                    value_a=artifact_a.get("artifact_type"),
                    description=f"Artifact '{artifact_id}' ({artifact_a.get('artifact_type')}) removed",
                ))
            
            elif not artifact_a and artifact_b:
                # Artifact added
                category.items.append(DiffItemV1(
                    diff_type=DiffType.ADDED,
                    path=f"artifacts.{artifact_id}",
                    key=artifact_id,
                    value_b=artifact_b.get("artifact_type"),
                    description=f"Artifact '{artifact_id}' ({artifact_b.get('artifact_type')}) added",
                ))
            
            else:
                # Artifact exists in both, compare checksums
                checksum_a = artifact_a.get("checksum_sha256", "")
                checksum_b = artifact_b.get("checksum_sha256", "")
                
                if checksum_a != checksum_b:
                    category.items.append(DiffItemV1(
                        diff_type=DiffType.CHANGED,
                        path=f"artifacts.{artifact_id}.checksum_sha256",
                        key="checksum_sha256",
                        value_a=checksum_a[:16] + "..." if checksum_a else "",
                        value_b=checksum_b[:16] + "..." if checksum_b else "",
                        description=f"Artifact '{artifact_id}' checksum changed",
                    ))
                
                # Compare other artifact fields
                for field in ["artifact_type", "source_path", "target_path"]:
                    value_a = artifact_a.get(field)
                    value_b = artifact_b.get(field)
                    
                    if value_a != value_b:
                        category.items.append(DiffItemV1(
                            diff_type=DiffType.CHANGED,
                            path=f"artifacts.{artifact_id}.{field}",
                            key=field,
                            value_a=value_a,
                            value_b=value_b,
                            description=f"Artifact '{artifact_id}' {field} changed",
                        ))
        
        category.count = len(category.items)
        return category
    
    def compare_manifest_metadata(
        self,
        manifest_a: Dict[str, Any],
        manifest_b: Dict[str, Any],
    ) -> DiffCategoryV1:
        """Compare manifest metadata (excluding artifacts)."""
        category = DiffCategoryV1(category="metadata")
        
        # Fields to compare (excluding artifacts and hash fields)
        metadata_fields = [
            "schema_version", "deployment_id", "job_id", "created_at",
            "created_by", "artifact_count", "deployment_target", "deployment_notes",
        ]
        
        for field in metadata_fields:
            value_a = manifest_a.get(field)
            value_b = manifest_b.get(field)
            
            if value_a != value_b:
                category.items.append(DiffItemV1(
                    diff_type=DiffType.CHANGED,
                    path=f"manifest.{field}",
                    key=field,
                    value_a=value_a,
                    value_b=value_b,
                    description=f"Manifest {field} changed",
                ))
        
        # Compare hash fields separately
        for hash_field in ["manifest_hash", "bundle_hash"]:
            hash_a = manifest_a.get(hash_field, "")
            hash_b = manifest_b.get(hash_field, "")
            
            if hash_a != hash_b:
                category.items.append(DiffItemV1(
                    diff_type=DiffType.CHANGED,
                    path=f"manifest.{hash_field}",
                    key=hash_field,
                    value_a=hash_a[:16] + "..." if hash_a else "",
                    value_b=hash_b[:16] + "..." if hash_b else "",
                    description=f"Manifest {hash_field} changed",
                ))
        
        category.count = len(category.items)
        return category
    
    def compare_strategy_reports(
        self,
        report_a: Optional[Dict[str, Any]],
        report_b: Optional[Dict[str, Any]],
    ) -> DiffCategoryV1:
        """Compare strategy reports (with metric redaction)."""
        category = DiffCategoryV1(category="strategy_report")
        
        if not report_a and not report_b:
            return category
        
        if report_a and not report_b:
            category.items.append(DiffItemV1(
                diff_type=DiffType.REMOVED,
                path="strategy_report",
                key="strategy_report",
                value_a="Present",
                description="Strategy report removed",
            ))
            category.count = 1
            return category
        
        if not report_a and report_b:
            category.items.append(DiffItemV1(
                diff_type=DiffType.ADDED,
                path="strategy_report",
                key="strategy_report",
                value_b="Present",
                description="Strategy report added",
            ))
            category.count = 1
            return category
        
        # Both reports exist, compare with metric redaction
        if self.redact_metrics:
            report_a = MetricRedactor.redact_dict(report_a)
            report_b = MetricRedactor.redact_dict(report_b)
        
        # Compare top-level fields
        diffs = self.compare_dicts(report_a, report_b, "strategy_report")
        category.items.extend(diffs)
        category.count = len(category.items)
        
        return category
    
    def generate_diff_report(
        self,
        bundle_a_dir: Path,
        bundle_b_dir: Path,
        report_id: Optional[str] = None,
    ) -> DiffReportV1:
        """
        Generate comprehensive diff report for two deployment bundles.
        
        Args:
            bundle_a_dir: Path to first deployment directory
            bundle_b_dir: Path to second deployment directory
            report_id: Optional report ID (auto-generated if None)
            
        Returns:
            DiffReportV1 with structured diff
        """
        from .bundle_resolver import BundleResolver
        
        # Generate report ID if not provided
        if report_id is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            report_id = f"diff_{timestamp}_{hashlib.sha256(str(bundle_a_dir).encode()).hexdigest()[:8]}"
        
        # Initialize resolver
        resolver = BundleResolver(outputs_root=self.outputs_root)
        
        # Resolve both bundles
        resolution_a = resolver.resolve_bundle(bundle_a_dir)
        resolution_b = resolver.resolve_bundle(bundle_b_dir)
        
        # Create diff report
        diff_report = DiffReportV1(
            report_id=report_id,
            compared_at=datetime.now().isoformat(),
            bundle_a_path=str(bundle_a_dir),
            bundle_b_path=str(bundle_b_dir),
            bundle_a_valid=resolution_a.is_valid,
            bundle_b_valid=resolution_b.is_valid,
        )
        
        # Set deployment IDs and job IDs if available
        if resolution_a.manifest:
            diff_report.bundle_a_deployment_id = resolution_a.manifest.deployment_id
            diff_report.bundle_a_job_id = resolution_a.manifest.job_id
        
        if resolution_b.manifest:
            diff_report.bundle_b_deployment_id = resolution_b.manifest.deployment_id
            diff_report.bundle_b_job_id = resolution_b.manifest.job_id
        
        # Collect validation errors
        if resolution_a.validation_errors:
            diff_report.validation_errors.extend([
                f"Bundle A: {error}" for error in resolution_a.validation_errors
            ])
        
        if resolution_b.validation_errors:
            diff_report.validation_errors.extend([
                f"Bundle B: {error}" for error in resolution_b.validation_errors
            ])
        
        # Only generate diffs if both bundles are valid
        if resolution_a.is_valid and resolution_b.is_valid:
            manifest_a = resolution_a.manifest
            manifest_b = resolution_b.manifest
            
            # Compare manifest metadata
            manifest_a_dict = manifest_a.model_dump()
            manifest_b_dict = manifest_b.model_dump()
            
            metadata_category = self.compare_manifest_metadata(manifest_a_dict, manifest_b_dict)
            if metadata_category.count > 0:
                diff_report.categories.append(metadata_category)
            
            # Compare artifacts
            artifacts_a = [artifact.model_dump() for artifact in manifest_a.artifacts]
            artifacts_b = [artifact.model_dump() for artifact in manifest_b.artifacts]
            
            artifacts_category = self.compare_artifacts(artifacts_a, artifacts_b)
            if artifacts_category.count > 0:
                diff_report.categories.append(artifacts_category)
            
            # Compare gate summaries
            if manifest_a.gate_summary and manifest_b.gate_summary:
                gate_category = self.compare_gate_summaries(
                    manifest_a.gate_summary,
                    manifest_b.gate_summary,
                )
                if gate_category.count > 0:
                    diff_report.categories.append(gate_category)
            
            # Compare strategy reports
            if manifest_a.strategy_report or manifest_b.strategy_report:
                strategy_category = self.compare_strategy_reports(
                    manifest_a.strategy_report,
                    manifest_b.strategy_report,
                )
                if strategy_category.count > 0:
                    diff_report.categories.append(strategy_category)
            
            # Compare other key artifacts if needed
            # (portfolio_config, admission_report, config_snapshot, input_manifest)
        
        # Calculate total differences
        total_differences = sum(category.count for category in diff_report.categories)
        diff_report.total_differences = total_differences
        
        # Compute diff hash
        diff_report.diff_hash = self.compute_diff_hash(diff_report)
        
        logger.info(f"Generated diff report {report_id} with {total_differences} differences")
        logger.info(f"Diff hash: {diff_report.diff_hash[:16]}...")
        
        return diff_report
    
    def write_diff_report(
        self,
        diff_report: DiffReportV1,
        output_dir: Optional[Path] = None,
    ) -> Path:
        """
        Write diff report to JSON file (evidence folder only).
        
        Args:
            diff_report: Diff report to write
            output_dir: Output directory (default: outputs/_dp_evidence/replay_compare_v1/)
            
        Returns:
            Path to written JSON file
        """
        if output_dir is None:
            output_dir = self.outputs_root / "_dp_evidence" / "replay_compare_v1"
        
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Create filename from report ID
        filename = f"{diff_report.report_id}.json"
        output_path = output_dir / filename
        
        # Convert to dict and write
        report_dict = diff_report.model_dump()
        
        import json
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(report_dict, f, indent=2, ensure_ascii=False)
        
        logger.info(f"Diff report written to {output_path}")
        return output_path


# ============================================================================
# CLI Interface
# ============================================================================

def main_cli():
    """Command-line interface for diff engine."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Generate deterministic diff reports for deployment bundles (no metric leakage)"
    )
    parser.add_argument(
        "bundle_a",
        type=Path,
        help="Path to first deployment directory"
    )
    parser.add_argument(
        "bundle_b",
        type=Path,
        help="Path to second deployment directory"
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Output directory for diff report (default: outputs/_dp_evidence/replay_compare_v1/)"
    )
    parser.add_argument(
        "--no-redact",
        action="store_true",
        help="Disable metric redaction (not recommended for Hybrid BC v1.1)"
    )
    parser.add_argument(
        "--outputs-root",
        type=Path,
        default=get_outputs_root(),
        help="Root outputs directory"
    )
    
    args = parser.parse_args()
    
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    
    # Check if bundles exist
    if not args.bundle_a.exists():
        print(f"Error: Bundle A not found: {args.bundle_a}")
        return 1
    
    if not args.bundle_b.exists():
        print(f"Error: Bundle B not found: {args.bundle_b}")
        return 1
    
    # Initialize diff engine
    diff_engine = DiffEngine(
        outputs_root=args.outputs_root,
        redact_metrics=not args.no_redact,
    )
    
    # Generate diff report
    print(f"Generating diff report for:")
    print(f"  Bundle A: {args.bundle_a}")
    print(f"  Bundle B: {args.bundle_b}")
    print(f"  Metric redaction: {not args.no_redact}")
    
    try:
        diff_report = diff_engine.generate_diff_report(args.bundle_a, args.bundle_b)
        
        print(f"\nDiff Report Summary:")
        print(f"  Report ID: {diff_report.report_id}")
        print(f"  Compared at: {diff_report.compared_at}")
        print(f"  Total differences: {diff_report.total_differences}")
        print(f"  Bundle A valid: {diff_report.bundle_a_valid}")
        print(f"  Bundle B valid: {diff_report.bundle_b_valid}")
        
        if diff_report.validation_errors:
            print(f"  Validation errors: {len(diff_report.validation_errors)}")
            for error in diff_report.validation_errors[:3]:  # Show first 3
                print(f"    - {error}")
        
        # Show diff categories
        print(f"\nDiff Categories:")
        for category in diff_report.categories:
            print(f"  - {category.category}: {category.count} differences")
        
        # Write to file
        output_path = diff_engine.write_diff_report(diff_report, args.output_dir)
        print(f"\nDiff report written to: {output_path}")
        print(f"Diff hash: {diff_report.diff_hash[:16]}...")
        
        return 0
        
    except Exception as e:
        print(f"Error generating diff report: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    import sys
    sys.exit(main_cli())
