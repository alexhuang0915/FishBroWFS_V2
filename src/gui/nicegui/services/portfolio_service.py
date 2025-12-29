"""Portfolio service - save/load portfolio artifacts."""
import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


def save_portfolio(
    portfolio: Dict[str, Any],
    outputs_root: Path = Path("outputs"),
    season: str = "2026Q1",
    portfolio_id: Optional[str] = None,
) -> Path:
    """Save portfolio artifact.
    
    Args:
        portfolio: Portfolio specification.
        outputs_root: Root outputs directory.
        season: Season identifier.
        portfolio_id: Optional portfolio ID; generates if None.
    
    Returns:
        Path to saved portfolio JSON.
    """
    if portfolio_id is None:
        import uuid
        portfolio_id = f"portfolio_{uuid.uuid4().hex[:8]}"
    
    portfolio_dir = outputs_root / "seasons" / season / "portfolios"
    portfolio_dir.mkdir(parents=True, exist_ok=True)
    
    portfolio_path = portfolio_dir / f"{portfolio_id}.json"
    with open(portfolio_path, "w", encoding="utf-8") as f:
        json.dump(portfolio, f, indent=2, ensure_ascii=False)
    
    logger.info(f"Portfolio saved to {portfolio_path}")
    return portfolio_path


def load_portfolio(portfolio_id: str, season: str = "2026Q1") -> Optional[Dict[str, Any]]:
    """Load portfolio artifact."""
    portfolio_path = Path("outputs") / "seasons" / season / "portfolios" / f"{portfolio_id}.json"
    if not portfolio_path.exists():
        return None
    try:
        with open(portfolio_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Failed to load portfolio: {e}")
        return None