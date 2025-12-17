#!/usr/bin/env python3
"""
FishBro WFS Perf Harness (Red Team Spec v1.0)
狀態: ✅ File-based IPC / JIT-First / Observable
用途: 量測 JIT Grid Runner 的穩態吞吐量 (Steady-state Throughput)

修正紀錄:
- v1.1: 修復 numpy generator abs 錯誤
- v1.2: Hotfix: 解決 subprocess Import Error，強制注入 PYTHONPATH 並增強 debug info
"""
import os
import sys
import time
import gc
import json
import cProfile
import argparse
import subprocess
import tempfile
import statistics
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import List, Dict, Any, Optional

import numpy as np

from FishBroWFS_V2.perf.cost_model import estimate_seconds
from FishBroWFS_V2.perf.profile_report import _format_profile_report

# ==========================================
# 1. 配置與常數 (Tiers)
# ==========================================

@dataclass
class PerfConfig:
    name: str
    n_bars: int
    n_params: int
    hot_runs: int
    timeout: int
    disable_jit: bool
    sort_params: bool

# Baseline Tier (default): Fast, suitable for commit-to-commit comparison
# Can be overridden via FISHBRO_PERF_BARS and FISHBRO_PERF_PARAMS env vars
TIER_JIT_BARS = int(os.environ.get("FISHBRO_PERF_BARS", "20000"))
TIER_JIT_PARAMS = int(os.environ.get("FISHBRO_PERF_PARAMS", "1000"))
TIER_JIT_HOT_RUNS = int(os.environ.get("FISHBRO_PERF_HOTRUNS", "5"))
TIER_JIT_TIMEOUT = int(os.environ.get("FISHBRO_PERF_TIMEOUT_S", "600"))

# Stress Tier: Optional, for extreme throughput testing (requires larger timeout or skip-cold)
TIER_STRESS_BARS = int(os.environ.get("FISHBRO_PERF_STRESS_BARS", "200000"))
TIER_STRESS_PARAMS = int(os.environ.get("FISHBRO_PERF_STRESS_PARAMS", "10000"))

TIER_TOY_BARS = 2_000
TIER_TOY_PARAMS = 10
TIER_TOY_HOT_RUNS = 1
TIER_TOY_TIMEOUT = 60

# Warmup compile tier (for skip-cold mode)
TIER_WARMUP_COMPILE_BARS = 2_000
TIER_WARMUP_COMPILE_PARAMS = 200

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

# ==========================================
# 2. 資料生成 (Deterministic)
# ==========================================

def generate_synthetic_data(n_bars: int, seed: int = 42) -> Dict[str, np.ndarray]:
    """
    Generate synthetic OHLC data for perf harness.
    
    Uses float32 for Stage0/perf optimization (memory bandwidth reduction).
    """
    from FishBroWFS_V2.config.dtypes import PRICE_DTYPE_STAGE0
    
    rng = np.random.default_rng(seed)
    close = 10000 + np.cumsum(rng.standard_normal(n_bars)) * 10
    high = close + np.abs(rng.standard_normal(n_bars)) * 5
    low = close - np.abs(rng.standard_normal(n_bars)) * 5
    open_ = (high + low) / 2 + rng.standard_normal(n_bars)
    
    high = np.maximum(high, np.maximum(open_, close))
    low = np.minimum(low, np.minimum(open_, close))
    
    # Use float32 for perf harness (Stage0 optimization)
    data = {
        "open": open_.astype(PRICE_DTYPE_STAGE0),
        "high": high.astype(PRICE_DTYPE_STAGE0),
        "low": low.astype(PRICE_DTYPE_STAGE0),
        "close": close.astype(PRICE_DTYPE_STAGE0),
    }
    
    for k, v in data.items():
        if not v.flags['C_CONTIGUOUS']:
            data[k] = np.ascontiguousarray(v, dtype=PRICE_DTYPE_STAGE0)
    return data

def generate_params(n_params: int, seed: int = 999) -> np.ndarray:
    """
    Generate parameter matrix for perf harness.
    
    Uses float32 for Stage0 optimization (memory bandwidth reduction).
    """
    from FishBroWFS_V2.config.dtypes import PRICE_DTYPE_STAGE0
    
    rng = np.random.default_rng(seed)
    w1 = rng.integers(10, 100, size=n_params)
    w2 = rng.integers(5, 50, size=n_params)
    # runner_grid contract: params_matrix must be (n, >=3)
    # Provide a minimal 3-column schema for perf harness.
    w3 = rng.integers(2, 30, size=n_params)
    params = np.column_stack((w1, w2, w3)).astype(PRICE_DTYPE_STAGE0)
    if not params.flags['C_CONTIGUOUS']:
        params = np.ascontiguousarray(params, dtype=PRICE_DTYPE_STAGE0)
    return params

