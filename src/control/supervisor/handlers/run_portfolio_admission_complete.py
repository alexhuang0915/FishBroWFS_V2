# This is the continuation of the handler - I'll append it to the main file
# 5. Money-sense UI metric
money_sense_metric = self._compute_money_sense_metric(
    research_results=research_results,
    allocated_run_ids=stacking_result.allocated_run_ids,
    portfolio_config=portfolio_config
)

# Build admission report
now = datetime.now(timezone.utc).isoformat()

# Determine verdict
verdict = "ADMITTED"
if len(stacking_result.allocated_run_ids) == 0:
    verdict = "REJECTED"
elif len(stacking_result.allocated_run_ids) < len(run_ids):
    verdict = "PARTIAL"

# Create summary
summary_parts = []
if correlation_result.passed:
    summary_parts.append("Correlation gate passed")
else:
    summary_parts.append(f"Correlation gate: {correlation_result.violating_pairs} violations")

summary_parts.append(f"Allocated {len(stacking_result.allocated_run_ids)} of {len(run_ids)} runs")
summary_parts.append(f"Pain index: {pain_index_result.pain_index:.3f}")
summary_parts.append(f"Diversification benefit: {marginal_result.diversification_benefit:.1%}")

summary = "; ".join(summary_parts)

# Create placeholder admission decision (will be filled by _generate_admission_decision)
placeholder_decision = {
    "verdict": "ADMITTED",
    "admitted_run_ids": stacking_result.allocated_run_ids,
    "rejected_run_ids": [rid for rid in run_ids if rid not in stacking_result.allocated_run_ids],
    "reasons": {},
    "portfolio_id": portfolio_id,
    "evaluated_at_utc": now
}

return AdmissionReportSection(
    portfolio_id=portfolio_id,
    analyzed_at=now,
    input_run_ids=run_ids,
    total_runs=len(run_ids),
    admitted_runs=len(stacking_result.allocated_run_ids),
    rejected_runs=len(run_ids) - len(stacking_result.allocated_run_ids),
    correlation_gate=correlation_result,
    portfolio_stacking=stacking_result,
    dynamic_pain_index=pain_index_result,
    marginal_contribution=marginal_result,
    money_sense_metric=money_sense_metric,
    verdict=verdict,
    admission_decision=placeholder_decision,
    summary=summary
)

def _run_correlation_analysis(
    self,
    research_results: Dict[str, ResearchWFSResult],
    threshold: float
) -> CorrelationGateResult:
    """Run correlation gate analysis."""
    run_ids = list(research_results.keys())
    violations = []
    total_pairs = 0
    violating_pairs = 0
    
    # Compute pairwise correlations
    for i, run_id1 in enumerate(run_ids):
        for j, run_id2 in enumerate(run_ids):
            if i >= j:  # Skip self and duplicate pairs
                continue
            
            total_pairs += 1
            
            # Extract OOS equity series
            series1 = extract_oos_equity_series(research_results[run_id1])
            series2 = extract_oos_equity_series(research_results[run_id2])
            
            # Compute correlation
            correlation = compute_correlation(series1, series2)
            
            # Check if correlation exceeds threshold (absolute value)
            if abs(correlation) > threshold:
                violating_pairs += 1
                violations.append({
                    "run_id1": run_id1,
                    "run_id2": run_id2,
                    "correlation": correlation,
                    "threshold": threshold
                })
    
    passed = violating_pairs == 0
    
    return CorrelationGateResult(
        passed=passed,
        violations=violations,
        threshold=threshold,
        total_pairs=total_pairs,
        violating_pairs=violating_pairs
    )

