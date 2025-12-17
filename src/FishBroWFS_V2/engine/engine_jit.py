from __future__ import annotations

from dataclasses import asdict
from typing import Iterable, List, Tuple

import numpy as np

# Engine JIT matcher kernel contract:
# - Complexity target: O(B + I + A), where:
#     B = bars, I = intents, A = per-bar active-book scan.
# - Forbidden: scanning all intents per bar (O(B*I)).
# - Extension point: ttl_bars (0=GTC, 1=one-shot next-bar-only, future: >1).

try:
    import numba as nb
except Exception:  # pragma: no cover
    nb = None  # type: ignore

from FishBroWFS_V2.engine.types import (
    BarArrays,
    Fill,
    OrderIntent,
    OrderKind,
    OrderRole,
    Side,
)
from FishBroWFS_V2.engine.matcher_core import simulate as simulate_py
from FishBroWFS_V2.engine.constants import (
    KIND_LIMIT,
    KIND_STOP,
    ROLE_ENTRY,
    ROLE_EXIT,
    SIDE_BUY,
    SIDE_SELL,
)

STATUS_OK = 0
STATUS_ERROR_UNSORTED = 1

# JIT truth (debug/perf observability)
JIT_PATH_USED_LAST = False
JIT_KERNEL_SIGNATURES_LAST = None  # type: ignore


def get_jit_truth() -> dict:
    """
    Debug helper: returns whether the last simulate() call used the JIT kernel,
    and (if available) the kernel signatures snapshot.
    """
    return {
        "jit_path_used": bool(JIT_PATH_USED_LAST),
        "kernel_signatures": JIT_KERNEL_SIGNATURES_LAST,
    }


def _to_int(x) -> int:
    # Enum values are int/str; we convert deterministically.
    if isinstance(x, Side):
        return int(x.value)
    if isinstance(x, OrderRole):
        # EXIT first tie-break relies on role; map explicitly.
        return 0 if x == OrderRole.EXIT else 1
    if isinstance(x, OrderKind):
        return 0 if x == OrderKind.STOP else 1
    return int(x)


def _to_kind_int(k: OrderKind) -> int:
    return 0 if k == OrderKind.STOP else 1


def _to_role_int(r: OrderRole) -> int:
    return 0 if r == OrderRole.EXIT else 1


def _to_side_int(s: Side) -> int:
    return int(s.value)


def _kind_from_int(v: int) -> OrderKind:
    return OrderKind.STOP if v == 0 else OrderKind.LIMIT


def _role_from_int(v: int) -> OrderRole:
    return OrderRole.EXIT if v == 0 else OrderRole.ENTRY


def _side_from_int(v: int) -> Side:
    return Side.BUY if v == 1 else Side.SELL


def _pack_intents(intents: Iterable[OrderIntent]):
    """
    Pack intents into plain arrays for numba.

    Fields:
      order_id: int64
      created_bar: int64
      role: int8 (0=EXIT,1=ENTRY)
      kind: int8 (0=STOP,1=LIMIT)
      side: int8 (1=BUY,-1=SELL)
      price: float64
      qty: int64
    """
    it = list(intents)
    n = len(it)
    order_id = np.empty(n, dtype=np.int64)
    created_bar = np.empty(n, dtype=np.int64)
    role = np.empty(n, dtype=np.int8)
    kind = np.empty(n, dtype=np.int8)
    side = np.empty(n, dtype=np.int8)
    price = np.empty(n, dtype=np.float64)
    qty = np.empty(n, dtype=np.int64)

    for i, x in enumerate(it):
        order_id[i] = int(x.order_id)
        created_bar[i] = int(x.created_bar)
        role[i] = np.int8(_to_role_int(x.role))
        kind[i] = np.int8(_to_kind_int(x.kind))
        side[i] = np.int8(_to_side_int(x.side))
        price[i] = float(x.price)
        qty[i] = int(x.qty)

    return order_id, created_bar, role, kind, side, price, qty


