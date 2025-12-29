"""Derive service - compute derived.json from intent.json (MACHINE ONLY)."""
import json
import logging
from pathlib import Path
from typing import Optional

from ..models.intent_models import IntentDocument
from ..models.derived_models import DerivedDocument

logger = logging.getLogger(__name__)


def derive_from_intent(intent: IntentDocument) -> DerivedDocument:
    """Compute derived.json from intent.
    
    This is a placeholder; actual derivation should be deterministic
    and integrate with existing backend logic.
    
    Args:
        intent: Validated intent.
    
    Returns:
        Derived document.
    """
    # Placeholder logic
    estimated = intent.compute_intent.max_combinations
    risk_class = "MEDIUM"
    if intent.compute_intent.compute_level == "LOW":
        risk_class = "LOW"
    elif intent.compute_intent.compute_level == "HIGH":
        risk_class = "HIGH"
    
    execution_plan = {
        "steps": [
            {"action": "validate_intent", "status": "pending"},
            {"action": "expand_strategies", "status": "pending"},
            {"action": "run_simulations", "status": "pending"},
        ]
    }
    
    return DerivedDocument(
        estimated_combinations=estimated,
        risk_class=risk_class,
        execution_plan=execution_plan,
        warnings=["Derivation is placeholder"],
        assumptions={"placeholder": True},
    )


def write_derived(
    derived: DerivedDocument,
    outputs_root: Path = Path("outputs"),
    season: str = "2026Q1",
    run_id: str = "run_placeholder",
) -> Path:
    """Write derived.json to run directory.
    
    Args:
        derived: Derived document.
        outputs_root: Root outputs directory.
        season: Season identifier.
        run_id: Run ID.
    
    Returns:
        Path to derived.json.
    """
    run_dir = outputs_root / "seasons" / season / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    
    derived_path = run_dir / "derived.json"
    with open(derived_path, "w", encoding="utf-8") as f:
        json.dump(derived.model_dump(mode="json"), f, indent=2, ensure_ascii=False)
    
    logger.info(f"Derived written to {derived_path}")
    return derived_path


def derive_and_write(intent_path: Path) -> Optional[Path]:
    """Read intent.json, derive, write derived.json."""
    try:
        with open(intent_path, "r", encoding="utf-8") as f:
            intent_dict = json.load(f)
        intent = IntentDocument.model_validate(intent_dict)
        derived = derive_from_intent(intent)
        # Assume same directory as intent.json
        run_dir = intent_path.parent
        derived_path = run_dir / "derived.json"
        with open(derived_path, "w", encoding="utf-8") as f:
            json.dump(derived.model_dump(mode="json"), f, indent=2, ensure_ascii=False)
        return derived_path
    except Exception as e:
        logger.error(f"Derivation failed: {e}")
        return None