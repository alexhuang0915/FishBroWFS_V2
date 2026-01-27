from __future__ import annotations

import argparse
import json
import os
import random
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _now_tag() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _load_yaml(path: Path) -> dict[str, Any]:
    import yaml  # type: ignore

    doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(doc, dict):
        raise ValueError(f"YAML must be a mapping: {path}")
    return doc


def _dump_yaml(path: Path, doc: dict[str, Any]) -> None:
    import yaml  # type: ignore

    path.write_text(yaml.safe_dump(doc, sort_keys=False), encoding="utf-8")


def _list_auto_runs(artifacts_root: Path) -> list[Path]:
    p = artifacts_root / "auto_runs"
    if not p.exists():
        return []
    return sorted([d for d in p.iterdir() if d.is_dir() and d.name.startswith("auto_")], key=lambda x: x.stat().st_mtime)


def _latest_auto_run_after(artifacts_root: Path, before: set[str]) -> Path | None:
    after = _list_auto_runs(artifacts_root)
    for d in reversed(after):
        if d.name not in before:
            return d
    # Fallback: latest by mtime.
    return after[-1] if after else None


def _run(cmd: list[str], *, env: dict[str, str] | None = None, cwd: Path | None = None) -> None:
    p = subprocess.run(cmd, env=env, cwd=str(cwd) if cwd else None)
    if p.returncode != 0:
        raise RuntimeError(f"Command failed ({p.returncode}): {' '.join(cmd)}")


def _product(vals: list[int]) -> int:
    out = 1
    for v in vals:
        out *= int(v)
    return out


def _param_grid_size(strategy_doc: dict[str, Any]) -> int:
    params = strategy_doc.get("parameters") or {}
    if not isinstance(params, dict):
        return 1
    sizes: list[int] = []
    for _, spec in params.items():
        if not isinstance(spec, dict):
            continue
        t = str(spec.get("type") or "").strip().lower()
        if t != "choice":
            continue
        choices = spec.get("choices") or []
        if not isinstance(choices, list):
            choices = [choices]
        sizes.append(max(1, len([x for x in choices if x is not None])))
    return _product(sizes) if sizes else 1


def _set_choices(doc: dict[str, Any], key: str, values: list[float]) -> None:
    params = doc.setdefault("parameters", {})
    if not isinstance(params, dict):
        raise ValueError("strategy.parameters must be a mapping")
    spec = params.get(key) or {}
    if not isinstance(spec, dict):
        spec = {}
    spec["type"] = "choice"
    if "default" not in spec:
        spec["default"] = values[0]
    spec["choices"] = values
    params[key] = spec


def _freeze_param(doc: dict[str, Any], key: str, value: float) -> None:
    _set_choices(doc, key, [float(value)])
    doc["parameters"][key]["default"] = float(value)


def _ensure_small_grid(doc: dict[str, Any], *, max_grid: int) -> None:
    """
    Keep total parameter combinations under max_grid by freezing unused/low-priority params.
    V1 priority: keep thresholds and exit stop; freeze entry_atr_mult when entry.mode == market.
    """
    static = ((doc.get("static_params") or {}).get("dsl") or {})
    entry = static.get("entry") if isinstance(static.get("entry"), dict) else {}
    entry_mode = str(entry.get("mode") or "market").strip().lower()
    if entry_mode != "stop":
        # Not used when market mode: freeze to 1 to avoid blowing up WFS grid.
        if "entry_atr_mult" in (doc.get("parameters") or {}):
            _freeze_param(doc, "entry_atr_mult", 1.0)

    size = _param_grid_size(doc)
    if size <= max_grid:
        return

    # Freeze weights (most expensive) before thresholds/stops.
    for k in ["w_corr", "w_spread", "w_rel_vol"]:
        if k in (doc.get("parameters") or {}):
            spec = doc["parameters"][k]
            try:
                v = float(spec.get("default", 0.0))
            except Exception:
                v = 0.0
            _freeze_param(doc, k, v)
            size = _param_grid_size(doc)
            if size <= max_grid:
                return

    # Freeze stop if still too big.
    if "exit_atr_mult" in (doc.get("parameters") or {}):
        spec = doc["parameters"]["exit_atr_mult"]
        try:
            v = float(spec.get("default", 2.0))
        except Exception:
            v = 2.0
        _freeze_param(doc, "exit_atr_mult", v)


@dataclass(frozen=True)
class ClosureRule:
    min_grade: str
    min_trades: int


def _grade_val(g: str | None) -> int:
    order = {"A": 0, "B": 1, "C": 2, "D": 3}
    return order.get((g or "").strip().upper(), 99)


def _meets_grade(g: str | None, min_g: str) -> bool:
    return _grade_val(g) <= _grade_val(min_g)