def _sort_packed_by_created_bar(
    packed: Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray],
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """
    Sort packed intent arrays by (created_bar, order_id).

    Why:
      - Cursor + active-book kernel requires activate_bar=(created_bar+1) and order_id to be non-decreasing.
      - Determinism is preserved because selection is still based on (kind priority, order_id).
    """
    order_id, created_bar, role, kind, side, price, qty = packed
    # lexsort uses last key as primary -> (created_bar primary, order_id secondary)
    idx = np.lexsort((order_id, created_bar))
    return (
        order_id[idx],
        created_bar[idx],
        role[idx],
        kind[idx],
        side[idx],
        price[idx],
        qty[idx],
    )


def simulate(
    bars: BarArrays,
    intents: Iterable[OrderIntent],
) -> List[Fill]:
    """
    Phase 2A: JIT accelerated matcher.

    Kill switch:
      - If numba is unavailable OR NUMBA_DISABLE_JIT=1, fall back to Python reference.
    """
    global JIT_PATH_USED_LAST, JIT_KERNEL_SIGNATURES_LAST

    if nb is None:
        JIT_PATH_USED_LAST = False
        JIT_KERNEL_SIGNATURES_LAST = None
        return simulate_py(bars, intents)

    # If numba is disabled, keep behavior stable.
    # Numba respects NUMBA_DISABLE_JIT; but we short-circuit to be safe.
    import os

    if os.environ.get("NUMBA_DISABLE_JIT", "").strip() == "1":
        JIT_PATH_USED_LAST = False
        JIT_KERNEL_SIGNATURES_LAST = None
        return simulate_py(bars, intents)

    packed = _sort_packed_by_created_bar(_pack_intents(intents))
    status, fills_arr = _simulate_kernel(
        bars.open,
        bars.high,
        bars.low,
        packed[0],
        packed[1],
        packed[2],
        packed[3],
        packed[4],
        packed[5],
        packed[6],
        np.int64(1),  # ttl_bars=1 keeps Phase-2 semantics (next-bar only)
    )
    if int(status) != STATUS_OK:
        JIT_PATH_USED_LAST = True
        raise RuntimeError(f"engine_jit kernel error: status={int(status)}")

    # record JIT truth (best-effort)
    JIT_PATH_USED_LAST = True
    try:
        sigs = getattr(_simulate_kernel, "signatures", None)
        if sigs is not None:
            JIT_KERNEL_SIGNATURES_LAST = list(sigs)
        else:
            JIT_KERNEL_SIGNATURES_LAST = None
    except Exception:
        JIT_KERNEL_SIGNATURES_LAST = None

    # Convert to Fill objects (drop unused capacity)
    out: List[Fill] = []
    m = fills_arr.shape[0]
    for i in range(m):
        row = fills_arr[i]
        out.append(
            Fill(
                bar_index=int(row[0]),
                role=_role_from_int(int(row[1])),
                kind=_kind_from_int(int(row[2])),
                side=_side_from_int(int(row[3])),
                price=float(row[4]),
                qty=int(row[5]),
                order_id=int(row[6]),
            )
        )
    return out


