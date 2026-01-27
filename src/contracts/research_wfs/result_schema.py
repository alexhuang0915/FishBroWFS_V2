"""
Research=WFS result schema v1.0.

Strict, versioned result schema for Research=WFS (Walk-Forward Simulation) pipeline.
This schema defines the canonical result.json structure that MUST be produced by
Phase4-A Research=WFS handler.

Top-level REQUIRED keys:
{
  "version": "1.0",
  "meta": {...},
  "config": {...},
  "estimate": {...},
  "windows": [...],
  "series": {...},
  "metrics": {...},
  "verdict": {...}
}

All values MUST be JSON-serializable (no NaN/inf). Convert to null or 0.0 with warnings.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, TypedDict, Literal
from pydantic import BaseModel, Field, ConfigDict, field_validator
import json


# -----------------------------------------------------------------------------
# Meta section
# -----------------------------------------------------------------------------

class WindowRule(TypedDict):
    """Window rule definition."""
    is_years: int
    oos_quarters: int
    rolling: Literal["quarterly"]


class MetaSection(BaseModel):
    """Meta information about the research run."""
    job_id: str
    run_at: str  # ISO8601
    strategy_family: str
    instrument: str
    timeframe: str
    start_season: str  # e.g., "2020Q1"
    end_season: str    # e.g., "2024Q4"
    window_rule: WindowRule
    
    model_config = ConfigDict(frozen=True)


# -----------------------------------------------------------------------------
# Config section
# -----------------------------------------------------------------------------

class CommissionModel(TypedDict):
    """Commission cost model."""
    model: str  # "per_trade", "per_side", "percentage"
    value: float
    unit: str  # "USD", "ticks", "points", "percent"


class SlippageModel(TypedDict):
    """Slippage cost model."""
    model: str  # "fixed", "percentage", "bps"
    value: float
    unit: str  # "ticks", "points", "percent", "bps"


class CostsConfig(TypedDict):
    """Cost configuration."""
    commission: CommissionModel
    slippage: SlippageModel


class RiskConfig(TypedDict):
    """Risk configuration."""
    risk_unit_1R: float
    stop_model: str


class DataConfig(TypedDict):
    """Data configuration."""
    data1: str
    data2: Optional[str]
    timeframe: str
    actual_time_range: Dict[str, str]  # {"start": ISO, "end": ISO}


class InstrumentConfig(TypedDict):
    """Instrument configuration."""
    symbol: str
    exchange: Optional[str]
    currency: str
    multiplier: float


class FxConfig(TypedDict):
    """FX configuration."""
    base_currency: str
    fx_to_base: Dict[str, float]
    as_of: Optional[str]


class ConfigSection(BaseModel):
    """Configuration used for the research run."""
    instrument: InstrumentConfig
    costs: CostsConfig
    risk: RiskConfig
    data: DataConfig
    fx: Optional[FxConfig] = None
    
    model_config = ConfigDict(frozen=True)


# -----------------------------------------------------------------------------
# Estimate section
# -----------------------------------------------------------------------------

class EstimateSection(BaseModel):
    """Pre-run estimates."""
    strategy_count: int
    param_count: int
    window_count: int
    workers: int
    estimated_runtime_sec: int  # must be >0
    
    @field_validator('estimated_runtime_sec')
    @classmethod
    def runtime_positive(cls, v: int) -> int:
        if v <= 0:
            raise ValueError('estimated_runtime_sec must be >0')
        return v
    
    model_config = ConfigDict(frozen=True)


# -----------------------------------------------------------------------------
# Window section
# -----------------------------------------------------------------------------

class TimeRange(TypedDict):
    """Time range with ISO timestamps."""
    start: str  # ISO8601
    end: str    # ISO8601


class WindowResult(BaseModel):
    """Per-season window result."""
    season: str  # "YYYYQ#"
    is_range: TimeRange
    oos_range: TimeRange
    best_params: Dict[str, Any]
    is_metrics: Dict[str, Any]  # MUST include: net, mdd, trades
    oos_metrics: Dict[str, Any]  # MUST include: net, mdd, trades
    # Optional: detailed OOS trade ledger (round-trip trades only).
    # Keep it window-scoped to avoid exploding result size during grid search.
    oos_trades: List[Dict[str, Any]] = Field(default_factory=list)
    pass_: bool = Field(alias="pass")
    fail_reasons: List[str]
    warnings: List[str] = Field(default_factory=list)
    
    model_config = ConfigDict(frozen=True, populate_by_name=True)


# -----------------------------------------------------------------------------
# Series section
# -----------------------------------------------------------------------------

class EquityPoint(TypedDict):
    """Single equity point."""
    t: str  # ISO timestamp
    v: float  # equity value


class StitchDiagnostic(TypedDict):
    """Diagnostic for stitching."""
    season: str
    jump_abs: float
    jump_pct: float


class SeriesSection(BaseModel):
    """Stitched equity series."""
    stitched_is_equity: List[EquityPoint]
    stitched_oos_equity: List[EquityPoint]
    stitched_bnh_equity: List[EquityPoint]  # B&H baseline REQUIRED
    stitch_diagnostics: Dict[str, List[StitchDiagnostic]]
    drawdown_series: List[Dict[str, Any]]  # may be empty; keep key present
    
    model_config = ConfigDict(frozen=True)


# -----------------------------------------------------------------------------
# Metrics section
# -----------------------------------------------------------------------------

class RawMetrics(TypedDict):
    """Raw aggregated metrics."""
    rf: float  # Return Factor
    wfe: float  # Walk-Forward Efficiency (0..1)
    ecr: float  # Efficiency to Capital Ratio
    trades: int
    pass_rate: float  # (0..1)
    ulcer_index: float
    max_underwater_days: int
    net_profit: float
    max_drawdown: float


class ScoreMetrics(TypedDict):
    """5D expert scores (0..100)."""
    profit: float
    stability: float
    robustness: float
    reliability: float
    armor: float
    total_weighted: float


class MetricsSection(BaseModel):
    """Aggregated metrics and scores."""
    raw: RawMetrics
    scores: ScoreMetrics
    hard_gates_triggered: List[str]
    
    model_config = ConfigDict(frozen=True)


# -----------------------------------------------------------------------------
# Verdict section
# -----------------------------------------------------------------------------

class VerdictSection(BaseModel):
    """Final evaluation verdict."""
    grade: Literal["S", "A", "B", "C", "D"]
    is_tradable: bool
    summary: str
    
    model_config = ConfigDict(frozen=True)


# -----------------------------------------------------------------------------
# Top-level result schema
# -----------------------------------------------------------------------------

class ResearchWFSResult(BaseModel):
    """Complete Research=WFS result schema v1.0."""
    version: Literal["1.0"] = "1.0"
    meta: MetaSection
    config: ConfigSection
    estimate: EstimateSection
    windows: List[WindowResult]
    series: SeriesSection
    metrics: MetricsSection
    verdict: VerdictSection
    warnings: List[str] = Field(default_factory=list)
    
    model_config = ConfigDict(frozen=True)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict with JSON-serializable values."""
        # Use pydantic's model_dump with custom serialization
        def _serialize(obj: Any) -> Any:
            if isinstance(obj, (int, float, str, bool, type(None))):
                return obj
            if isinstance(obj, dict):
                return {k: _serialize(v) for k, v in obj.items()}
            if isinstance(obj, list):
                return [_serialize(item) for item in obj]
            if isinstance(obj, BaseModel):
                return _serialize(obj.model_dump(mode='json'))
            # Handle NaN/inf
            if isinstance(obj, float):
                if obj != obj:  # NaN
                    return None
                if obj == float('inf'):
                    return None
                if obj == float('-inf'):
                    return None
            # Default: try to convert to string
            return str(obj)
        
        data = self.model_dump(mode='json')
        return _serialize(data)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ResearchWFSResult:
        """Create result from dict with validation."""
        return cls.model_validate(data)
    
    def to_json(self, indent: int = 2) -> str:
        """Serialize to JSON string."""
        return json.dumps(self.to_dict(), indent=indent, sort_keys=True, ensure_ascii=False)