# ==========================================
# 3. Worker 邏輯 (Child Process)
# ==========================================

def worker_log(msg: str):
    print(f"[worker] {msg}", flush=True)


def _env_flag(name: str) -> bool:
    return os.environ.get(name, "").strip() == "1"


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, str(default)))
    except Exception:
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, str(default)))
    except Exception:
        return default


# NOTE: _format_profile_report moved to src/FishBroWFS_V2/perf/profile_report.py

def _run_microbench_numba_indicators(closes: np.ndarray, hot_runs: int) -> Dict[str, Any]:
    """
    Perf-only microbench:
      - Prove Numba is active in worker process.
      - Measure pure numeric kernels (no Python object loop) baseline.
    """
    try:
        import numba as nb  # type: ignore
    except Exception:  # pragma: no cover
        return {"microbench": "numba_missing"}

    from FishBroWFS_V2.indicators import numba_indicators as ni  # type: ignore

    # Use a fixed window; keep deterministic and cheap.
    length = 14
    x = np.ascontiguousarray(closes, dtype=np.float64)

    # Warmup compile (first call triggers compilation if JIT enabled).
    _ = ni.rolling_max(x, length)

    # Hot runs
    times: List[float] = []
    for _i in range(max(1, hot_runs)):
        t0 = time.perf_counter()
        _ = ni.rolling_max(x, length)
        times.append(time.perf_counter() - t0)

    best = min(times) if times else 0.0
    n = int(x.shape[0])
    # rolling_max visits each element once -> treat as "ops" ~= n
    tput = (n / best) if best > 0 else 0.0
    return {
        "microbench": "rolling_max",
        "n": n,
        "best_s": best,
        "ops_per_s": tput,
        "nb_disable_jit": int(getattr(nb.config, "DISABLE_JIT", -1)),
    }


