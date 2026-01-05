"""
Correlation Gate - Enforces pairwise correlation limit between candidate strategies.

Deterministic: input order does not affect output.
Tie‑break: lower score rejected; if equal score, lexicographically larger run_id rejected.
"""
import numpy as np
from typing import Dict, List, Tuple, Optional, Set
from dataclasses import dataclass
import json
from pathlib import Path


@dataclass
class CorrelationViolation:
    """Record of a correlation violation between two runs."""
    run_id_a: str
    run_id_b: str
    correlation: float  # absolute value
    threshold: float


@dataclass
class CorrelationGateResult:
    """Result of applying correlation gate to a set of candidates."""
    admitted_run_ids: List[str]
    rejected_run_ids: List[str]
    violations: List[CorrelationViolation]
    correlation_matrix: Dict[str, Dict[str, float]]  # run_id -> run_id -> corr

    def write_evidence(self, output_dir: Path) -> None:
        """Write correlation gate evidence files."""
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # correlation_matrix.json
        matrix_data = {}
        for rid_a, row in self.correlation_matrix.items():
            matrix_data[rid_a] = {rid_b: float(val) for rid_b, val in row.items()}
        
        matrix_path = output_dir / "correlation_matrix.json"
        with open(matrix_path, "w", encoding="utf-8") as f:
            json.dump(matrix_data, f, indent=2, sort_keys=True)
        
        # correlation_violations.json
        violations_data = [
            {
                "run_id_a": v.run_id_a,
                "run_id_b": v.run_id_b,
                "correlation": v.correlation,
                "threshold": v.threshold
            }
            for v in self.violations
        ]
        violations_path = output_dir / "correlation_violations.json"
        with open(violations_path, "w", encoding="utf-8") as f:
            json.dump(violations_data, f, indent=2, sort_keys=True)
        
        # admitted_run_ids.json
        admitted_path = output_dir / "admitted_run_ids.json"
        with open(admitted_path, "w", encoding="utf-8") as f:
            json.dump(self.admitted_run_ids, f, indent=2)
        
        # rejected_run_ids.json
        rejected_path = output_dir / "rejected_run_ids.json"
        with open(rejected_path, "w", encoding="utf-8") as f:
            json.dump(self.rejected_run_ids, f, indent=2)


