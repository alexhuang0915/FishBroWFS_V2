"""Portfolio-related schemas for signal series and instrument configuration."""

from pydantic import BaseModel, ConfigDict, Field
from typing import Literal, Dict


class InstrumentsConfigV1(BaseModel):
    """Schema for instruments configuration YAML (version 1)."""
    version: int
    base_currency: str
    fx_rates: Dict[str, float]
    instruments: Dict[str, dict]  # 這裡可先放 dict，validate 在 loader 做


class SignalSeriesMetaV1(BaseModel):
    """Metadata for signal series (bar-based position/margin/notional)."""
    model_config = ConfigDict(populate_by_name=True)
    
    schema_id: Literal["SIGNAL_SERIES_V1"] = Field(
        default="SIGNAL_SERIES_V1",
        alias="schema"
    )
    instrument: str
    timeframe: str
    tz: str

    base_currency: str
    instrument_currency: str
    fx_to_base: float

    multiplier: float
    initial_margin_per_contract: float
    maintenance_margin_per_contract: float

    # traceability
    source_run_id: str
    source_spec_sha: str
    instruments_config_sha256: str