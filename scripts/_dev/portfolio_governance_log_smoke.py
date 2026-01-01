#!/usr/bin/env python3
"""
Smoke test for portfolio governance logging.
Writes a dummy event + artifact, prints created paths.
"""
import sys
import tempfile
from pathlib import Path

# Ensure src is in path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from portfolio.models.governance_models import (
    StrategyIdentity,
    GovernanceLogEvent,
    ReasonCode,
    StrategyState,
    GovernanceParams,
)
from portfolio.governance.logging import (
    governance_root,
    write_artifact_json,
    append_governance_event,
    now_utc_iso,
)


def main() -> None:
    print("=== Portfolio Governance Log Smoke Test ===")

    # Use a temporary directory for outputs to avoid polluting real outputs
    import shutil
    import atexit

    tmp = Path(tempfile.mkdtemp(prefix="gov_smoke_"))
    atexit.register(lambda: shutil.rmtree(tmp, ignore_errors=True))

    # Monkey‑patch governance_root to point to the temporary directory
    import portfolio.governance.logging as logging_module
    original_root = logging_module.governance_root
    logging_module.governance_root = lambda: tmp

    try:
        # 1. Write a dummy artifact
        params = GovernanceParams()
        artifact_path = write_artifact_json("test_params.json", params)
        print(f"Artifact written: {artifact_path}")

        # 2. Create a dummy identity
        identity = StrategyIdentity(
            strategy_id="S2_999",
            version_hash="abc123",
            universe={"symbol": "MNQ", "timeframe": "5m", "session": "RTH", "venue": "CME"},
            data_fingerprint="fingerprint123",
            cost_model_id="cost_v1",
            tags=["Trend"],
        )

        # 3. Create a log event
        event = GovernanceLogEvent(
            timestamp_utc=now_utc_iso(),
            actor="smoke_test",
            strategy_key=identity.identity_key(),
            from_state=StrategyState.INCUBATION,
            to_state=StrategyState.CANDIDATE,
            reason_code=ReasonCode.PROMOTE_TO_PAPER,
            attached_artifacts=[str(artifact_path.relative_to(tmp))],
            data_fingerprint="fingerprint123",
            extra={"test": True},
        )

        # 4. Append to log
        log_path = append_governance_event(event)
        print(f"Log appended: {log_path}")

        # 5. Show log content
        if log_path.exists():
            lines = log_path.read_text().strip().split("\n")
            print(f"Log lines: {len(lines)}")
            for line in lines[-2:]:  # last couple lines
                print(f"  {line}")

        print("Smoke test PASSED")
    finally:
        # Restore original function
        logging_module.governance_root = original_root


if __name__ == "__main__":
    main()