def _run_portfolio_stacking(
    self,
    research_results: Dict[str, ResearchWFSResult],
    portfolio_config: PortfolioConfigSection,
    correlation_violations: List[str]
) -> PortfolioStackingResult:
    """Run portfolio stacking (risk-budget allocation)."""
    run_ids = list(research_results.keys())
    
    # Filter out runs with correlation violations
    # Simple heuristic: exclude runs involved in high correlations
    excluded_runs = set()
    for run_id in run_ids:
        if run_id in correlation_violations:
            excluded_runs.add(run_id)
    
    # Also exclude runs with poor performance (OOS net <= 0)
    for run_id, result in research_results.items():
        oos_metrics = result.windows[0].oos_metrics if result.windows else {}
        oos_net = oos_metrics.get("net", 0)
        if oos_net <= 0:
            excluded_runs.add(run_id)
    
    # Determine allocated runs
    allocated_run_ids = [rid for rid in run_ids if rid not in excluded_runs]
    
    # Simple equal-weight allocation
    allocation_weights = {}
    if allocated_run_ids:
        weight = 1.0 / len(allocated_run_ids)
        for run_id in allocated_run_ids:
            allocation_weights[run_id] = weight
    
    # Determine lots per run (simplified)
    lots_per_run = {}
    for run_id in allocated_run_ids:
        # Simple heuristic: 1 lot per strategy up to max
        lots = min(portfolio_config.max_lots_per_strategy, 
                  max(portfolio_config.min_lots_per_strategy, 1))
        lots_per_run[run_id] = lots
    
    # Calculate risk budget usage
    risk_budget_used = len(allocated_run_ids) * portfolio_config.risk_budget_per_strategy
    risk_budget_total = portfolio_config.total_capital * portfolio_config.target_volatility
    
    return PortfolioStackingResult(
        allocated_run_ids=allocated_run_ids,
        allocation_weights=allocation_weights,
        risk_budget_used=risk_budget_used,
        risk_budget_total=risk_budget_total,
        lots_per_run=lots_per_run
    )

def _run_dynamic_pain_index_analysis(
    self,
    research_results: Dict[str, ResearchWFSResult],
    allocated_run_ids: List[str]
) -> DynamicPainIndexResult:
    """Run dynamic pain index analysis."""
    if not allocated_run_ids:
        return DynamicPainIndexResult(
            pain_index=0.0,
            max_drawdown_pct=0.0,
            max_drawdown_abs=0.0,
            underwater_days=0,
            recovery_time_days=0,
            severity_score=0.0
        )
    
    # Combine equity series of allocated runs (simple average)
    combined_series = []
    first_run_id = allocated_run_ids[0]
    first_series = extract_oos_equity_series(research_results[first_run_id])
    
    # Initialize with timestamps from first series
    for point in first_series:
        combined_series.append({
            "t": point["t"],
            "v": point["v"]  # Will be averaged
        })
    
    # Average across all allocated runs
    for run_id in allocated_run_ids[1:]:
        series = extract_oos_equity_series(research_results[run_id])
        series_dict = {p["t"]: p["v"] for p in series}
        
        for i, point in enumerate(combined_series):
            timestamp = point["t"]
            if timestamp in series_dict:
                combined_series[i]["v"] += series_dict[timestamp]
    
    # Divide by number of runs to get average
    num_runs = len(allocated_run_ids)
    for point in combined_series:
        point["v"] /= num_runs
    
    # Convert to EquityPoint format
    equity_points = [EquityPoint(t=p["t"], v=p["v"]) for p in combined_series]
    
    # Compute metrics
    max_drawdown_pct, max_drawdown_abs, underwater_days = compute_drawdown_metrics(equity_points)
    pain_index = compute_pain_index(equity_points)
    
    # Simple severity score (0-100, lower is better)
    severity_score = min(100.0, pain_index * 100 + max_drawdown_pct)
    
    # Estimate recovery time (simplified)
    recovery_time_days = min(365, int(underwater_days * 1.5))
    
    return DynamicPainIndexResult(
        pain_index=pain_index,
        max_drawdown_pct=max_drawdown_pct,
        max_drawdown_abs=max_drawdown_abs,
        underwater_days=underwater_days,
        recovery_time_days=recovery_time_days,
        severity_score=severity_score
    )

