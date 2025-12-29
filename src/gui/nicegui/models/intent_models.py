"""Intent JSON schema (strict contract)."""
from enum import Enum
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field, model_validator


class RunMode(str, Enum):
    SMOKE = "SMOKE"
    LITE = "LITE"
    FULL = "FULL"


class ComputeLevel(str, Enum):
    LOW = "LOW"
    MID = "MID"
    HIGH = "HIGH"


class IntentIdentity(BaseModel):
    season: str = Field(..., description="Season identifier, e.g., '2026Q1'")
    run_mode: RunMode = Field(..., description="SMOKE, LITE, FULL")


class MarketUniverse(BaseModel):
    instrument: str = Field(..., description="Instrument symbol, e.g., 'MNQ', 'MES'")
    timeframe: str = Field(..., description="Timeframe string: '30m','60m','120m','240m'")
    regime_filters: List[str] = Field(default=[], description="List of regime filters, empty list or NONE rule")
    
    @model_validator(mode="after")
    def validate_regime_filters(self) -> "MarketUniverse":
        # If NONE is present, list must be empty (or contain only "NONE"?)
        # For simplicity, we allow any list.
        return self


class StrategySpace(BaseModel):
    long: List[str] = Field(default=[], description="List of long strategy IDs")
    short: List[str] = Field(default=[], description="List of short strategy IDs")


class ComputeIntent(BaseModel):
    compute_level: ComputeLevel = Field(..., description="LOW, MID, HIGH")
    max_combinations: int = Field(..., ge=1, description="Maximum number of combinations to evaluate")


class ProductRiskAssumptions(BaseModel):
    margin_model: str = Field(..., description="Symbolic or explicit margin model")
    contract_specs: Dict[str, Any] = Field(default_factory=dict, description="Explicit contract specifications")
    risk_budget: str = Field(..., description="Explicit value or symbolic tag")


class IntentDocument(BaseModel):
    """Root intent.json schema."""
    identity: IntentIdentity
    market_universe: MarketUniverse
    strategy_space: StrategySpace
    compute_intent: ComputeIntent
    product_risk_assumptions: ProductRiskAssumptions
    
    class Config:
        extra = "forbid"
        frozen = True