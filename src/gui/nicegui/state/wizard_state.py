"""Wizard page state."""
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any


@dataclass
class WizardState:
    """Wizard UI state (in memory only)."""
    
    # Step 1: Mode
    run_mode: str = "LITE"  # SMOKE, LITE, FULL
    
    # Step 2: Universe
    timeframe: str = "60m"
    instrument: str = "MNQ"
    regime_filters: List[str] = field(default_factory=list)
    regime_none: bool = False
    
    # Step 3: Strategies
    long_strategies: List[str] = field(default_factory=list)  # IDs
    short_strategies: List[str] = field(default_factory=list)
    
    # Step 4: Compute
    compute_level: str = "MID"  # LOW, MID, HIGH
    max_combinations: int = 1000
    
    # Step 5: Product / Risk Assumptions
    margin_model: str = "Symbolic"
    contract_specs: Dict[str, Any] = field(default_factory=dict)
    risk_budget: str = "MEDIUM"
    
    # Derived preview (machine‑computed)
    estimated_combinations: int = 0
    risk_class: str = "LOW"
    execution_plan: Optional[Dict[str, Any]] = None
    
    # UI helpers
    current_step: int = 1
    
    def to_intent_dict(self) -> Dict[str, Any]:
        """Convert current state to intent.json structure."""
        return {
            "identity": {
                "season": "2026Q1",  # TODO: fetch from app state
                "run_mode": self.run_mode,
            },
            "market_universe": {
                "instrument": self.instrument,
                "timeframe": self.timeframe,
                "regime_filters": self.regime_filters if not self.regime_none else [],
            },
            "strategy_space": {
                "long": self.long_strategies,
                "short": self.short_strategies,
            },
            "compute_intent": {
                "compute_level": self.compute_level,
                "max_combinations": self.max_combinations,
            },
            "product_risk_assumptions": {
                "margin_model": self.margin_model,
                "contract_specs": self.contract_specs,
                "risk_budget": self.risk_budget,
            },
        }
    
    def reset(self) -> None:
        """Reset wizard to defaults."""
        self.run_mode = "LITE"
        self.timeframe = "60m"
        self.instrument = "MNQ"
        self.regime_filters.clear()
        self.regime_none = False
        self.long_strategies.clear()
        self.short_strategies.clear()
        self.compute_level = "MID"
        self.max_combinations = 1000
        self.margin_model = "Symbolic"
        self.contract_specs = {}
        self.risk_budget = "MEDIUM"
        self.estimated_combinations = 0
        self.risk_class = "LOW"
        self.execution_plan = None
        self.current_step = 1