def _run_marginal_contribution_analysis(
    self,
    research_results: Dict[str, ResearchWFSResult],
    allocated_run_ids: List[str]
) -> MarginalContributionResult:
    """Run marginal contribution analysis (risk attribution)."""
    if not allocated_run_ids:
        return MarginalContributionResult(
            contributions={},
            total_risk=0.0,
            diversification_benefit=0.0
        )
    
    # Simple risk contribution based on volatility
    contributions = {}
    volatilities = {}
    
    for run_id in allocated_run_ids:
        series = extract_oos_equity_series(research_results[run_id])
        values = [p["v"] for p in series]
        
        if len(values) < 2:
            volatility = 0.0
        else:
            # Compute standard deviation of returns
            returns = []
            for i in range(1, len(values)):
                if values[i-1] != 0:
                    ret = (values[i] - values[i-1]) / abs(values[i-1])
                    returns.append(ret)
            
            if returns:
                volatility = statistics.stdev(returns) if len(returns) > 1 else 0.0
            else:
                volatility = 0.0
        
        volatilities[run_id] = volatility
    
    # Total portfolio volatility (simplified as average)
    total_volatility = sum(volatilities.values()) / len(volatilities) if volatilities else 0.0
    
    # Contribution as proportion of total volatility
    for run_id, vol in volatilities.items():
        if total_volatility > 0:
            contribution = vol / total_volatility / len(volatilities)
        else:
            contribution = 1.0 / len(volatilities) if volatilities else 0.0
        contributions[run_id] = contribution
    
    # Diversification benefit (simplified)
    # 1 - (portfolio_vol / sum(individual_vols))
    sum_individual_vols = sum(volatilities.values())
    if sum_individual_vols > 0:
        diversification_benefit = 1.0 - (total_volatility * len(volatilities) / sum_individual_vols)
        diversification_benefit = max(0.0, min(1.0, diversification_benefit))
    else:
        diversification_benefit = 0.0
    
    return MarginalContributionResult(
        contributions=contributions,
        total_risk=total_volatility,
        diversification_benefit=diversification_benefit
    )

def _compute_money_sense_metric(
    self,
    research_results: Dict[str, ResearchWFSResult],
    allocated_run_ids: List[str],
    portfolio_config: PortfolioConfigSection
) -> MoneySenseMetric:
    """Compute money-sense UI metric (dual MDD representation)."""
    if not allocated_run_ids:
        return MoneySenseMetric(
            mdd_percentage=0.0,
            mdd_absolute=0.0,
            currency=portfolio_config.currency,
            capital_at_risk=0.0,
            risk_adjusted_return=0.0
        )
    
    # Get combined equity series
    combined_series = []
    first_run_id = allocated_run_ids[0]
    first_series = extract_oos_equity_series(research_results[first_run_id])
    
    for point in first_series:
        combined_series.append({
            "t": point["t"],
            "v": point["v"]
        })
    
    for run_id in allocated_run_ids[1:]:
        series = extract_oos_equity_series(research_results[run_id])
        series_dict = {p["t"]: p["v"] for p in series}
        
        for i, point in enumerate(combined_series):
            timestamp = point["t"]
            if timestamp in series_dict:
                combined_series[i]["v"] += series_dict[timestamp]
    
    num_runs = len(allocated_run_ids)
    for point in combined_series:
        point["v"] /= num_runs
    
    equity_points = [EquityPoint(t=p["t"], v=p["v"]) for p in combined_series]
    
    # Compute drawdown metrics
    max_drawdown_pct, max_drawdown_abs, _ = compute_drawdown_metrics(equity_points)
    
    # Capital at risk (simplified)
    capital_at_risk = portfolio_config.total_capital * (max_drawdown_pct / 100)
    
    # Risk-adjusted return (simplified Sharpe-like ratio)
    values = [p["v"] for p in equity_points]
    if len(values) > 1:
        total_return = (values[-1] - values[0]) / abs(values[0]) if values[0] != 0 else 0.0
        risk_adjusted_return = total_return / max_drawdown_pct if max_drawdown_pct > 0 else 0.0
    else:
        risk_adjusted_return = 0.0
    
    return MoneySenseMetric(
        mdd_percentage=max_drawdown_pct,
        mdd_absolute=max_drawdown_abs,
        currency=portfolio_config.currency,
        capital_at_risk=capital_at_risk,
        risk_adjusted_return=risk_adjusted_return
    )

