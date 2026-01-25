from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import yaml


@dataclass(frozen=True)
class HardGate:
    id: str
    metric: str
    op: str
    threshold: float
    fail_reason: str


@dataclass(frozen=True)
class Grading:
    score_metric: str
    cutoffs: dict[str, float]


@dataclass(frozen=True)
class WFSPolicy:
    schema_version: str
    name: str
    description: str
    hard_gates: tuple[HardGate, ...]
    grading: Grading


def load_wfs_policy(path: Path) -> WFSPolicy:
    doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    schema_version = str(doc.get("schema_version") or "").strip()
    name = str(doc.get("name") or "").strip()
    description = str(doc.get("description") or "").strip()
    if schema_version != "1.0":
        raise ValueError(f"Unsupported policy schema_version: {schema_version!r}")
    if not name:
        raise ValueError("Policy missing name")

    gates_raw = doc.get("hard_gates") or []
    if not isinstance(gates_raw, list) or not gates_raw:
        raise ValueError("Policy hard_gates must be a non-empty list")

    hard_gates: list[HardGate] = []
    for g in gates_raw:
        if not isinstance(g, dict):
            raise ValueError("Policy hard_gates entries must be objects")
        gid = str(g.get("id") or "").strip()
        metric = str(g.get("metric") or "").strip()
        op = str(g.get("op") or "").strip()
        if op not in {">=", "<=", ">", "<"}:
            raise ValueError(f"Unsupported gate op: {op!r}")
        try:
            threshold = float(g.get("threshold"))
        except Exception as exc:
            raise ValueError(f"Invalid gate threshold for {gid or metric}: {g.get('threshold')!r}") from exc
        fail_reason = str(g.get("fail_reason") or "").strip() or f"{gid or metric} gate failed"
        if not gid or not metric:
            raise ValueError("Gate requires id and metric")
        hard_gates.append(HardGate(id=gid, metric=metric, op=op, threshold=threshold, fail_reason=fail_reason))

    grading_raw = doc.get("grading") or {}
    if not isinstance(grading_raw, dict):
        raise ValueError("Policy grading must be an object")
    score_metric = str(grading_raw.get("score_metric") or "total_weighted").strip()
    cutoffs_raw = grading_raw.get("cutoffs") or {}
    if not isinstance(cutoffs_raw, dict):
        raise ValueError("Policy grading.cutoffs must be an object")
    cutoffs: dict[str, float] = {}
    for k, v in cutoffs_raw.items():
        try:
            cutoffs[str(k)] = float(v)
        except Exception as exc:
            raise ValueError(f"Invalid grading cutoff for {k!r}: {v!r}") from exc
    if not cutoffs:
        cutoffs = {"A": 80.0, "B": 65.0, "C": 50.0}

    return WFSPolicy(
        schema_version=schema_version,
        name=name,
        description=description,
        hard_gates=tuple(hard_gates),
        grading=Grading(score_metric=score_metric, cutoffs=cutoffs),
    )


def evaluate_hard_gates(policy: WFSPolicy, raw_metrics: dict[str, Any]) -> tuple[list[str], list[str]]:
    failed_ids: list[str] = []
    fail_reasons: list[str] = []
    for gate in policy.hard_gates:
        if gate.metric not in raw_metrics:
            failed_ids.append(gate.id)
            fail_reasons.append(f"{gate.fail_reason} (missing metric)")
            continue
        try:
            value = float(raw_metrics[gate.metric])
        except Exception:
            failed_ids.append(gate.id)
            fail_reasons.append(f"{gate.fail_reason} (non-numeric metric)")
            continue

        ok = _compare(value, gate.op, gate.threshold)
        if not ok:
            failed_ids.append(gate.id)
            fail_reasons.append(gate.fail_reason)
    return failed_ids, fail_reasons


def grade_from_score(policy: WFSPolicy, score: float, *, failed_gate_ids: Iterable[str]) -> str:
    if any(True for _ in failed_gate_ids):
        return "D"
    # Highest cutoff wins. Unknown keys are ignored.
    order = [("A",), ("B",), ("C",)]
    for letter in ("A", "B", "C"):
        cutoff = policy.grading.cutoffs.get(letter)
        if cutoff is None:
            continue
        if score >= float(cutoff):
            return letter
    return "C"


def _compare(value: float, op: str, threshold: float) -> bool:
    if op == ">=":
        return value >= threshold
    if op == "<=":
        return value <= threshold
    if op == ">":
        return value > threshold
    if op == "<":
        return value < threshold
    raise ValueError(f"Unsupported op: {op}")

