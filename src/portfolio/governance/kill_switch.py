"""
Kill‑switch engine for strategy‑level and portfolio‑level circuit breakers.
"""
from typing import Dict, Tuple

from ..models.governance_models import (
    GovernanceParams,
    KillSwitchReport,
    ReasonCode,
    StrategyState,
)
from .state_machine import PortfolioGovernanceStore, transition
from .governance_logging import write_artifact_json, now_utc_iso, governance_root


# ========== Strategy‑Level Kill Switch ==========

def should_kill_strategy(
    dd_live: float,
    dd_reference: float,
    params: GovernanceParams,
) -> Tuple[bool, float]:
    """
    Determine whether a strategy's live drawdown exceeds the kill threshold.

    Threshold = max(dd_reference * dd_k_multiplier, dd_absolute_cap)

    Returns (triggered, threshold).
    """
    threshold = max(dd_reference * params.dd_k_multiplier, params.dd_absolute_cap)
    triggered = dd_live > threshold
    return triggered, threshold


def handle_strategy_kill(
    store: PortfolioGovernanceStore,
    strategy_key: str,
    dd_live: float,
    dd_reference: float,
    params: GovernanceParams,
    actor: str = "worker",
) -> str:
    """
    Evaluate kill condition, write KillSwitchReport, and transition to RETIRED.

    Returns the artifact path (relative to governance root).
    """
    triggered, threshold = should_kill_strategy(dd_live, dd_reference, params)

    # Write report
    report = KillSwitchReport(
        strategy_key=strategy_key,
        dd_live=dd_live,
        dd_reference=dd_reference,
        k_multiplier=params.dd_k_multiplier,
        dd_absolute_cap=params.dd_absolute_cap,
        triggered=triggered,
        reason=(
            f"dd_live {dd_live:.3f} > threshold {threshold:.3f}"
            if triggered else
            f"dd_live {dd_live:.3f} ≤ threshold {threshold:.3f}"
        ),
        timestamp_utc=now_utc_iso(),
    )
    artifact_path = write_artifact_json(
        f"kill_switch_{strategy_key}_{now_utc_iso()[:10]}.json",
        report,
    )

    # If triggered, transition LIVE/PROBATION → RETIRED
    if triggered:
        record = store.get(strategy_key)
        if record and record.state in (StrategyState.LIVE, StrategyState.PROBATION):
            transition(
                store=store,
                strategy_key=strategy_key,
                to_state=StrategyState.RETIRED,
                reason_code=ReasonCode.RETIRE_KILL_SWITCH,
                actor=actor,
                attached_artifacts=[str(artifact_path.relative_to(governance_root()))],
                data_fingerprint=record.identity.data_fingerprint,
                extra={
                    "dd_live": dd_live,
                    "dd_reference": dd_reference,
                    "threshold": threshold,
                },
            )

    return str(artifact_path.relative_to(governance_root()))


# ========== Portfolio‑Level Circuit Breaker ==========

def should_trigger_portfolio_breaker(
    dd_portfolio: float,
    params: GovernanceParams,
) -> bool:
    """Return True if portfolio drawdown exceeds the cap."""
    return dd_portfolio > params.portfolio_dd_cap


def apply_portfolio_breaker(
    weights: Dict[str, float],
    params: GovernanceParams,
) -> Dict[str, float]:
    """
    Reduce exposure by multiplying all weights by exposure_reduction_on_breaker,
    and allocate the remainder to a _CASH bucket.

    Returns a new weight dict that includes a "_CASH" entry.
    """
    if not 0 <= params.exposure_reduction_on_breaker <= 1:
        raise ValueError(
            f"exposure_reduction_on_breaker must be in [0,1], got {params.exposure_reduction_on_breaker}"
        )

    # Scale down all strategy weights
    scaled = {k: v * params.exposure_reduction_on_breaker for k, v in weights.items()}
    cash_weight = 1.0 - sum(scaled.values())

    # Add cash bucket
    scaled["_CASH"] = cash_weight
    return scaled


# ========== Combined Portfolio Breaker Handler ==========

def handle_portfolio_breaker(
    store: PortfolioGovernanceStore,
    dd_portfolio: float,
    current_weights: Dict[str, float],
    params: GovernanceParams,
    actor: str = "worker",
) -> Tuple[bool, Dict[str, float], str]:
    """
    Evaluate portfolio breaker, apply weight reduction, and log event.

    Returns:
        - triggered: bool
        - new_weights: dict with _CASH entry
        - artifact_path: str (relative to governance root)
    """
    triggered = should_trigger_portfolio_breaker(dd_portfolio, params)
    new_weights = current_weights.copy()

    if triggered:
        new_weights = apply_portfolio_breaker(current_weights, params)

        # Log a portfolio‑level event
        from ..models.governance_models import GovernanceLogEvent
        from .governance_logging import append_governance_event

        event = GovernanceLogEvent(
            timestamp_utc=now_utc_iso(),
            actor=actor,
            strategy_key=None,
            from_state=None,
            to_state=None,
            reason_code=ReasonCode.PORTFOLIO_CIRCUIT_BREAKER,
            attached_artifacts=[],
            data_fingerprint=None,
            extra={
                "dd_portfolio": dd_portfolio,
                "portfolio_dd_cap": params.portfolio_dd_cap,
                "exposure_reduction": params.exposure_reduction_on_breaker,
                "weights_before": current_weights,
                "weights_after": new_weights,
            },
        )
        append_governance_event(event)

        # Write a simple artifact for audit
        import json
        from pathlib import Path
        from .governance_logging import governance_root

        artifact = {
            "timestamp_utc": now_utc_iso(),
            "dd_portfolio": dd_portfolio,
            "portfolio_dd_cap": params.portfolio_dd_cap,
            "exposure_reduction": params.exposure_reduction_on_breaker,
            "weights_before": current_weights,
            "weights_after": new_weights,
        }
        artifact_path = governance_root() / "artifacts" / f"portfolio_breaker_{now_utc_iso()[:10]}.json"
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        artifact_path.write_text(json.dumps(artifact, indent=2, sort_keys=True))
        artifact_path_str = str(artifact_path.relative_to(governance_root()))
    else:
        artifact_path_str = ""

    return triggered, new_weights, artifact_path_str