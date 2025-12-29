"""Intent service - write intent.json (HUMAN ONLY)."""
import json
import logging
from pathlib import Path
from typing import Optional

from ..models.intent_models import IntentDocument

logger = logging.getLogger(__name__)


def write_intent(
    intent: IntentDocument,
    outputs_root: Path = Path("outputs"),
    season: Optional[str] = None,
    run_id: Optional[str] = None,
) -> Path:
    """Write intent.json to the appropriate run directory.
    
    Args:
        intent: Validated intent document.
        outputs_root: Root outputs directory.
        season: Season identifier; if None, uses intent.identity.season.
        run_id: Run ID; if None, generates a new one (placeholder).
    
    Returns:
        Path to the written intent.json file.
    
    Raises:
        ValueError: If intent validation fails.
        IOError: If directory creation or writing fails.
    """
    if season is None:
        season = intent.identity.season
    if run_id is None:
        # TODO: integrate with backend to generate a proper run_id
        import uuid
        run_id = f"run_{uuid.uuid4().hex[:8]}"
    
    # Ensure run directory exists
    run_dir = outputs_root / "seasons" / season / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    
    intent_path = run_dir / "intent.json"
    
    # Write intent.json (pretty JSON)
    with open(intent_path, "w", encoding="utf-8") as f:
        json.dump(intent.model_dump(mode="json"), f, indent=2, ensure_ascii=False)
    
    logger.info(f"Intent written to {intent_path}")
    return intent_path


def validate_intent(intent_dict: dict) -> tuple[bool, list[str]]:
    """Validate intent dictionary against schema.
    
    Returns:
        (is_valid, list_of_errors)
    """
    try:
        IntentDocument.model_validate(intent_dict)
        return True, []
    except Exception as e:
        return False, [str(e)]