class CorrelationGate:
    """Gate that rejects strategies with excessive pairwise correlation."""
    
    def __init__(self, max_pairwise_correlation: float, min_overlap_days: int = 60):
        """
        Args:
            max_pairwise_correlation: threshold (0 < value < 1)
            min_overlap_days: minimum overlapping days required to compute correlation
        """
        self.max_pairwise_correlation = max_pairwise_correlation
        self.min_overlap_days = min_overlap_days
    
    def evaluate(
        self,
        candidate_run_ids: List[str],
        returns_series: Dict[str, Tuple[List[str], List[float]]],  # run_id -> (dates, returns)
        scores: Dict[str, float]
    ) -> CorrelationGateResult:
        """
        Apply correlation gate to candidates.
        
        Steps:
        1. Sort candidate_run_ids deterministically.
        2. For each pair, compute Pearson correlation on aligned returns.
        3. If abs(corr) > threshold, record violation.
        4. Resolve violations: reject lower score; tie -> reject lexicographically larger run_id.
        5. Iterate until no violations remain.
        
        Returns:
            CorrelationGateResult with admitted/rejected lists and evidence.
        """
        # 1. Deterministic ordering
        sorted_candidates = sorted(candidate_run_ids)
        
        # 2. Compute correlation matrix
        corr_matrix, valid_pairs = self._compute_correlation_matrix(sorted_candidates, returns_series)
        
        # 3. Identify violations
        violations = self._find_violations(sorted_candidates, corr_matrix, valid_pairs)
        
        # 4. Resolve violations iteratively
        admitted = set(sorted_candidates)
        rejected = set()
        violation_records = []
        
        # Sort violations by severity (higher correlation first) for deterministic resolution
        sorted_violations = sorted(
            violations,
            key=lambda v: (abs(v.correlation), -scores.get(v.run_id_a, 0), -scores.get(v.run_id_b, 0)),
            reverse=True
        )
        
        for viol in sorted_violations:
            if viol.run_id_a not in admitted or viol.run_id_b not in admitted:
                # Already rejected one of them
                continue
            
            # Decide which to reject
            reject_id = self._choose_run_to_reject(viol.run_id_a, viol.run_id_b, scores)
            admitted.remove(reject_id)
            rejected.add(reject_id)
            violation_records.append(viol)
        
        # 5. Final admitted list (sorted)
        admitted_sorted = sorted(admitted)
        rejected_sorted = sorted(rejected)
        
        return CorrelationGateResult(
            admitted_run_ids=admitted_sorted,
            rejected_run_ids=rejected_sorted,
            violations=violation_records,
            correlation_matrix=corr_matrix
        )
    
    def _compute_correlation_matrix(
        self,
        run_ids: List[str],
        returns_series: Dict[str, Tuple[List[str], List[float]]]
    ) -> Tuple[Dict[str, Dict[str, float]], Dict[Tuple[str, str], bool]]:
        """
        Compute pairwise Pearson correlation matrix.
        
        Returns:
            - corr_matrix: dict of dict, symmetric, diagonal = 1.0
            - valid_pairs: dict mapping (id_a, id_b) -> True if correlation could be computed
        """
        # Preprocess returns into numpy arrays with aligned dates
        from collections import defaultdict
        import pandas as pd
        
        # Convert to pandas Series for alignment
        series_dict = {}
        for rid in run_ids:
            if rid not in returns_series:
                # Missing returns -> cannot compute correlation; treat as zero variance?
                # We'll skip pairs involving this run_id (they will be rejected elsewhere)
                continue
            dates, returns = returns_series[rid]
            # Assume dates are ISO strings; convert to datetime
            try:
                ts = pd.to_datetime(dates)
                series_dict[rid] = pd.Series(returns, index=ts, name=rid)
            except Exception:
                # If parsing fails, skip
                continue
        
        # Build matrix
        corr_matrix = {rid: {} for rid in run_ids}
        valid_pairs = {}
        
        for i, rid_a in enumerate(run_ids):
            corr_matrix[rid_a][rid_a] = 1.0
            if rid_a not in series_dict:
                continue
            series_a = series_dict[rid_a]
            for rid_b in run_ids[i+1:]:
                if rid_b not in series_dict:
                    valid_pairs[(rid_a, rid_b)] = False
                    continue
                series_b = series_dict[rid_b]
                
                # Align by date intersection
                aligned = pd.concat([series_a, series_b], axis=1).dropna()
                if len(aligned) < self.min_overlap_days:
                    # Insufficient overlap -> treat as invalid
                    valid_pairs[(rid_a, rid_b)] = False
                    continue
                
                # Compute Pearson correlation
                corr = aligned.iloc[:, 0].corr(aligned.iloc[:, 1])
                if np.isnan(corr):
                    corr = 0.0  # fallback
                
                corr_matrix[rid_a][rid_b] = corr
                corr_matrix[rid_b][rid_a] = corr
                valid_pairs[(rid_a, rid_b)] = True
        
        return corr_matrix, valid_pairs
    
    def _find_violations(
        self,
        run_ids: List[str],
        corr_matrix: Dict[str, Dict[str, float]],
        valid_pairs: Dict[Tuple[str, str], bool]
    ) -> List[CorrelationViolation]:
        """Identify pairs where absolute correlation exceeds threshold."""
        violations = []
        for i, rid_a in enumerate(run_ids):
            for rid_b in run_ids[i+1:]:
                if not valid_pairs.get((rid_a, rid_b), False):
                    continue
                corr = corr_matrix[rid_a].get(rid_b)
                if corr is None:
                    continue
                if abs(corr) > self.max_pairwise_correlation:
                    violations.append(CorrelationViolation(
                        run_id_a=rid_a,
                        run_id_b=rid_b,
                        correlation=corr,
                        threshold=self.max_pairwise_correlation
                    ))
        return violations
    
    def _choose_run_to_reject(self, run_id_a: str, run_id_b: str, scores: Dict[str, float]) -> str:
        """
        Deterministic tie‑break:
        - Reject lower score.
        - If scores equal, reject lexicographically larger run_id.
        """
        score_a = scores.get(run_id_a, 0.0)
        score_b = scores.get(run_id_b, 0.0)
        
        if score_a < score_b:
            return run_id_a
        elif score_b < score_a:
            return run_id_b
        else:
            # Equal score, reject lexicographically larger
            return max(run_id_a, run_id_b)
    