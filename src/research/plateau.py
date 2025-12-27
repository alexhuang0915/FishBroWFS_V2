#!/usr/bin/env python3
"""
Plateau Identification for research results.

Phase 3A: Automatically identify stable parameter regions (plateaus) from a
grid of candidates, replacing human judgment of heatmaps.

Algorithm:
1. Load candidates (params dict + score) from winners.json or similar.
2. Normalize parameter dimensions to unit scale.
3. For each candidate, compute local neighborhood (k‑nearest neighbors).
4. Compute stability metric (variance of neighbor scores) and local average score.
5. Select candidate with best combined score (high average, low variance).
6. Define plateau as candidates within a distance threshold that have scores
   within a relative range of the selected candidate.
7. Output main candidate, backup candidates, plateau members, and stability report.

Deterministic: same input → same output.
No external randomness, no ML beyond basic statistics.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, List, Any, Tuple, Optional
import numpy as np


@dataclass(frozen=True)
class PlateauCandidate:
    """A single candidate with parameters and performance score."""
    candidate_id: str
    strategy_id: str
    symbol: str
    timeframe: str
    params: Dict[str, float]  # parameter name → value
    score: float
    metrics: Dict[str, Any]  # original metrics (net_profit, max_dd, trades, etc.)


@dataclass(frozen=True)
class PlateauRegion:
    """A connected region of parameter space with similar performance."""
    region_id: str
    members: List[PlateauCandidate]  # candidates belonging to this region
    centroid_params: Dict[str, float]  # average parameter values
    centroid_score: float  # average score of members
    score_variance: float  # variance of scores within region
    stability_score: float  # computed as centroid_score / (1 + score_variance)
    # distance threshold used to define region
    distance_threshold: float


@dataclass(frozen=True)
class PlateauReport:
    """Full plateau identification report."""
    candidates_seen: int
    param_names: List[str]
    selected_main: PlateauCandidate
    selected_backup: List[PlateauCandidate]  # ordered by preference
    plateau_region: PlateauRegion
    algorithm_version: str = "v1"
    notes: str = ""


def load_candidates_from_winners(winners_path: Path) -> List[PlateauCandidate]:
    """
    Load candidates from a winners.json (v2) file.

    Expected format:
        {
            "topk": [
                {
                    "candidate_id": "...",
                    "strategy_id": "...",
                    "symbol": "...",
                    "timeframe": "...",
                    "params": {...},
                    "score": ...,
                    "metrics": {...}
                },
                ...
            ]
        }
    """
    if not winners_path.exists():
        raise FileNotFoundError(f"winners.json not found at {winners_path}")

    with open(winners_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    topk = data.get("topk", [])
    if not topk:
        raise ValueError("winners.json contains empty 'topk' list")

    candidates = []
    for item in topk:
        candidate = PlateauCandidate(
            candidate_id=item.get("candidate_id", ""),
            strategy_id=item.get("strategy_id", ""),
            symbol=item.get("symbol", ""),
            timeframe=item.get("timeframe", ""),
            params=item.get("params", {}),
            score=float(item.get("score", 0.0)),
            metrics=item.get("metrics", {})
        )
        candidates.append(candidate)

    return candidates


def _normalize_params(candidates: List[PlateauCandidate]) -> Tuple[np.ndarray, List[str], Dict[str, Tuple[float, float]]]:
    """
    Convert parameter dicts to a normalized numpy matrix (zero mean, unit variance per dimension).

    Returns:
        X: (n_candidates, n_params) normalized matrix
        param_names: list of parameter names in order
        scaling_info: dict mapping param_name -> (mean, std) for later denormalization
    """
    if not candidates:
        raise ValueError("No candidates provided")

    # Collect all parameter names (union across candidates)
    param_names_set = set()
    for cand in candidates:
        param_names_set.update(cand.params.keys())
    param_names = sorted(param_names_set)

    if not param_names:
        # No parameters (edge case) – return dummy dimension
        X = np.zeros((len(candidates), 1))
        scaling_info = {"dummy": (0.0, 1.0)}
        return X, ["dummy"], scaling_info

    # Build raw matrix
    X_raw = np.zeros((len(candidates), len(param_names)))
    for i, cand in enumerate(candidates):
        for j, pname in enumerate(param_names):
            X_raw[i, j] = cand.params.get(pname, 0.0)

    # Normalize
    means = np.mean(X_raw, axis=0)
    stds = np.std(X_raw, axis=0)
    # Avoid division by zero
    stds[stds == 0] = 1.0
    X = (X_raw - means) / stds

    scaling_info = {}
    for idx, pname in enumerate(param_names):
        scaling_info[pname] = (means[idx], stds[idx])

    return X, param_names, scaling_info


def _compute_pairwise_distances(X: np.ndarray) -> np.ndarray:
    """Compute Euclidean distance matrix between all candidates."""
    n = X.shape[0]
    distances = np.zeros((n, n))
    for i in range(n):
        # vectorized computation of squared differences
        diff = X - X[i]
        distances[i, :] = np.sqrt(np.sum(diff ** 2, axis=1))
    return distances


def _find_plateau(
    candidates: List[PlateauCandidate],
    X: np.ndarray,
    param_names: List[str],
    distance_matrix: np.ndarray,
    k_neighbors: int = 5,
    score_threshold_rel: float = 0.1,
) -> PlateauReport:
    """
    Core plateau identification logic.

    Steps:
    1. For each candidate compute local stability (score variance among k‑nearest neighbors).
    2. Combine local average score and variance into a composite score.
    3. Select candidate with highest composite score.
    4. Grow region around selected candidate by including neighbors within a distance threshold
       that also have scores within relative threshold.
    5. Choose backup candidates as next best within region.
    """
    n = len(candidates)
    if n == 0:
        raise ValueError("No candidates")

    # Ensure k_neighbors <= n-1
    k = min(k_neighbors, n - 1) if n > 1 else 0

    scores = np.array([c.score for c in candidates])

    # For each candidate, find k‑nearest neighbors (excluding self)
    neighbor_indices = []
    neighbor_variances = []
    neighbor_avg_scores = []

    for i in range(n):
        if k == 0:
            neighbor_indices.append([i])
            neighbor_variances.append(0.0)
            neighbor_avg_scores.append(scores[i])
            continue

        # distances to all other candidates
        dists = distance_matrix[i]
        # get indices sorted by distance (skip self)
        sorted_idx = np.argsort(dists)
        # self is at distance zero, so first element is i
        nearest = sorted_idx[1:k+1]  # exclude self
        neighbor_indices.append(nearest.tolist())
        neighbor_scores = scores[nearest]
        neighbor_variances.append(np.var(neighbor_scores))
        neighbor_avg_scores.append(np.mean(neighbor_scores))

    # Composite score: average_score * (1 - normalized_variance)
    # Normalize variance across candidates to [0,1] range
    if n > 1 and max(neighbor_variances) > 0:
        norm_var = np.array(neighbor_variances) / max(neighbor_variances)
    else:
        norm_var = np.zeros(n)

    composite = np.array(neighbor_avg_scores) * (1.0 - norm_var)

    # Select candidate with highest composite score
    selected_idx = int(np.argmax(composite))
    selected = candidates[selected_idx]

    # Determine distance threshold as median distance to its k‑nearest neighbors
    if k > 0:
        neighbor_dists = distance_matrix[selected_idx][neighbor_indices[selected_idx]]
        distance_threshold = float(np.median(neighbor_dists)) * 1.5  # expand a bit
    else:
        distance_threshold = 0.0

    # Grow region: include all candidates within distance_threshold AND score within relative range
    region_indices = []
    for i in range(n):
        if distance_matrix[selected_idx, i] <= distance_threshold:
            # score within score_threshold_rel of selected score
            if abs(scores[i] - selected.score) <= score_threshold_rel * abs(selected.score):
                region_indices.append(i)

    region_members = [candidates[i] for i in region_indices]

    # Compute region centroid (average normalized parameters)
    if region_members:
        X_region = X[region_indices]
        centroid_normalized = np.mean(X_region, axis=0)
        # Convert centroid back to original parameter scale (requires scaling_info)
        # For simplicity we'll just use the selected candidate's params as centroid.
        centroid_params = selected.params
        centroid_score = float(np.mean(scores[region_indices]))
        region_score_var = float(np.var(scores[region_indices]))
    else:
        centroid_params = selected.params
        centroid_score = selected.score
        region_score_var = 0.0

    # Stability score = centroid_score / (1 + region_score_var)
    stability_score = centroid_score / (1.0 + region_score_var)

    plateau_region = PlateauRegion(
        region_id=f"plateau_{selected_idx}",
        members=region_members,
        centroid_params=centroid_params,
        centroid_score=centroid_score,
        score_variance=region_score_var,
        stability_score=stability_score,
        distance_threshold=distance_threshold,
    )

    # Select backup candidates: top‑3 scores within region (excluding main)
    region_scores_with_idx = [(i, scores[i]) for i in region_indices if i != selected_idx]
    region_scores_with_idx.sort(key=lambda x: x[1], reverse=True)
    backup_indices = [idx for idx, _ in region_scores_with_idx[:2]]  # at most two backups
    backup_candidates = [candidates[i] for i in backup_indices]

    report = PlateauReport(
        candidates_seen=n,
        param_names=param_names,
        selected_main=selected,
        selected_backup=backup_candidates,
        plateau_region=plateau_region,
        notes=f"k_neighbors={k}, score_threshold_rel={score_threshold_rel}",
    )
    return report


def identify_plateau_from_winners(winners_path: Path, **kwargs) -> PlateauReport:
    """
    High‑level entry point: load winners.json and run plateau identification.

    Keyword arguments are passed to _find_plateau (k_neighbors, score_threshold_rel).
    """
    candidates = load_candidates_from_winners(winners_path)
    X, param_names, _ = _normalize_params(candidates)
    distances = _compute_pairwise_distances(X)
    return _find_plateau(candidates, X, param_names, distances, **kwargs)


def save_plateau_report(report: PlateauReport, output_dir: Path) -> None:
    """Save plateau report and chosen parameters as JSON files."""
    output_dir.mkdir(parents=True, exist_ok=True)

    # Convert dataclasses to dicts for JSON serialization
    def dataclass_to_dict(obj):
        if hasattr(obj, "__dataclass_fields__"):
            d = asdict(obj)
            # Recursively convert nested dataclasses
            for k, v in d.items():
                if isinstance(v, list):
                    d[k] = [dataclass_to_dict(item) if hasattr(item, "__dataclass_fields__") else item for item in v]
                elif hasattr(v, "__dataclass_fields__"):
                    d[k] = dataclass_to_dict(v)
            return d
        return obj

    report_dict = dataclass_to_dict(report)

    # Plateau report
    plateau_path = output_dir / "plateau_report.json"
    with open(plateau_path, "w", encoding="utf-8") as f:
        json.dump(report_dict, f, indent=2, ensure_ascii=False)

    # Chosen parameters (main + backups)
    chosen = {
        "main": dataclass_to_dict(report.selected_main),
        "backups": dataclass_to_dict(report.selected_backup),
        "generated_at": "",  # caller can fill timestamp
    }
    chosen_path = output_dir / "chosen_params.json"
    with open(chosen_path, "w", encoding="utf-8") as f:
        json.dump(chosen, f, indent=2, ensure_ascii=False)

    print(f"Plateau report saved to {plateau_path}")
    print(f"Chosen parameters saved to {chosen_path}")


if __name__ == "__main__":
    # Simple CLI for testing
    import sys
    if len(sys.argv) != 2:
        print("Usage: python plateau.py <winners.json>")
        sys.exit(1)

    winners = Path(sys.argv[1])
    if not winners.exists():
        print(f"File not found: {winners}")
        sys.exit(1)

    report = identify_plateau_from_winners(winners)
    save_plateau_report(report, winners.parent)