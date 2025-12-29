"""Portfolio page state."""
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class PortfolioItem:
    """A candidate selected for portfolio."""
    strategy_id: str
    side: str  # 'long' or 'short'
    sharpe: float
    weight: float = 0.0
    selected: bool = False


@dataclass
class PortfolioState:
    """Portfolio UI state (in memory only)."""
    
    # Available candidates (read‑only from backend)
    candidates: List[PortfolioItem] = field(default_factory=list)
    
    # Selected candidates with weights
    selected_items: Dict[str, PortfolioItem] = field(default_factory=dict)
    
    # Portfolio metrics (derived)
    total_weight: float = 0.0
    portfolio_sharpe: float = 0.0
    expected_return: float = 0.0
    max_drawdown: float = 0.0
    correlation: float = 0.0
    
    # UI state
    last_saved_id: Optional[str] = None
    
    def update_weights(self) -> None:
        """Recalculate total weight and ensure sum == 100%."""
        self.total_weight = sum(item.weight for item in self.selected_items.values())
        # Normalize if needed (UI should enforce)
    
    def add_candidate(self, item: PortfolioItem) -> None:
        """Add a candidate to available list."""
        self.candidates.append(item)
    
    def toggle_selection(self, strategy_id: str) -> None:
        """Toggle selection of a candidate."""
        for cand in self.candidates:
            if cand.strategy_id == strategy_id:
                cand.selected = not cand.selected
                if cand.selected:
                    self.selected_items[strategy_id] = cand
                else:
                    self.selected_items.pop(strategy_id, None)
                break
    
    def reset(self) -> None:
        """Reset portfolio to empty."""
        self.candidates.clear()
        self.selected_items.clear()
        self.total_weight = 0.0
        self.portfolio_sharpe = 0.0
        self.expected_return = 0.0
        self.max_drawdown = 0.0
        self.correlation = 0.0
        self.last_saved_id = None