from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from core.paths import get_outputs_root

from .portfolio_spec import PortfolioSpecV1, data2_candidates_by_data1, data2_primary_by_data1
from control.strategy_registry_yaml import load_strategy_registry_yaml


AutoMode = Literal["deterministic", "llm"]
Data2Mode = Literal["single", "matrix"]


@dataclass(frozen=True)
class AutoWfsPlan:
    mode: AutoMode
    season: str
    start_season: str
    end_season: str
    timeframes_min: list[int]
    strategy_ids: list[str]
    instrument_ids: list[str]
    data2_mode: Data2Mode
    data2_candidates_by_instrument: dict[str, list[str]]
    max_workers: int
    auto_finalize: bool
    select_policy: Literal["recommended", "all"]

    @property
    def required_datasets(self) -> set[str]:
        out: set[str] = set(self.instrument_ids)
        for cands in self.data2_candidates_by_instrument.values():
            for v in cands:
                out.add(v)
        return out


def _any_strategy_requires_secondary_data(strategy_ids: list[str]) -> bool:
    reg = load_strategy_registry_yaml()
    for sid in strategy_ids:
        entry = reg.get(str(sid).strip())
        if entry and bool(entry.raw.get("requires_secondary_data")):
            return True
    return False


def plan_from_portfolio_spec(
    spec: PortfolioSpecV1,
    *,
    mode: AutoMode = "deterministic",
    season: str | None = None,
    timeframes_min: list[int] | None = None,
    data2_dataset_id: str | None = None,
    data2_mode: Data2Mode = "matrix",
    max_workers: int = 1,
    auto_finalize: bool = True,
    select_policy: Literal["recommended", "all"] = "recommended",
) -> AutoWfsPlan:
    # Season range:
    # - `plan.season` is a *snapshot/build season* used for cache/artifacts paths.
    # - `plan.start_season` / `plan.end_season` define the WFS window range.
    #
    # V1 rule:
    # - If spec.seasons has length 1: treat it as a single-quarter run.
    # - If spec.seasons has length >= 2: treat [first, last] as the inclusive season range.
    chosen = (season or "").strip() or spec.seasons[-1]
    start = spec.seasons[0]
    end = spec.seasons[-1]

    tfs = [int(x) for x in (timeframes_min or [60])]
    if not tfs:
        tfs = [60]

    data2_override = str(data2_dataset_id).strip() if data2_dataset_id else None
    if data2_override:
        data2_map = {ins: [data2_override] for ins in spec.instrument_ids}
        chosen_mode: Data2Mode = "single"
    else:
        chosen_mode = data2_mode
        if data2_mode == "single":
            prim = data2_primary_by_data1(spec.instrument_ids)
            data2_map = {ins: ([v] if v else []) for ins, v in prim.items()}
        else:
            data2_map = data2_candidates_by_data1(spec.instrument_ids)

    # If none of the selected strategies require data2, suppress it entirely.
    # This makes baseline closure runs deterministic and cheaper, while still allowing
    # matrix runs for strategies that explicitly require secondary data.
    if not _any_strategy_requires_secondary_data(list(spec.strategy_ids)):
        data2_map = {ins: [] for ins in spec.instrument_ids}
        chosen_mode = "single"

    return AutoWfsPlan(
        mode=mode,
        season=chosen,
        start_season=start,
        end_season=end,
        timeframes_min=tfs,
        strategy_ids=list(spec.strategy_ids),
        instrument_ids=list(spec.instrument_ids),
        data2_mode=chosen_mode,
        data2_candidates_by_instrument=data2_map,
        max_workers=int(max_workers),
        auto_finalize=bool(auto_finalize),
        select_policy=select_policy,
    )


def default_portfolio_spec_path() -> Path:
    return Path("configs/portfolio/portfolio_spec_v1.yaml")


def auto_runs_root() -> Path:
    # Keep under artifacts so it's discoverable and immutable-ish.
    return get_outputs_root() / "artifacts" / "auto_runs"
