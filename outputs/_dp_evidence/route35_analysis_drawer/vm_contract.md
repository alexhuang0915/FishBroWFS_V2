# Route 3.5: ViewModel/Adapter Contract

## Discovery Summary

### Existing Components Found

1. **`analysis_drawer_widget.py`** - Basic drawer container
   - Slide-in animation from right
   - Backdrop with click-to-close
   - Basic header with close button
   - Placeholder for report content
   - Uses `JobAnalysisVM` from `hybrid_bc_vms.py`

2. **`analysis_widget.py`** - Comprehensive analysis suite (917 lines)
   - 4 tabs: Dashboard, Risk, Period, Trades
   - Matplotlib charts with dark theme
   - KPI cards, equity curve, metrics grid
   - Trade history table with statistics
   - Loads data from artifact directories

3. **`hybrid_bc_vms.py`** - Existing ViewModels
   - `JobIndexVM` (Layer 1) - No metrics
   - `JobContextVM` (Layer 2) - No metrics
   - `JobAnalysisVM` (Layer 3) - Allows metrics in payload

## Enhanced ViewModel Design

### 1. `JobAnalysisVM` Enhancement
Extend existing `JobAnalysisVM` with structured fields for TradingView-grade UX:

```python
@dataclass
class JobAnalysisVM:
    """ViewModel for Layer 3 (Analysis Drawer) - Enhanced for Route 3.5."""
    
    # Core identification
    job_id: str
    short_id: str  # First 8 chars for display
    
    # Job context (from JobContextVM)
    strategy_name: str
    instrument: str
    timeframe: str
    run_mode: str
    season: str
    created_at: str
    
    # Data status (from DatasetResolver)
    data1_status: str  # "READY", "MISSING", "STALE", "UNKNOWN"
    data2_status: str
    data1_id: Optional[str]
    data2_id: Optional[str]
    
    # Gate summary (from Gatekeeper)
    gate_summary: GateSummaryVM
    
    # Performance metrics (structured)
    metrics: PerformanceMetricsVM
    
    # Time series data (for charts)
    series: TimeSeriesVM
    
    # Trade data
    trades: List[TradeRowVM]
    
    # Artifacts
    artifacts: List[ArtifactItemVM]
    
    # Raw payload (backward compatibility)
    payload: Dict[str, Any] = field(default_factory=dict)
```

### 2. Supporting ViewModels

#### `GateSummaryVM`
```python
@dataclass
class GateSummaryVM:
    """Gate summary for display in Analysis Drawer."""
    total_permutations: int
    valid_candidates: int
    plateau_check: Literal["Pass", "Fail", "N/A"]
    gate_status: Literal["PASS", "WARNING", "FAIL"]
    failure_reasons: List[str]  # If FAIL, bullet reasons
```

#### `PerformanceMetricsVM`
```python
@dataclass
class PerformanceMetricsVM:
    """Structured performance metrics with ranges/bands."""
    
    # Core metrics with ranges
    sharpe: MetricWithRange
    max_drawdown: MetricWithRange
    win_rate: MetricWithRange
    profit_factor: MetricWithRange
    expectancy: MetricWithRange
    
    # Additional metrics
    net_profit: float
    total_trades: int
    avg_trade: float
    sqn: float  # System Quality Number
    
    # Qualitative bands
    @dataclass
    class MetricWithRange:
        value: float
        band: Literal["Excellent", "Good", "Fair", "Poor", "Very Poor"]
        percentile: float  # 0-100
        min_range: float
        max_range: float
```

#### `TimeSeriesVM`
```python
@dataclass
class TimeSeriesVM:
    """Time series data for charting with downsampling support."""
    
    # Equity curve
    equity_timestamps: List[datetime]
    equity_values: List[float]
    
    # Drawdown
    drawdown_timestamps: List[datetime]
    drawdown_values: List[float]  # Negative values
    
    # Downsampling metadata
    original_count: int
    downsampled_count: int
    downsampling_method: Literal["LTTB", "uniform", "none"]
    
    # Chart display hints
    suggested_chart_type: Literal["line", "area", "candlestick"]
    y_axis_label: str = "Equity ($)"
```

#### `TradeRowVM`
```python
@dataclass
class TradeRowVM:
    """Individual trade for display in table and chart highlighting."""
    
    entry_time: datetime
    exit_time: datetime
    side: Literal["LONG", "SHORT"]
    entry_price: float
    exit_price: float
    pnl: float
    return_pct: float
    bars_held: int
    
    # For chart highlighting
    chart_x_position: Optional[float] = None  # Position in chart coordinates
    is_best_trade: bool = False
    is_worst_trade: bool = False
```

#### `ArtifactItemVM`
```python
@dataclass
class ArtifactItemVM:
    """Artifact file available for viewing."""
    
    name: str
    display_name: str
    file_type: Literal["json", "parquet", "csv", "png", "pdf", "txt"]
    size_bytes: int
    relative_path: str  # Relative to job directory
    
    # Viewer capabilities
    can_preview: bool
    preview_type: Optional[Literal["text", "image", "table", "chart"]]
```

### 3. Adapter Layer Contract