def run_worker(
    npz_path: str,
    hot_runs: int,
    skip_cold: bool = False,
    warmup_bars: int = 0,
    warmup_params: int = 0,
    microbench: bool = False,
):
    try:
        # Stage P2-1.6: Parse trigger_rate env var
        trigger_rate = _env_float("FISHBRO_PERF_TRIGGER_RATE", 1.0)
        if trigger_rate < 0.0 or trigger_rate > 1.0:
            raise ValueError(f"FISHBRO_PERF_TRIGGER_RATE must be in [0, 1], got {trigger_rate}")
        worker_log(f"trigger_rate={trigger_rate}")
        
        worker_log(f"Starting. Loading input: {npz_path}")
        
        with np.load(npz_path, allow_pickle=False) as data:
            opens = data['open']
            highs = data['high']
            lows = data['low']
            closes = data['close']
            params = data['params']
            
        worker_log(f"Data loaded. Bars: {len(opens)}, Params: {len(params)}")

        if microbench:
            worker_log("MICROBENCH enabled: running numba indicator microbench.")
            res = _run_microbench_numba_indicators(closes, hot_runs=hot_runs)
            print("__RESULT_JSON_START__")
            print(json.dumps({"mode": "microbench", "result": res}))
            print("__RESULT_JSON_END__")
            return
        
        try:
            # Phase 3B Grid Runner (correct target)
            # src/FishBroWFS_V2/pipeline/runner_grid.py
            from FishBroWFS_V2.pipeline.runner_grid import run_grid  # type: ignore
            worker_log("Grid runner imported successfully (FishBroWFS_V2.pipeline.runner_grid).")
            # Enable runner_grid observability payload in returned dict (timings + jit truth + counts).
            os.environ["FISHBRO_PROFILE_GRID"] = "1"

            # ---- JIT truth report (perf-only) ----
            worker_log(f"ENV NUMBA_DISABLE_JIT={os.environ.get('NUMBA_DISABLE_JIT','')!r}")
            try:
                import numba as _nb  # type: ignore
                worker_log(f"Numba present. nb.config.DISABLE_JIT={getattr(_nb.config,'DISABLE_JIT',None)!r}")
            except Exception as _e:
                worker_log(f"Numba import failed: {_e!r}")

            # run_grid itself might be Python; report what it is.
            worker_log(f"run_grid type={type(run_grid)} has_signatures={hasattr(run_grid,'signatures')}")
            if hasattr(run_grid, "signatures"):
                worker_log(f"run_grid.signatures(before)={getattr(run_grid,'signatures',None)!r}")
            # --------------------------------------
        except ImportError as e:
            worker_log(f"FATAL: Import grid runner failed: {e!r}")
            
            # --- DEBUG INFO ---
            worker_log(f"Current sys.path: {sys.path}")
            src_path = Path(__file__).resolve().parent.parent / "src"
            if src_path.exists():
                worker_log(f"Listing {src_path}:")
                try:
                    for p in src_path.iterdir():
                        worker_log(f" - {p.name}")
                        if p.is_dir() and (p / "__init__.py").exists():
                             worker_log(f"   (package content): {[sub.name for sub in p.iterdir()]}")
                except Exception as ex:
                    worker_log(f"   Error listing dir: {ex}")
            else:
                worker_log(f"Src path not found at: {src_path}")
            # ------------------
            sys.exit(1)
        
        # Warmup run (perf-only): compile/JIT on a tiny slice so the real run measures steady-state.
        # IMPORTANT: respect CLI-provided warmup_{bars,params}. If 0, fall back to defaults.
        if warmup_bars and warmup_bars > 0:
            wb = min(int(warmup_bars), len(opens))
        else:
            wb = min(2000, len(opens))

        if warmup_params and warmup_params > 0:
            wp = min(int(warmup_params), len(params))
        else:
            wp = min(200, len(params))
        if wb >= 10 and wp >= 10:
            worker_log(f"Starting WARMUP run (bars={wb}, params={wp})...")
            _ = run_grid(
                open_=opens[:wb],
                high=highs[:wb],
                low=lows[:wb],
                close=closes[:wb],
                params_matrix=params[:wp],
                commission=0.0,
                slip=0.0,
                sort_params=False,
            )
            worker_log("WARMUP finished.")
            if hasattr(run_grid, "signatures"):
                worker_log(f"run_grid.signatures(after)={getattr(run_grid,'signatures',None)!r}")
        
        lane_sort = os.environ.get("FISHBRO_PERF_LANE_SORT", "0").strip() == "1"
        lane_id = os.environ.get("FISHBRO_PERF_LANE_ID", "?").strip()
        do_profile = _env_flag("FISHBRO_PERF_PROFILE")
        topn = _env_int("FISHBRO_PERF_PROFILE_TOP", 40)
        mode = os.environ.get("FISHBRO_PERF_PROFILE_MODE", "").strip()
        jit_enabled = os.environ.get("NUMBA_DISABLE_JIT", "").strip() != "1"
        cold_time = 0.0
        if skip_cold:
            # Skip-cold mode: warmup already done, skip full cold run
            worker_log("Skip-cold mode: skipping full cold run (warmup already completed)")
        else:
            # Full cold run
            worker_log("Starting COLD run...")
            t0 = time.perf_counter()
            _ = run_grid(
                open_=opens,
                high=highs,
                low=lows,
                close=closes,
                params_matrix=params,
                commission=0.0,
                slip=0.0,
                sort_params=lane_sort,
            )
            cold_time = time.perf_counter() - t0
            worker_log(f"COLD run finished: {cold_time:.4f}s")
        
        worker_log(f"Starting {hot_runs} HOT runs (GC disabled)...")
        hot_times = []
        last_out: Optional[Dict[str, Any]] = None
        gc.disable()
        try:
            for i in range(hot_runs):
                t_start = time.perf_counter()
                if do_profile and i == 0:
                    pr = cProfile.Profile()
                    pr.enable()
                    last_out = run_grid(
                        open_=opens,
                        high=highs,
                        low=lows,
                        close=closes,
                        params_matrix=params,
                        commission=0.0,
                        slip=0.0,
                        sort_params=lane_sort,
                    )
                    pr.disable()
                    print(
                        _format_profile_report(
                            lane_id=lane_id,
                            n_bars=int(len(opens)),
                            n_params=int(len(params)),
                            jit_enabled=bool(jit_enabled),
                            sort_params=bool(lane_sort),
                            topn=int(topn),
                            mode=mode,
                            pr=pr,
                        ),
                        end="",
                    )
                else:
                    last_out = run_grid(
                        open_=opens,
                        high=highs,
                        low=lows,
                        close=closes,
                        params_matrix=params,
                        commission=0.0,
                        slip=0.0,
                        sort_params=lane_sort,
                    )
                t_end = time.perf_counter()
                hot_times.append(t_end - t_start)
        finally:
            gc.enable()
        
        avg_hot = statistics.mean(hot_times) if hot_times else 0.0
        min_hot = min(hot_times) if hot_times else 0.0
        
        result = {
            "cold_time": cold_time,
            "hot_times": hot_times,
            "avg_hot_time": avg_hot,
            "min_hot_time": min_hot,
            "n_bars": len(opens),
            "n_params": len(params),
            "throughput": (len(opens) * len(params)) / min_hot if min_hot > 0 else 0,
        }

        # Attach runner_grid observability payload (timings + jit truth + counts)
        if isinstance(last_out, dict) and "perf" in last_out:
            result["perf"] = last_out["perf"]
            # Stage P2-1.6: Add trigger_rate_configured to perf dict
            if isinstance(result["perf"], dict):
                result["perf"]["trigger_rate_configured"] = float(trigger_rate)
        
        # Stage P2-1.8: Debug timing keys (only if PERF_DEBUG=1)
        if os.environ.get("PERF_DEBUG", "").strip() == "1":
            perf_keys = sorted(result.get("perf", {}).keys()) if isinstance(result.get("perf"), dict) else []
            worker_log(f"DEBUG: perf keys count={len(perf_keys)}, has t_total_kernel_s={'t_total_kernel_s' in perf_keys}")
            if len(perf_keys) > 0:
                worker_log(f"DEBUG: perf keys sample: {perf_keys[:20]}")
        
        print(f"__RESULT_JSON_START__")
        print(json.dumps(result))
        print(f"__RESULT_JSON_END__")
        
    except Exception as e:
        worker_log(f"CRASH: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

# ==========================================
# 4. Controller 邏輯 (Host Process)
# ==========================================

def run_lane(
    lane_id: int,
    cfg: PerfConfig,
    tmp_dir: str,
    ohlc_data: Dict[str, np.ndarray],
    microbench: bool = False,
) -> Dict[str, Any]:
    print(f"\n>>> Running Lane {lane_id}: {cfg.name}")
    print(f"    Config: Bars={cfg.n_bars}, Params={cfg.n_params}, JIT={not cfg.disable_jit}, Sort={cfg.sort_params}")
    
    params = generate_params(cfg.n_params)
    # Do not pre-sort here; sorting behavior must be owned by runner_grid(sort_params=...).
    # For no-sort lane, we shuffle to simulate random access order.
    if not cfg.sort_params:
        np.random.shuffle(params)
        print("    Params shuffled (random access simulation).")
    else:
        print("    Params left unsorted; runner_grid(sort_params=True) will apply cache-friendly sort.")
        
    npz_path = os.path.join(tmp_dir, f"input_lane_{lane_id}.npz")
    np.savez_compressed(
        npz_path, 
        open=ohlc_data["open"][:cfg.n_bars],
        high=ohlc_data["high"][:cfg.n_bars],
        low=ohlc_data["low"][:cfg.n_bars],
        close=ohlc_data["close"][:cfg.n_bars],
        params=params
    )
    
    env = os.environ.copy()
    
    # 關鍵修正: 強制注入 PYTHONPATH 確保子進程看得到 src
    src_path = str(PROJECT_ROOT / "src")
    if "PYTHONPATH" in env:
        env["PYTHONPATH"] = f"{src_path}:{env['PYTHONPATH']}"
    else:
        env["PYTHONPATH"] = src_path
        
    if cfg.disable_jit:
        env["NUMBA_DISABLE_JIT"] = "1"
    else:
        env.pop("NUMBA_DISABLE_JIT", None)
    
    # Stage P2-1.6: Pass FISHBRO_PERF_TRIGGER_RATE to worker if set
    # (env.copy() already includes it, but we ensure it's explicitly passed)
    trigger_rate_env = os.environ.get("FISHBRO_PERF_TRIGGER_RATE")
    if trigger_rate_env:
        env["FISHBRO_PERF_TRIGGER_RATE"] = trigger_rate_env
        
    # Build worker command
    cmd = [
        sys.executable,
        __file__,
        "--worker",
        "--input",
        npz_path,
        "--hot-runs",
        str(cfg.hot_runs),
    ]
    if microbench:
        cmd.append("--microbench")
    # Pass lane sort flag to worker via env (avoid CLI churn)
    env["FISHBRO_PERF_LANE_SORT"] = "1" if cfg.sort_params else "0"
    env["FISHBRO_PERF_LANE_ID"] = str(lane_id)
    
    # Add skip-cold and warmup params if needed
    skip_cold = os.environ.get("FISHBRO_PERF_SKIP_COLD", "").lower() == "true"
    if skip_cold:
        cmd.extend(["--skip-cold"])
        warmup_bars = int(os.environ.get("FISHBRO_PERF_WARMUP_BARS", str(TIER_WARMUP_COMPILE_BARS)))
        warmup_params = int(os.environ.get("FISHBRO_PERF_WARMUP_PARAMS", str(TIER_WARMUP_COMPILE_PARAMS)))
        cmd.extend(["--warmup-bars", str(warmup_bars), "--warmup-params", str(warmup_params)])
    
    try:
        proc = subprocess.run(
            cmd,
            env=env,
            capture_output=True,
            text=True,
            timeout=cfg.timeout,
            check=True
        )
        
        stdout = proc.stdout
        # Print worker stdout (includes JIT truth report)
        print(stdout, end="")
        
        result_json = None
        lines = stdout.splitlines()
        capture = False
        json_str = ""
        
        for line in lines:
            if line.strip() == "__RESULT_JSON_END__":
                capture = False
            if capture:
                json_str += line
            if line.strip() == "__RESULT_JSON_START__":
                capture = True
                
        if json_str:
            result_json = json.loads(json_str)
            
            # Phase 3.0-C: FAIL-FAST defense - detect fallback to object mode
            strict_arrays = os.environ.get("FISHBRO_PERF_STRICT_ARRAYS", "1").strip() == "1"
            if strict_arrays and isinstance(result_json, dict):
                perf = result_json.get("perf")
                if isinstance(perf, dict):
                    intent_mode = perf.get("intent_mode")
                    if intent_mode != "arrays":
                        # Handle None or any non-"arrays" value
                        intent_mode_str = str(intent_mode) if intent_mode is not None else "None"
                        error_msg = (
                            f"ERROR: intent_mode expected 'arrays' but got '{intent_mode_str}' (lane {lane_id})\n"
                            f"This indicates the kernel fell back to object mode, which is a performance regression.\n"
                            f"To disable this check, set FISHBRO_PERF_STRICT_ARRAYS=0"
                        )
                        print(f"❌ {error_msg}", file=sys.stderr)
                        raise RuntimeError(error_msg)
            
            return result_json
        else:
            print("❌ Error: Worker finished but no JSON result found.")
            print("--- Worker Stdout ---")
            print(stdout)
            print("--- Worker Stderr ---")
            print(proc.stderr)
            return {}
            
    except subprocess.TimeoutExpired as e:
        print(f"❌ Error: Lane {lane_id} Timeout ({cfg.timeout}s).")
        if e.stdout: print(e.stdout)
        if e.stderr: print(e.stderr)
        return {}
    except subprocess.CalledProcessError as e:
        print(f"❌ Error: Lane {lane_id} Crashed (Exit {e.returncode}).")
        print("--- Worker Stdout ---")
        print(e.stdout)
        print("--- Worker Stderr ---")
        print(e.stderr)
        return {}
    except Exception as e:
        print(f"❌ Error: System error {e}")
        return {}

def print_report(results: List[Dict[str, Any]]):
    print("\n\n=== FishBro WFS Perf Harness Report ===")
    print("| Lane | Mode | Sort | Bars | Params | Cold(s) | Hot(s) | Tput (Ops/s) | Speedup |")
    print("|---|---|---|---|---|---|---|---|---|")
    
    jit_no_sort_tput = 0
    for r in results:
        if not r or "res" not in r or "lane_id" not in r: continue
        lane_id = r.get('lane_id', 0)
        name = r.get('name', 'Unknown')
        bars = r['res'].get('n_bars', 0)
        params = r['res'].get('n_params', 0)
        cold = r['res'].get('cold_time', 0)
        hot = r['res'].get('min_hot_time', 0)
        tput = r['res'].get('throughput', 0)
        
        if lane_id == 3:
            jit_no_sort_tput = tput
            speedup = "1.0x (Base)"
        elif jit_no_sort_tput > 0 and tput > 0:
            ratio = tput / jit_no_sort_tput
            speedup = f"{ratio:.2f}x"
        else:
            speedup = "-"
            
        mode = "Py" if r.get("disable_jit", False) else "JIT"
        sort = "Yes" if r.get("sort_params", False) else "No"
        print(f"| {lane_id} | {mode} | {sort} | {bars} | {params} | {cold:.4f} | {hot:.4f} | {int(tput):,} | {speedup} |")
    print("\nNote: Tput = (Bars * Params) / Min Hot Run Time")
    
    # Phase 4 Stage E: Cost Model Output
    print("\n=== Cost Model (Predictable Cost Estimation) ===")
    for r in results:
        if not r or "res" not in r or "lane_id" not in r: continue
        lane_id = r.get('lane_id', 0)
        res = r.get('res', {})
        bars = res.get('n_bars', 0)
        params = res.get('n_params', 0)
        min_hot_time = res.get('min_hot_time', 0)
        
        if min_hot_time > 0 and params > 0:
            # Calculate cost per parameter (milliseconds)
            cost_ms_per_param = (min_hot_time / params) * 1000.0
            
            # Calculate params per second
            params_per_sec = params / min_hot_time
            
            # Estimate time for 50k params
            estimated_time_for_50k_params = estimate_seconds(
                bars=bars,
                params=50000,
                cost_ms_per_param=cost_ms_per_param,
            )
            
            # Output cost model fields (stdout)
            print(f"\nLane {lane_id} Cost Model:")
            print(f"  bars: {bars}")
            print(f"  params: {params}")
            print(f"  best_time_s: {min_hot_time:.6f}")
            print(f"  params_per_sec: {params_per_sec:,.2f}")
            print(f"  cost_ms_per_param: {cost_ms_per_param:.6f}")
            print(f"  estimated_time_for_50k_params: {estimated_time_for_50k_params:.2f}")
            
            # Stage P2-1.5: Entry Sparse Observability
            perf = res.get('perf', {})
            if isinstance(perf, dict):
                entry_valid_mask_sum = perf.get('entry_valid_mask_sum')
                entry_intents_total = perf.get('entry_intents_total')
                entry_intents_per_bar_avg = perf.get('entry_intents_per_bar_avg')
                intents_total_reported = perf.get('intents_total_reported')
                trigger_rate_configured = perf.get('trigger_rate_configured')
                
                # Always output if perf dict exists (fields should always be present)
                if entry_valid_mask_sum is not None or entry_intents_total is not None:
                    print(f"\nLane {lane_id} Entry Sparse Observability:")
                    # Stage P2-1.6: Display trigger_rate_configured
                    if trigger_rate_configured is not None:
                        print(f"  trigger_rate_configured: {trigger_rate_configured:.6f}")
                    print(f"  entry_valid_mask_sum: {entry_valid_mask_sum if entry_valid_mask_sum is not None else 0}")
                    print(f"  entry_intents_total: {entry_intents_total if entry_intents_total is not None else 0}")
                    if entry_intents_per_bar_avg is not None:
                        print(f"  entry_intents_per_bar_avg: {entry_intents_per_bar_avg:.6f}")
                    else:
                        # Calculate if missing
                        if entry_intents_total is not None and bars > 0:
                            print(f"  entry_intents_per_bar_avg: {entry_intents_total / bars:.6f}")
                    print(f"  intents_total_reported: {intents_total_reported if intents_total_reported is not None else perf.get('intents_total', 0)}")
    
    # Stage P2-1.8: Breakdown (Kernel Stage Timings)
    print("\n=== Breakdown (Kernel Stage Timings) ===")
    for r in results:
        if not r or "res" not in r or "lane_id" not in r: continue
        lane_id = r.get('lane_id', 0)
        res = r.get('res', {})
        perf = res.get('perf', {})
        
        if isinstance(perf, dict):
            trigger_rate = perf.get('trigger_rate_configured')
            t_ind_donchian = perf.get('t_ind_donchian_s')
            t_ind_atr = perf.get('t_ind_atr_s')
            t_build_entry = perf.get('t_build_entry_intents_s')
            t_sim_entry = perf.get('t_simulate_entry_s')
            t_calc_exits = perf.get('t_calc_exits_s')
            t_sim_exit = perf.get('t_simulate_exit_s')
            t_total_kernel = perf.get('t_total_kernel_s')
            
            print(f"\nLane {lane_id} Breakdown:")
            if trigger_rate is not None:
                print(f"  trigger_rate_configured: {trigger_rate:.6f}")
            
            # Helper to format timing with "(missing)" if None
            def fmt_time(key: str, val) -> str:
                if val is None:
                    return f"  {key}: (missing)"
                return f"  {key}: {val:.6f}"
            
            # Stage P2-2 Step A: Micro-profiling indicators
            print(fmt_time("t_ind_donchian_s", t_ind_donchian))
            print(fmt_time("t_ind_atr_s", t_ind_atr))
            print(fmt_time("t_build_entry_intents_s", t_build_entry))
            print(fmt_time("t_simulate_entry_s", t_sim_entry))
            print(fmt_time("t_calc_exits_s", t_calc_exits))
            print(fmt_time("t_simulate_exit_s", t_sim_exit))
            print(fmt_time("t_total_kernel_s", t_total_kernel))
            
            # Print percentages if t_total_kernel is available and > 0
            if t_total_kernel is not None and t_total_kernel > 0:
                def fmt_pct(key: str, val, total: float) -> str:
                    if val is None:
                        return f"    {key}: (missing)"
                    pct = (val / total) * 100.0
                    return f"    {key}: {pct:.1f}%"
                
                print("  Percentages:")
                print(fmt_pct("t_ind_donchian_s", t_ind_donchian, t_total_kernel))
                print(fmt_pct("t_ind_atr_s", t_ind_atr, t_total_kernel))
                print(fmt_pct("t_build_entry_intents_s", t_build_entry, t_total_kernel))
                print(fmt_pct("t_simulate_entry_s", t_sim_entry, t_total_kernel))
                print(fmt_pct("t_calc_exits_s", t_calc_exits, t_total_kernel))
                print(fmt_pct("t_simulate_exit_s", t_sim_exit, t_total_kernel))
            
            # Stage P2-2 Step A: Memoization potential assessment
            unique_ch = perf.get('unique_channel_len_count')
            unique_atr = perf.get('unique_atr_len_count')
            unique_pair = perf.get('unique_ch_atr_pair_count')
            
            if unique_ch is not None or unique_atr is not None or unique_pair is not None:
                print(f"\nLane {lane_id} Memoization Potential:")
                if unique_ch is not None:
                    print(f"  unique_channel_len_count: {unique_ch}")
                else:
                    print(f"  unique_channel_len_count: (missing)")
                if unique_atr is not None:
                    print(f"  unique_atr_len_count: {unique_atr}")
                else:
                    print(f"  unique_atr_len_count: (missing)")
                if unique_pair is not None:
                    print(f"  unique_ch_atr_pair_count: {unique_pair}")
                else:
                    print(f"  unique_ch_atr_pair_count: (missing)")
            
            # Stage P2-1.8: Display downstream counts
            entry_fills_total = perf.get('entry_fills_total')
            exit_intents_total = perf.get('exit_intents_total')
            exit_fills_total = perf.get('exit_fills_total')
            
            if entry_fills_total is not None or exit_intents_total is not None or exit_fills_total is not None:
                print(f"\nLane {lane_id} Downstream Observability:")
                if entry_fills_total is not None:
                    print(f"  entry_fills_total: {entry_fills_total}")
                else:
                    print(f"  entry_fills_total: (missing)")
                if exit_intents_total is not None:
                    print(f"  exit_intents_total: {exit_intents_total}")
                else:
                    print(f"  exit_intents_total: (missing)")
                if exit_fills_total is not None:
                    print(f"  exit_fills_total: {exit_fills_total}")
                else:
                    print(f"  exit_fills_total: (missing)")

def run_matcherbench() -> None:
    """
    Matcher-only microbenchmark.
    Purpose:
      - Measure true throughput of cursor-based matcher kernel
      - Avoid runner_grid / Python orchestration overhead
    """
    from FishBroWFS_V2.engine.engine_jit import simulate
    from FishBroWFS_V2.engine.types import (
        BarArrays,
        OrderIntent,
        OrderKind,
        OrderRole,
        Side,
    )

    # ---- config (safe defaults) ----
    n_bars = int(os.environ.get("FISHBRO_MB_BARS", "20000"))
    intents_per_bar = int(os.environ.get("FISHBRO_MB_INTENTS_PER_BAR", "2"))
    hot_runs = int(os.environ.get("FISHBRO_MB_HOTRUNS", "3"))

    print(
        f"[matcherbench] bars={n_bars}, intents_per_bar={intents_per_bar}, hot_runs={hot_runs}"
    )

    # ---- synthetic OHLC ----
    rng = np.random.default_rng(42)
    close = 10000 + np.cumsum(rng.standard_normal(n_bars))
    high = close + 5.0
    low = close - 5.0
    open_ = (high + low) * 0.5

    bars = BarArrays(
        open=open_.astype(np.float64),
        high=high.astype(np.float64),
        low=low.astype(np.float64),
        close=close.astype(np.float64),
    )

    # ---- generate intents: created_bar = t-1 ----
    intents = []
    oid = 1
    for t in range(1, n_bars):
        for _ in range(intents_per_bar):
            # ENTRY
            intents.append(
                OrderIntent(
                    order_id=oid,
                    created_bar=t - 1,
                    role=OrderRole.ENTRY,
                    kind=OrderKind.STOP,
                    side=Side.BUY,
                    price=float(high[t - 1]),
                    qty=1,
                )
            )
            oid += 1
            # EXIT
            intents.append(
                OrderIntent(
                    order_id=oid,
                    created_bar=t - 1,
                    role=OrderRole.EXIT,
                    kind=OrderKind.STOP,
                    side=Side.SELL,
                    price=float(low[t - 1]),
                    qty=1,
                )
            )
            oid += 1

    print(f"[matcherbench] total_intents={len(intents)}")

    # ---- warmup (compile) ----
    simulate(bars, intents)

    # ---- hot runs ----
    times = []
    gc.disable()
    try:
        for _ in range(hot_runs):
            t0 = time.perf_counter()
            fills = simulate(bars, intents)
            dt = time.perf_counter() - t0
            times.append(dt)
    finally:
        gc.enable()

    best = min(times)
    bars_per_s = n_bars / best
    intents_scanned = len(intents)
    intents_per_s = intents_scanned / best
    fills_per_s = len(fills) / best

    print("\n=== MATCHERBENCH RESULT ===")
    print(f"best_time_s      : {best:.6f}")
    print(f"bars_per_sec     : {bars_per_s:,.0f}")
    print(f"intents_per_sec  : {intents_per_s:,.0f}")
    print(f"fills_per_sec    : {fills_per_s:,.0f}")


def main():
    parser = argparse.ArgumentParser(description="FishBro WFS Perf Harness")
    parser.add_argument("--worker", action="store_true", help="Run as worker")
    parser.add_argument("--input", type=str, help="Path to input NPZ")
    parser.add_argument("--hot-runs", type=int, default=5, help="Hot runs")
    parser.add_argument("--skip-cold", action="store_true", help="Skip full cold run, use warmup compile instead")
    parser.add_argument("--warmup-bars", type=int, default=0, help="Warmup compile bars (for skip-cold)")
    parser.add_argument("--warmup-params", type=int, default=0, help="Warmup compile params (for skip-cold)")
    parser.add_argument("--microbench", action="store_true", help="Run microbench only (numba indicator baseline)")
    parser.add_argument("--include-python-baseline", action="store_true", help="Include Toy Tier")
    parser.add_argument(
        "--matcherbench",
        action="store_true",
        help="Benchmark matcher kernel only (engine_jit.simulate), no runner_grid",
    )
    parser.add_argument("--stress-tier", action="store_true", help="Use stress tier (200k×10k) instead of warmup tier")
    args = parser.parse_args()
    
    if args.matcherbench:
        run_matcherbench()
        return

    if args.worker:
        if not args.input: sys.exit(1)
        run_worker(
            args.input,
            args.hot_runs,
            args.skip_cold,
            args.warmup_bars,
            args.warmup_params,
            args.microbench,
        )
        return

    print("Initializing Perf Harness...")
    
    # Stage P2-1.6: Parse and display trigger_rate in main process
    trigger_rate = _env_float("FISHBRO_PERF_TRIGGER_RATE", 1.0)
    if trigger_rate < 0.0 or trigger_rate > 1.0:
        raise ValueError(f"FISHBRO_PERF_TRIGGER_RATE must be in [0, 1], got {trigger_rate}")
    print(f"trigger_rate={trigger_rate}")
    
    lanes_cfg: List[PerfConfig] = []
    
    # Select tier based on stress-tier flag
    if args.stress_tier:
        jit_bars = TIER_STRESS_BARS
        jit_params = TIER_STRESS_PARAMS
        print(f"Using STRESS tier: {jit_bars:,} bars × {jit_params:,} params")
    else:
        jit_bars = TIER_JIT_BARS
        jit_params = TIER_JIT_PARAMS
        print(f"Using WARMUP tier: {jit_bars:,} bars × {jit_params:,} params")
    
    if args.include_python_baseline:
        lanes_cfg.append(PerfConfig("Lane 1 (Py, No Sort)", TIER_TOY_BARS, TIER_TOY_PARAMS, TIER_TOY_HOT_RUNS, TIER_TOY_TIMEOUT, True, False))
        lanes_cfg.append(PerfConfig("Lane 2 (Py, Sort)", TIER_TOY_BARS, TIER_TOY_PARAMS, TIER_TOY_HOT_RUNS, TIER_TOY_TIMEOUT, True, True))
        
    lanes_cfg.append(PerfConfig("Lane 3 (JIT, No Sort)", jit_bars, jit_params, TIER_JIT_HOT_RUNS, TIER_JIT_TIMEOUT, False, False))
    lanes_cfg.append(PerfConfig("Lane 4 (JIT, Sort)", jit_bars, jit_params, TIER_JIT_HOT_RUNS, TIER_JIT_TIMEOUT, False, True))
    
    max_bars = max(c.n_bars for c in lanes_cfg)
    print(f"Generating synthetic data (Max Bars: {max_bars})...")
    ohlc_data = generate_synthetic_data(max_bars)
    
    results = []
    try:
        with tempfile.TemporaryDirectory() as tmp_dir:
            print(f"Created temp dir for IPC: {tmp_dir}")
            for i, cfg in enumerate(lanes_cfg):
                lane_id = i + 1
                if not args.include_python_baseline: lane_id += 2 
                res = run_lane(lane_id, cfg, tmp_dir, ohlc_data, microbench=args.microbench)
                if res:
                    results.append(
                        {
                            "lane_id": lane_id,
                            "name": cfg.name,
                            "res": res,
                            "disable_jit": cfg.disable_jit,
                            "sort_params": cfg.sort_params,
                        }
                    )
                else: results.append({})
                
        print_report(results)
    except RuntimeError as e:
        # Phase 3.0-C: FAIL-FAST - exit with non-zero code on intent_mode violation
        print(f"\n❌ FAIL-FAST triggered: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()