def _best_rows_by_instrument(summary: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows = summary.get("rows") or []
    if not isinstance(rows, list):
        return {}
    best: dict[str, dict[str, Any]] = {}

    def key(r: dict[str, Any]):
        return (
            _grade_val(r.get("grade")),
            -(r.get("score_total_weighted") if r.get("score_total_weighted") is not None else float("-inf")),
            -(r.get("trades") if r.get("trades") is not None else float("-inf")),
        )

    for r in rows:
        if not isinstance(r, dict):
            continue
        d1 = str(r.get("data1") or "").strip()
        if not d1:
            continue
        if d1 not in best or key(r) < key(best[d1]):
            best[d1] = r
    return best


def _closure_satisfied(best: dict[str, dict[str, Any]], *, instruments: list[str], rule: ClosureRule) -> tuple[bool, list[str]]:
    missing: list[str] = []
    for ins in instruments:
        r = best.get(ins)
        if not r:
            missing.append(f"{ins}: no result row")
            continue
        if not _meets_grade(r.get("grade"), rule.min_grade):
            missing.append(f"{ins}: grade {r.get('grade')} < {rule.min_grade} (not met)")
            continue
        try:
            tr = int(r.get("trades") or 0)
        except Exception:
            tr = 0
        if tr < rule.min_trades:
            missing.append(f"{ins}: trades {tr} < {rule.min_trades} (not met)")
            continue
    return (len(missing) == 0), missing


def _mutate_weights(doc: dict[str, Any], rng: random.Random) -> dict[str, float]:
    """
    Simple, deterministic-ish search: pick one weight triple per iteration.
    Freeze weights to single values so WFS grid stays focused on thresholds/stops.
    """
    # Candidate sets (small but expressive)
    w_corr = rng.choice([-2.0, -1.0, 0.0, 1.0, 2.0])
    w_spread = rng.choice([-2.0, -1.0, 0.0, 1.0, 2.0])
    w_rel_vol = rng.choice([-2.0, -1.0, 0.0])
    for k, v in [("w_corr", w_corr), ("w_spread", w_spread), ("w_rel_vol", w_rel_vol)]:
        if k in (doc.get("parameters") or {}):
            _freeze_param(doc, k, v)
    return {"w_corr": w_corr, "w_spread": w_spread, "w_rel_vol": w_rel_vol}


def _mutate_thresholds(doc: dict[str, Any], rng: random.Random) -> dict[str, list[float]]:
    """
    Keep thresholds as a small local search set.
    """
    long_center = rng.choice([0.0, 0.3, 0.5, 0.8, 1.0])
    short_center = -long_center
    long_choices = sorted({round(long_center + d, 2) for d in (-0.3, 0.0, 0.3)})
    short_choices = sorted({round(short_center + d, 2) for d in (-0.3, 0.0, 0.3)})
    _set_choices(doc, "th_long", long_choices)
    _set_choices(doc, "th_short", short_choices)
    doc["parameters"]["th_long"]["default"] = float(long_center)
    doc["parameters"]["th_short"]["default"] = float(short_center)
    return {"th_long": long_choices, "th_short": short_choices}


def main() -> int:
    ap = argparse.ArgumentParser(description="Autonomous optimizer loop for configs/strategies/dsl_linear_v1.yaml")
    ap.add_argument("--spec", type=Path, required=True, help="Portfolio spec path")
    ap.add_argument("--snapshot-season", type=str, required=True, help="Cache snapshot season for auto_cli --season")
    ap.add_argument("--tfs", type=str, default="15,30,60,120,240")
    ap.add_argument("--max-workers", type=int, default=10)
    ap.add_argument("--timeout-sec", type=float, default=28800)
    ap.add_argument("--iterations", type=int, default=10)
    ap.add_argument("--min-grade", type=str, default="B")
    ap.add_argument("--min-trades", type=int, default=120)
    ap.add_argument("--seed", type=int, default=20260127)
    ap.add_argument("--no-finalize", action="store_true", default=True)
    args = ap.parse_args()

    repo_root = Path.cwd()
    artifacts_root = repo_root / "outputs" / "artifacts"
    strategy_path = repo_root / "configs" / "strategies" / "dsl_linear_v1.yaml"

    if not strategy_path.exists():
        raise SystemExit(f"Missing strategy config: {strategy_path}")

    run_dir = repo_root / "outputs" / "optimizer" / f"dsl_linear_v1_{_now_tag()}"
    run_dir.mkdir(parents=True, exist_ok=True)
    state_path = run_dir / "run_state.json"

    original = strategy_path.read_text(encoding="utf-8")
    (run_dir / "original_dsl_linear_v1.yaml").write_text(original, encoding="utf-8")

    rng = random.Random(int(args.seed))
    rule = ClosureRule(min_grade=str(args.min_grade).strip().upper(), min_trades=int(args.min_trades))

    # Determine target instruments from spec (we use it for closure check).
    spec_doc = _load_yaml(args.spec)
    instruments = [str(x).strip() for x in (spec_doc.get("instrument_ids") or []) if str(x).strip()]

    state: dict[str, Any] = {
        "version": "1.0",
        "generated_at": _iso_now(),
        "spec": str(args.spec),
        "snapshot_season": args.snapshot_season,
        "tfs": args.tfs,
        "max_workers": args.max_workers,
        "timeout_sec": args.timeout_sec,
        "iterations": args.iterations,
        "closure": {"min_grade": rule.min_grade, "min_trades": rule.min_trades, "instruments": instruments},
        "history": [],
        "best": None,
    }

    before_dirs = {d.name for d in _list_auto_runs(artifacts_root)}

    try:
        for it in range(int(args.iterations)):
            # Load, mutate, constrain.
            doc = _load_yaml(strategy_path)
            weights = _mutate_weights(doc, rng)
            thresh = _mutate_thresholds(doc, rng)
            _ensure_small_grid(doc, max_grid=10_000)
            grid_size = _param_grid_size(doc)

            # Persist iteration config.
            iter_dir = run_dir / f"iter_{it:03d}"
            iter_dir.mkdir(parents=True, exist_ok=True)
            _dump_yaml(iter_dir / "dsl_linear_v1.yaml", doc)

            # Apply to live config (registry points here).
            _dump_yaml(strategy_path, doc)

            # Run auto WFS (matrix).
            cmd = [
                sys.executable,
                "-m",
                "control.auto_cli",
                "--spec",
                str(args.spec),
                "--season",
                str(args.snapshot_season),
                "--tfs",
                str(args.tfs),
                "--data2-mode",
                "matrix",
                "--max-workers",
                str(int(args.max_workers)),
                "--timeout-sec",
                str(float(args.timeout_sec)),
            ]
            if bool(args.no_finalize):
                cmd.append("--no-finalize")

            _run(cmd, env={**os.environ, "PYTHONPATH": str(repo_root / "src")}, cwd=repo_root)

            # Discover the new auto-run.
            auto_run = _latest_auto_run_after(artifacts_root, before_dirs)
            if auto_run is None:
                raise RuntimeError("No auto-run directory produced")
            before_dirs.add(auto_run.name)

            # Produce matrix summary for this auto-run dir (writes into auto_run dir).
            _run(
                [sys.executable, "-m", "control.matrix_summary_cli", "--auto-run", auto_run.name],
                env={**os.environ, "PYTHONPATH": str(repo_root / "src")},
                cwd=repo_root,
            )
            summary_path = auto_run / "matrix_summary.json"
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            best = _best_rows_by_instrument(summary)
            ok, missing = _closure_satisfied(best, instruments=instruments, rule=rule)

            record = {
                "iter": it,
                "generated_at": _iso_now(),
                "grid_size": grid_size,
                "weights": weights,
                "thresholds": thresh,
                "auto_run_id": auto_run.name,
                "best_by_instrument": {k: {"grade": v.get("grade"), "trades": v.get("trades"), "score": v.get("score_total_weighted"), "timeframe": v.get("timeframe"), "data2": v.get("data2"), "job_id": v.get("job_id")} for k, v in best.items()},
                "closure_ok": ok,
                "closure_missing": missing,
            }
            state["history"].append(record)

            # Update best: by (closure_ok, sum(score), sum(trades))
            def _sum_score(rows: dict[str, dict[str, Any]]) -> float:
                s = 0.0
                for ins in instruments:
                    r = rows.get(ins) or {}
                    v = r.get("score_total_weighted")
                    if isinstance(v, (int, float)):
                        s += float(v)
                return s

            def _sum_trades(rows: dict[str, dict[str, Any]]) -> int:
                s = 0
                for ins in instruments:
                    r = rows.get(ins) or {}
                    try:
                        s += int(r.get("trades") or 0)
                    except Exception:
                        pass
                return s

            cur_score = _sum_score(best)
            cur_trades = _sum_trades(best)
            best_rec = state.get("best")
            if best_rec is None:
                state["best"] = {**record, "sum_score": cur_score, "sum_trades": cur_trades}
            else:
                prev_ok = bool(best_rec.get("closure_ok"))
                prev_score = float(best_rec.get("sum_score") or 0.0)
                prev_trades = int(best_rec.get("sum_trades") or 0)
                if (ok and not prev_ok) or (ok == prev_ok and (cur_score, cur_trades) > (prev_score, prev_trades)):
                    state["best"] = {**record, "sum_score": cur_score, "sum_trades": cur_trades}

            state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")

            if ok:
                break

    finally:
        # Leave the best-known config in place, but always keep original snapshot for rollback.
        state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")
        # Also keep a copy of the final live config for the run record.
        shutil.copy2(strategy_path, run_dir / "final_dsl_linear_v1.yaml")

    print(f"[optimizer] state: {state_path}")
    best = state.get("best") or {}
    print(f"[optimizer] best auto_run_id={best.get('auto_run_id')} closure_ok={best.get('closure_ok')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