#### `AnalysisDataAdapter`
```python
class AnalysisDataAdapter:
    """Adapter to convert raw API responses to structured ViewModels."""
    
    @staticmethod
    def from_job_payload(job_id: str, payload: Dict[str, Any]) -> JobAnalysisVM:
        """Convert raw job payload to structured JobAnalysisVM."""
        # Extract metrics
        metrics = PerformanceMetricsVM(
            sharpe=MetricWithRange(
                value=payload.get("sharpe", 0.0),
                band=_calculate_band("sharpe", payload.get("sharpe", 0.0)),
                percentile=_calculate_percentile("sharpe", payload.get("sharpe", 0.0)),
                min_range=0.0,
                max_range=3.0
            ),
            # ... other metrics
        )
        
        # Extract time series with downsampling
        equity_data = payload.get("equity_curve", [])
        series = TimeSeriesVM(
            equity_timestamps=[item["ts"] for item in equity_data],
            equity_values=[item["equity"] for item in equity_data],
            original_count=len(equity_data),
            downsampled_count=min(len(equity_data), 5000),  # Downsample if > 5000
            downsampling_method="LTTB" if len(equity_data) > 5000 else "none"
        )
        
        # Extract trades
        trades_data = payload.get("trades", [])
        trades = [
            TradeRowVM(
                entry_time=trade["entry_ts"],
                exit_time=trade["exit_ts"],
                side=trade["side"],
                entry_price=trade["entry_px"],
                exit_price=trade["exit_px"],
                pnl=trade["pnl"],
                return_pct=trade.get("return_pct", 0.0),
                bars_held=trade.get("bars_held", 0)
            )
            for trade in trades_data
        ]
        
        # Mark best/worst trades
        if trades:
            best_trade = max(trades, key=lambda t: t.pnl)
            worst_trade = min(trades, key=lambda t: t.pnl)
            best_trade.is_best_trade = True
            worst_trade.is_worst_trade = True
        
        return JobAnalysisVM(
            job_id=job_id,
            short_id=job_id[:8],
            # ... other fields
            metrics=metrics,
            series=series,
            trades=trades,
            payload=payload  # Keep raw for backward compatibility
        )
    
    @staticmethod
    def downsample_series(timestamps: List[datetime], values: List[float], 
                         max_points: int = 5000) -> Tuple[List[datetime], List[float]]:
        """Downsample time series using LTTB (Largest Triangle Three Buckets)."""
        if len(timestamps) <= max_points:
            return timestamps, values
        
        # Implement LTTB downsampling
        # ... implementation details
        
        return downsampled_timestamps, downsampled_values
```

### 4. Integration Points

#### Existing Integration
1. **Drawer Opening**: `analysis_drawer_widget.py` → `open_for_job(job_id, vm)`
2. **Data Loading**: Currently loads raw payload into `JobAnalysisVM`

#### Enhanced Integration
1. **Adapter Usage**: 
   ```python
   # In drawer opening logic
   raw_payload = fetch_job_analysis_data(job_id)
   vm = AnalysisDataAdapter.from_job_payload(job_id, raw_payload)
   drawer.open_for_job(job_id, vm)
   ```

2. **UI Component Binding**:
   - `JobContextBar` ← `JobAnalysisVM.strategy_name`, `instrument`, `timeframe`, `data1_status`, `data2_status`
   - `ChartCanvas` ← `TimeSeriesVM.equity_timestamps`, `equity_values`
   - `MetricRangeCardGrid` ← `PerformanceMetricsVM` with bands
   - `GateSummaryCard` ← `GateSummaryVM`
   - `TradeHighlightsCard` ← `List[TradeRowVM]` filtered for best/worst
   - `ArtifactIndexCard` ← `List[ArtifactItemVM]`

### 5. Data Flow

```
Raw API Response (JSON)
        ↓
AnalysisDataAdapter (converts to structured VMs)
        ↓
JobAnalysisVM (enhanced with all structured data)
        ↓
Analysis Drawer UI Components
        ├── JobContextBar (context + data status)
        ├── ChartCanvas (equity/drawdown charts)
        ├── MetricRangeCardGrid (performance metrics with bands)
        ├── GateSummaryCard (gate status)
        ├── TradeHighlightsCard (best/worst trades)
        └── ArtifactIndexCard (available artifacts)
```

### 6. Backward Compatibility

1. **Existing `JobAnalysisVM`**: Keep `payload` field for backward compatibility
2. **Existing `analysis_drawer_widget.py`**: Can still work with basic VM
3. **Gradual Migration**: New components use structured fields, fall back to payload if missing

### 7. Performance Considerations

1. **Downsampling**: Automatically downsample series > 5000 points for 60fps
2. **Lazy Loading**: Load heavy data (trades, artifacts) on demand
3. **Caching**: Cache adapter results for same job_id
4. **Memory**: Release series data when drawer closes

### 8. Testing Strategy

1. **Adapter Tests**: Verify conversion from raw payload to VMs
2. **Downsampling Tests**: Verify LTTB algorithm correctness
3. **Integration Tests**: Verify drawer opens/closes with VM
4. **Performance Tests**: Verify 60fps with 10k+ points

## Next Steps

1. Implement `AnalysisDataAdapter` class
2. Enhance `JobAnalysisVM` with new fields
3. Update `analysis_drawer_widget.py` to use enhanced VM
4. Create new UI components (JobContextBar, MetricRangeCardGrid, etc.)
5. Integrate existing `analysis_widget.py` charts into drawer
6. Add right-click context menus
7. Implement tests