def simulate_arrays(
    bars: BarArrays,
    *,
    order_id: np.ndarray,
    created_bar: np.ndarray,
    role: np.ndarray,
    kind: np.ndarray,
    side: np.ndarray,
    price: np.ndarray,
    qty: np.ndarray,
    ttl_bars: int = 1,
) -> List[Fill]:
    """
    Array/SoA entry point: bypass OrderIntent objects and _pack_intents hot-path.

    Arrays must be 1D and same length. Dtypes are expected:
      order_id,int64 ; created_bar,int64 ; role,int8 ; kind,int8 ; side,int8 ; price,float64 ; qty,int64

    ttl_bars:
      1 => one-shot next-bar-only (Phase 2 semantics)
      0 => GTC extension point (debug/tests)
    """
    global JIT_PATH_USED_LAST, JIT_KERNEL_SIGNATURES_LAST

    # Normalize/ensure arrays are numpy with the expected dtypes (cold path).
    oid = np.asarray(order_id, dtype=np.int64)
    cb = np.asarray(created_bar, dtype=np.int64)
    rl = np.asarray(role, dtype=np.int8)
    kd = np.asarray(kind, dtype=np.int8)
    sd = np.asarray(side, dtype=np.int8)
    px = np.asarray(price, dtype=np.float64)
    qy = np.asarray(qty, dtype=np.int64)

    if nb is None:
        JIT_PATH_USED_LAST = False
        JIT_KERNEL_SIGNATURES_LAST = None
        intents: List[OrderIntent] = []
        n = int(oid.shape[0])
        for i in range(n):
            r = OrderRole.EXIT if int(rl[i]) == ROLE_EXIT else OrderRole.ENTRY
            k = OrderKind.STOP if int(kd[i]) == KIND_STOP else OrderKind.LIMIT
            s = Side.BUY if int(sd[i]) == SIDE_BUY else Side.SELL
            intents.append(
                OrderIntent(
                    order_id=int(oid[i]),
                    created_bar=int(cb[i]),
                    role=r,
                    kind=k,
                    side=s,
                    price=float(px[i]),
                    qty=int(qy[i]),
                )
            )
        return simulate_py(bars, intents)

    import os

    if os.environ.get("NUMBA_DISABLE_JIT", "").strip() == "1":
        JIT_PATH_USED_LAST = False
        JIT_KERNEL_SIGNATURES_LAST = None
        intents: List[OrderIntent] = []
        n = int(oid.shape[0])
        for i in range(n):
            r = OrderRole.EXIT if int(rl[i]) == ROLE_EXIT else OrderRole.ENTRY
            k = OrderKind.STOP if int(kd[i]) == KIND_STOP else OrderKind.LIMIT
            s = Side.BUY if int(sd[i]) == SIDE_BUY else Side.SELL
            intents.append(
                OrderIntent(
                    order_id=int(oid[i]),
                    created_bar=int(cb[i]),
                    role=r,
                    kind=k,
                    side=s,
                    price=float(px[i]),
                    qty=int(qy[i]),
                )
            )
        return simulate_py(bars, intents)

    packed = _sort_packed_by_created_bar((oid, cb, rl, kd, sd, px, qy))
    status, fills_arr = _simulate_kernel(
        bars.open,
        bars.high,
        bars.low,
        packed[0],
        packed[1],
        packed[2],
        packed[3],
        packed[4],
        packed[5],
        packed[6],
        np.int64(ttl_bars),
    )
    if int(status) != STATUS_OK:
        JIT_PATH_USED_LAST = True
        raise RuntimeError(f"engine_jit kernel error: status={int(status)}")

    JIT_PATH_USED_LAST = True
    try:
        sigs = getattr(_simulate_kernel, "signatures", None)
        if sigs is not None:
            JIT_KERNEL_SIGNATURES_LAST = list(sigs)
        else:
            JIT_KERNEL_SIGNATURES_LAST = None
    except Exception:
        JIT_KERNEL_SIGNATURES_LAST = None

    out: List[Fill] = []
    m = fills_arr.shape[0]
    for i in range(m):
        row = fills_arr[i]
        out.append(
            Fill(
                bar_index=int(row[0]),
                role=_role_from_int(int(row[1])),
                kind=_kind_from_int(int(row[2])),
                side=_side_from_int(int(row[3])),
                price=float(row[4]),
                qty=int(row[5]),
                order_id=int(row[6]),
            )
        )
    return out


def _simulate_with_ttl(bars: BarArrays, intents: Iterable[OrderIntent], ttl_bars: int) -> List[Fill]:
    """
    Internal helper (tests/dev): run JIT matcher with a custom ttl_bars.
    ttl_bars=0 => GTC, ttl_bars=1 => one-shot next-bar-only (default).
    """
    if nb is None:
        return simulate_py(bars, intents)

    import os

    if os.environ.get("NUMBA_DISABLE_JIT", "").strip() == "1":
        return simulate_py(bars, intents)

    packed = _sort_packed_by_created_bar(_pack_intents(intents))
    status, fills_arr = _simulate_kernel(
        bars.open,
        bars.high,
        bars.low,
        packed[0],
        packed[1],
        packed[2],
        packed[3],
        packed[4],
        packed[5],
        packed[6],
        np.int64(ttl_bars),
    )
    if int(status) != STATUS_OK:
        raise RuntimeError(f"engine_jit kernel error: status={int(status)}")

    out: List[Fill] = []
    m = fills_arr.shape[0]
    for i in range(m):
        row = fills_arr[i]
        out.append(
            Fill(
                bar_index=int(row[0]),
                role=_role_from_int(int(row[1])),
                kind=_kind_from_int(int(row[2])),
                side=_side_from_int(int(row[3])),
                price=float(row[4]),
                qty=int(row[5]),
                order_id=int(row[6]),
            )
        )
    return out