# -----------------------------------------------------------------------------
# Helper functions
# -----------------------------------------------------------------------------

def validate_result_json(json_str: str) -> ResearchWFSResult:
    """Validate JSON string against schema."""
    data = json.loads(json_str)
    return ResearchWFSResult.from_dict(data)


def create_stub_result(job_id: str) -> ResearchWFSResult:
    """Create a stub result for testing."""
    from datetime import datetime, timezone
    
    return ResearchWFSResult(
        version="1.0",
        meta=MetaSection(
            job_id=job_id,
            run_at=datetime.now(timezone.utc).isoformat(),
            strategy_family="regime_filter_v1",
            instrument="MNQ",
            timeframe="5m",
            start_season="2020Q1",
            end_season="2024Q4",
            window_rule={"is_years": 3, "oos_quarters": 1, "rolling": "quarterly"}
        ),
        config=ConfigSection(
            instrument={
                "symbol": "MNQ",
                "exchange": "CME",
                "currency": "USD",
                "multiplier": 2.0
            },
            costs={
                "commission": {"model": "per_trade", "value": 0.5, "unit": "USD"},
                "slippage": {"model": "fixed", "value": 0.25, "unit": "ticks"}
            },
            risk={
                "risk_unit_1R": 100.0,
                "stop_model": "atr_stop"
            },
            data={
                "data1": "MNQ_5m",
                "data2": None,
                "timeframe": "5m",
                "actual_time_range": {
                    "start": "2020-01-01T00:00:00Z",
                    "end": "2024-12-31T23:59:59Z"
                }
            }
        ),
        estimate=EstimateSection(
            strategy_count=1,
            param_count=10,
            window_count=16,
            workers=4,
            estimated_runtime_sec=300
        ),
        windows=[],
        series=SeriesSection(
            stitched_is_equity=[],
            stitched_oos_equity=[],
            stitched_bnh_equity=[],
            stitch_diagnostics={"per_season": []},
            drawdown_series=[]
        ),
        metrics=MetricsSection(
            raw={
                "rf": 0.0,
                "wfe": 0.0,
                "ecr": 0.0,
                "trades": 0,
                "pass_rate": 0.0,
                "ulcer_index": 0.0,
                "max_underwater_days": 0,
                "net_profit": 0.0,
                "max_drawdown": 0.0
            },
            scores={
                "profit": 0.0,
                "stability": 0.0,
                "robustness": 0.0,
                "reliability": 0.0,
                "armor": 0.0,
                "total_weighted": 0.0
            },
            hard_gates_triggered=[]
        ),
        verdict=VerdictSection(
            grade="D",
            is_tradable=False,
            summary="Stub result for testing"
        )
    )