def _generate_admission_decision(
    self,
    portfolio_id: str,
    admission_report: AdmissionReportSection,
    research_results: Dict[str, ResearchWFSResult]
) -> AdmissionDecision:
    """Generate formal admission decision."""
    now = datetime.now(timezone.utc).isoformat()
    
    # Determine verdict based on admission report
    if admission_report.verdict == "REJECTED":
        verdict = AdmissionVerdict.REJECTED
    else:
        verdict = AdmissionVerdict.ADMITTED
    
    # Build reasons for rejected runs
    reasons = {}
    allocated_set = set(admission_report.portfolio_stacking.allocated_run_ids)
    
    for run_id in research_results.keys():
        if run_id not in allocated_set:
            # Determine reason for rejection
            result = research_results[run_id]
            oos_metrics = result.windows[0].oos_metrics if result.windows else {}
            oos_net = oos_metrics.get("net", 0)
            
            if oos_net <= 0:
                reasons[run_id] = "OOS net profit <= 0"
            else:
                reasons[run_id] = "Excluded due to correlation violations or risk budget constraints"
    
    return AdmissionDecision(
        verdict=verdict,
        admitted_run_ids=admission_report.portfolio_stacking.allocated_run_ids,
        rejected_run_ids=[rid for rid in research_results.keys() 
                        if rid not in admission_report.portfolio_stacking.allocated_run_ids],
        reasons=reasons,
        portfolio_id=portfolio_id,
        evaluated_at_utc=now
    )

def _write_artifacts(
    self,
    context: JobContext,
    portfolio_config: PortfolioConfigSection,
    admission_report: AdmissionReportSection,
    admission_decision: AdmissionDecision
) -> None:
    """Write portfolio admission artifacts."""
    artifacts_dir = Path(context.artifacts_dir)
    
    # 1. Write portfolio_config.json
    config_path = artifacts_dir / "portfolio_config.json"
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(portfolio_config.model_dump(), f, indent=2, ensure_ascii=False)
    
    # 2. Write admission_report.json
    report_path = artifacts_dir / "admission_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(admission_report.model_dump(), f, indent=2, ensure_ascii=False)
    
    # 3. Write admission_decision.json (using the schema from contracts)
    decision_path = artifacts_dir / "admission_decision.json"
    with open(decision_path, "w", encoding="utf-8") as f:
        json.dump(admission_decision.model_dump(), f, indent=2, ensure_ascii=False)
    
    # 4. Write summary.txt
    summary_path = artifacts_dir / "summary.txt"
    with open(summary_path, "w", encoding="utf-8") as f:
        f.write(f"Portfolio Admission Results\n")
        f.write(f"==========================\n")
        f.write(f"Portfolio ID: {portfolio_config.portfolio_id}\n")
        f.write(f"Verdict: {admission_decision.verdict.value}\n")
        f.write(f"Admitted runs: {len(admission_decision.admitted_run_ids)}\n")
        f.write(f"Rejected runs: {len(admission_decision.rejected_run_ids)}\n")
        f.write(f"\nSummary: {admission_report.summary}\n")
    
    logger.info(f"Wrote portfolio admission artifacts to {artifacts_dir}")


# Create handler instance
run_portfolio_admission_handler = RunPortfolioAdmissionHandler()