# ----------------------------
# Numba Kernel
# ----------------------------

if nb is not None:

    @nb.njit(cache=False)
    def _stop_fill(side: int, stop_price: float, o: float, h: float, l: float) -> float:
        # returns nan if no fill
        if side == 1:  # BUY
            if o >= stop_price:
                return o
            if h >= stop_price:
                return stop_price
            return np.nan
        else:  # SELL
            if o <= stop_price:
                return o
            if l <= stop_price:
                return stop_price
            return np.nan

    @nb.njit(cache=False)
    def _limit_fill(side: int, limit_price: float, o: float, h: float, l: float) -> float:
        # returns nan if no fill
        if side == 1:  # BUY
            if o <= limit_price:
                return o
            if l <= limit_price:
                return limit_price
            return np.nan
        else:  # SELL
            if o >= limit_price:
                return o
            if h >= limit_price:
                return limit_price
            return np.nan

    @nb.njit(cache=False)
    def _fill_price(kind: int, side: int, px: float, o: float, h: float, l: float) -> float:
        # kind: 0=STOP, 1=LIMIT
        if kind == 0:
            return _stop_fill(side, px, o, h, l)
        return _limit_fill(side, px, o, h, l)

    @nb.njit(cache=False)
    def _simulate_kernel(
        open_: np.ndarray,
        high: np.ndarray,
        low: np.ndarray,
        order_id: np.ndarray,
        created_bar: np.ndarray,
        role: np.ndarray,
        kind: np.ndarray,
        side: np.ndarray,
        price: np.ndarray,
        qty: np.ndarray,
        ttl_bars: np.int64,
    ):
        """
        Cursor + Active Book kernel (O(B + I + A)).

        Output columns (float64):
          0 bar_index
          1 role_int (0=EXIT,1=ENTRY)
          2 kind_int (0=STOP,1=LIMIT)
          3 side_int (1=BUY,-1=SELL)
          4 fill_price
          5 qty
          6 order_id

        Assumption:
          - intents are sorted by (created_bar, order_id) before calling this kernel.
        """
        n_bars = open_.shape[0]
        n_intents = order_id.shape[0]

        max_fills = n_bars * 2
        out = np.empty((max_fills, 7), dtype=np.float64)
        out_n = 0

        # -------------------------
        # Fail-fast monotonicity check (activate_bar, order_id)
        # -------------------------
        prev_activate = np.int64(-1)
        prev_order = np.int64(-1)
        for i in range(n_intents):
            a = np.int64(created_bar[i]) + np.int64(1)
            o = np.int64(order_id[i])
            if a < prev_activate or (a == prev_activate and o < prev_order):
                return np.int64(STATUS_ERROR_UNSORTED), out[:0]
            prev_activate = a
            prev_order = o

        # Active Book (indices into intent arrays)
        active_indices = np.empty(n_intents, dtype=np.int64)
        active_count = np.int64(0)
        global_cursor = np.int64(0)

        pos = np.int64(0)  # 0 flat, 1 long, -1 short

        for t in range(n_bars):
            o = float(open_[t])
            h = float(high[t])
            l = float(low[t])

            # Step A — Injection (cursor inject intents activating at this bar)
            while global_cursor < n_intents:
                a = np.int64(created_bar[global_cursor]) + np.int64(1)
                if a == np.int64(t):
                    active_indices[active_count] = global_cursor
                    active_count += np.int64(1)
                    global_cursor += np.int64(1)
                    continue
                if a > np.int64(t):
                    break
                # a < t should not happen if monotonicity check passed
                return np.int64(STATUS_ERROR_UNSORTED), out[:0]

            # Step B — Pass 1 (ENTRY scan, best-pick, swap-remove)
            # Deterministic selection: STOP(0) before LIMIT(1), then order_id asc.
            if pos == 0 and active_count > 0:
                best_k = np.int64(-1)
                best_kind = np.int64(99)
                best_oid = np.int64(2**62)
                best_fp = np.nan

                k = np.int64(0)
                while k < active_count:
                    idx = active_indices[k]
                    if np.int64(role[idx]) != np.int64(1):  # ENTRY
                        k += np.int64(1)
                        continue

                    kk = np.int64(kind[idx])
                    oo = np.int64(order_id[idx])
                    if kk < best_kind or (kk == best_kind and oo < best_oid):
                        fp = _fill_price(int(kk), int(side[idx]), float(price[idx]), o, h, l)
                        if not np.isnan(fp):
                            best_k = k
                            best_kind = kk
                            best_oid = oo
                            best_fp = fp
                    k += np.int64(1)

                if best_k != np.int64(-1):
                    idx = active_indices[best_k]
                    out[out_n, 0] = float(t)
                    out[out_n, 1] = float(role[idx])
                    out[out_n, 2] = float(kind[idx])
                    out[out_n, 3] = float(side[idx])
                    out[out_n, 4] = float(best_fp)
                    out[out_n, 5] = float(qty[idx])
                    out[out_n, 6] = float(order_id[idx])
                    out_n += 1

                    pos = np.int64(1) if np.int64(side[idx]) == np.int64(1) else np.int64(-1)

                    # swap-remove filled intent
                    active_indices[best_k] = active_indices[active_count - 1]
                    active_count -= np.int64(1)

            # Step C — Pass 2 (EXIT scan, best-pick, swap-remove)
            # Deterministic selection: STOP(0) before LIMIT(1), then order_id asc.
            if pos != 0 and active_count > 0:
                best_k = np.int64(-1)
                best_kind = np.int64(99)
                best_oid = np.int64(2**62)
                best_fp = np.nan

                k = np.int64(0)
                while k < active_count:
                    idx = active_indices[k]
                    if np.int64(role[idx]) != np.int64(0):  # EXIT
                        k += np.int64(1)
                        continue

                    s = np.int64(side[idx])
                    # long exits are SELL(-1), short exits are BUY(1)
                    if pos == np.int64(1) and s != np.int64(-1):
                        k += np.int64(1)
                        continue
                    if pos == np.int64(-1) and s != np.int64(1):
                        k += np.int64(1)
                        continue

                    kk = np.int64(kind[idx])
                    oo = np.int64(order_id[idx])
                    if kk < best_kind or (kk == best_kind and oo < best_oid):
                        fp = _fill_price(int(kk), int(s), float(price[idx]), o, h, l)
                        if not np.isnan(fp):
                            best_k = k
                            best_kind = kk
                            best_oid = oo
                            best_fp = fp
                    k += np.int64(1)

                if best_k != np.int64(-1):
                    idx = active_indices[best_k]
                    out[out_n, 0] = float(t)
                    out[out_n, 1] = float(role[idx])
                    out[out_n, 2] = float(kind[idx])
                    out[out_n, 3] = float(side[idx])
                    out[out_n, 4] = float(best_fp)
                    out[out_n, 5] = float(qty[idx])
                    out[out_n, 6] = float(order_id[idx])
                    out_n += 1

                    pos = np.int64(0)

                    # swap-remove filled intent
                    active_indices[best_k] = active_indices[active_count - 1]
                    active_count -= np.int64(1)

            # Step D — Housekeeping (TTL/GTC extension point)
            if ttl_bars > np.int64(0) and active_count > 0:
                k = np.int64(0)
                while k < active_count:
                    idx = active_indices[k]
                    activate_bar = np.int64(created_bar[idx]) + np.int64(1)
                    expire_bar = activate_bar + (ttl_bars - np.int64(1))
                    if np.int64(t) > expire_bar:
                        active_indices[k] = active_indices[active_count - 1]
                        active_count -= np.int64(1)
                        continue
                    k += np.int64(1)

        return np.int64(STATUS_OK), out[:out_n]

