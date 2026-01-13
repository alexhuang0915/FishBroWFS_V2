"""
Hybrid BC v1.1 Adapters for Shadow Adoption.

Implement adapters that accept raw objects and strip performance metrics
for Layer 1/2, while allowing metrics only in Layer 3.
"""

import re
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone

from .hybrid_bc_vms import JobIndexVM, JobContextVM, JobAnalysisVM, PlateauCheck

logger = logging.getLogger(__name__)

# Performance metric key patterns to strip
PERFORMANCE_KEY_PATTERNS = [
    r"sharpe",
    r"cagr",
    r"mdd",
    r"drawdown",
    r"roi",
    r"rank",
    r"score",
    r"net_profit",
    r"profit",
    r"pnl",
    r"max_drawdown",
    r"win_rate",
    r"expectancy",
    r"calmar",
    r"sortino",
    r"omega",
]

# Compile regex patterns for case-insensitive matching
PERFORMANCE_REGEX = re.compile(
    "|".join(f"({pattern})" for pattern in PERFORMANCE_KEY_PATTERNS),
    re.IGNORECASE
)


def _strip_performance_metrics(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Recursively remove performance metric keys from a dictionary.
    
    Args:
        data: Dictionary potentially containing performance metrics
        
    Returns:
        Dictionary with performance metric keys removed
    """
    if not isinstance(data, dict):
        return data
    
    result = {}
    for key, value in data.items():
        # Check if key matches performance metric pattern
        if PERFORMANCE_REGEX.search(key):
            logger.debug(f"Stripping performance metric key: {key}")
            continue
        
        # Recursively process nested dictionaries
        if isinstance(value, dict):
            result[key] = _strip_performance_metrics(value)
        elif isinstance(value, list):
            # Process each item in list if it's a dict
            result[key] = [
                _strip_performance_metrics(item) if isinstance(item, dict) else item
                for item in value
            ]
        else:
            result[key] = value
    
    return result


def _extract_plateau_check(raw: Dict[str, Any]) -> PlateauCheck:
    """
    Extract plateau check tri-state from raw job data.
    
    Returns:
        "Pass" if plateau true
        "Fail" if plateau false  
        "N/A" if missing stats/plateau
    """
    artifacts = raw.get("artifacts", {})
    
    # Check for plateau report in artifacts
    plateau_report = artifacts.get("plateau_report")
    if isinstance(plateau_report, dict):
        plateau = plateau_report.get("plateau")
        if plateau is True:
            return "Pass"
        elif plateau is False:
            return "Fail"
    
    # Check for plateau in metrics
    metrics = raw.get("metrics", {})
    if isinstance(metrics, dict):
        plateau = metrics.get("plateau")
        if plateau is True:
            return "Pass"
        elif plateau is False:
            return "Fail"
    
    return "N/A"


def _extract_gatekeeper_counts(raw: Dict[str, Any]) -> Dict[str, int]:
    """
    Extract gatekeeper counts from raw job data.
    
    Returns:
        Dict with total_permutations and valid_candidates
    """
    artifacts = raw.get("artifacts", {})
    
    # Try to extract from various artifact structures
    total_permutations = 0
    valid_candidates = 0
    
    # Check for research artifacts
    research_artifacts = artifacts.get("research_artifacts", {})
    if isinstance(research_artifacts, dict):
        total_permutations = research_artifacts.get("total_permutations", 0)
        valid_candidates = research_artifacts.get("valid_candidates", 0)
    
    # Check for gatekeeper results
    gatekeeper_results = artifacts.get("gatekeeper_results", {})
    if isinstance(gatekeeper_results, dict):
        if total_permutations == 0:
            total_permutations = gatekeeper_results.get("total_permutations", 0)
        if valid_candidates == 0:
            valid_candidates = gatekeeper_results.get("valid_candidates", 0)
    
    # Check for winners_v2 artifact
    winners_v2 = artifacts.get("winners_v2", {})
    if isinstance(winners_v2, dict) and valid_candidates == 0:
        candidates = winners_v2.get("candidates", [])
        if isinstance(candidates, list):
            valid_candidates = len(candidates)
    
    return {
        "total_permutations": total_permutations,
        "valid_candidates": valid_candidates
    }


def _extract_logs_tail(raw: Dict[str, Any], max_lines: int = 50) -> List[str]:
    """
    Extract tail of logs from raw job data.
    
    Args:
        raw: Raw job data
        max_lines: Maximum number of log lines to return
        
    Returns:
        List of log lines (most recent first)
    """
    artifacts = raw.get("artifacts", {})
    
    # Check for stdout/stderr logs
    logs = []
    
    # Try to get from stdout_tail_url or similar
    links = artifacts.get("links", {})
    stdout_url = links.get("stdout_tail_url")
    if stdout_url:
        # In a real implementation, we would fetch from URL
        # For now, return placeholder
        logs.append(f"Logs available at: {stdout_url}")
    
    # Check for error logs in error_details
    error_details = raw.get("error_details")
    if isinstance(error_details, dict):
        error_message = error_details.get("message")
        if error_message:
            logs.append(f"Error: {error_message}")
    
    # Limit to max_lines
    return logs[-max_lines:] if len(logs) > max_lines else logs


def _format_relative_time(timestamp_str: str) -> str:
    """
    Format timestamp as relative time (e.g., "2 hours ago").
    
    Args:
        timestamp_str: ISO format timestamp string
        
    Returns:
        Relative time string
    """
    if not timestamp_str:
        return ""
    
    try:
        # Parse ISO timestamp
        if timestamp_str.endswith('Z'):
            timestamp_str = timestamp_str[:-1] + '+00:00'
        
        dt = datetime.fromisoformat(timestamp_str)
        now = datetime.now(timezone.utc) if dt.tzinfo else datetime.now()
        
        # Calculate difference
        diff = now - dt
        
        if diff.days > 365:
            years = diff.days // 365
            return f"{years} year{'s' if years > 1 else ''} ago"
        elif diff.days > 30:
            months = diff.days // 30
            return f"{months} month{'s' if months > 1 else ''} ago"
        elif diff.days > 0:
            return f"{diff.days} day{'s' if diff.days > 1 else ''} ago"
        elif diff.seconds > 3600:
            hours = diff.seconds // 3600
            return f"{hours} hour{'s' if hours > 1 else ''} ago"
        elif diff.seconds > 60:
            minutes = diff.seconds // 60
            return f"{minutes} minute{'s' if minutes > 1 else ''} ago"
        else:
            return "just now"
            
    except (ValueError, AttributeError):
        return timestamp_str


def adapt_to_index(raw: Dict[str, Any]) -> JobIndexVM:
    """
    Adapt raw job data to JobIndexVM for Layer 1.
    
    Strips all performance metrics and returns only operational fields.
    
    Args:
        raw: Raw job data from supervisor API
        
    Returns:
        JobIndexVM with operational fields only
    """
    # Strip performance metrics
    stripped = _strip_performance_metrics(raw)
    
    # Extract fields
    job_id = stripped.get("job_id", "")
    short_id = job_id[:8] + "..." if len(job_id) > 8 else job_id
    
    status = stripped.get("status", "UNKNOWN")
    
    # Use job_status_translator for human-readable status
    from .job_status_translator import translate_job_status
    error_details = stripped.get("error_details")
    status_text = translate_job_status(status, error_details)
    
    # Format relative time from created_at
    created_at = stripped.get("created_at", "")
    relative_time = _format_relative_time(created_at)
    
    # Format duration (operational only)
    duration_seconds = stripped.get("duration_seconds")
    if duration_seconds is not None:
        if duration_seconds < 60:
            duration_text = f"{duration_seconds:.1f}s"
        elif duration_seconds < 3600:
            duration_text = f"{duration_seconds/60:.1f}m"
        else:
            duration_text = f"{duration_seconds/3600:.1f}h"
    else:
        duration_text = "—"
    
    # Determine job type
    run_mode = stripped.get("run_mode", "").upper()
    job_type = "WFS" if run_mode == "WFS" else "Single"
    
    # Extract note excerpt
    note = stripped.get("note", "")
    note_excerpt = note[:50] + "..." if len(note) > 50 else note
    
    return JobIndexVM(
        job_id=job_id,
        short_id=short_id,
        status=status,
        status_text=status_text,
        relative_time=relative_time,
        duration_text=duration_text,
        job_type=job_type,
        note_excerpt=note_excerpt,
        strategy_name=stripped.get("strategy_name", stripped.get("strategy_id", "")),
        instrument=stripped.get("instrument", ""),
        timeframe=str(stripped.get("timeframe", "")),
        run_mode=stripped.get("run_mode", ""),
        season=stripped.get("season", ""),
        created_at=created_at,
        finished_at=stripped.get("finished_at", "")
    )


def adapt_to_context(raw: Dict[str, Any]) -> JobContextVM:
    """
    Adapt raw job data to JobContextVM for Layer 2.
    
    Strips all performance metrics and returns context for explanation.
    
    Args:
        raw: Raw job data from supervisor API
        
    Returns:
        JobContextVM with context fields only
    """
    # Strip performance metrics
    stripped = _strip_performance_metrics(raw)
    
    # Extract basic fields
    job_id = stripped.get("job_id", "")
    
    # Full note
    full_note = stripped.get("note", "")
    
    # Tags (extract from various fields)
    tags = []
    strategy = stripped.get("strategy_name", stripped.get("strategy_id", ""))
    if strategy:
        tags.append(f"strategy:{strategy}")
    
    instrument = stripped.get("instrument", "")
    if instrument:
        tags.append(f"instrument:{instrument}")
    
    run_mode = stripped.get("run_mode", "")
    if run_mode:
        tags.append(f"mode:{run_mode}")
    
    season = stripped.get("season", "")
    if season:
        tags.append(f"season:{season}")
    
    # Config snapshot (strip metrics)
    config = stripped.get("config", {})
    if isinstance(config, dict):
        config_snapshot = _strip_performance_metrics(config)
    else:
        config_snapshot = {}
    
    # Health information
    status = stripped.get("status", "")
    error_details = stripped.get("error_details")
    
    health_summary = ""
    if status in ["FAILED", "REJECTED", "ABORTED"]:
        health_summary = f"Job {status.lower()}"
        if error_details and isinstance(error_details, dict):
            error_msg = error_details.get("message", "")
            if error_msg:
                health_summary += f": {error_msg}"
    elif status == "SUCCEEDED":
        health_summary = "Job completed successfully"
    elif status == "RUNNING":
        health_summary = "Job is running"
    else:
        health_summary = f"Job status: {status}"
    
    # Gatekeeper counts
    gatekeeper_counts = _extract_gatekeeper_counts(raw)
    
    # Plateau check
    plateau_check = _extract_plateau_check(raw)
    
    # Logs tail
    logs_tail = _extract_logs_tail(raw)
    
    return JobContextVM(
        job_id=job_id,
        full_note=full_note,
        tags=tags,
        config_snapshot=config_snapshot,
        health={
            "summary": health_summary,
            "error_details_json": error_details,
            "logs_tail": logs_tail
        },
        gatekeeper={
            "total_permutations": gatekeeper_counts["total_permutations"],
            "valid_candidates": gatekeeper_counts["valid_candidates"],
            "plateau_check": plateau_check
        },
        status=status,
        error_details=error_details,
        artifacts=stripped.get("artifacts", {})
    )


def adapt_to_analysis(raw: Dict[str, Any]) -> JobAnalysisVM:
    """
    Adapt raw job data to JobAnalysisVM for Layer 3.
    
    Preserves all performance metrics for analysis.
    
    Args:
        raw: Raw job data from supervisor API
        
    Returns:
        JobAnalysisVM with full payload including metrics
    """
    job_id = raw.get("job_id", "")
    
    # Determine report type
    report_type = ""
    artifacts = raw.get("artifacts", {})
    
    if artifacts.get("strategy_report_v1_url"):
        report_type = "strategy"
    elif artifacts.get("portfolio_report_v1_url"):
        report_type = "portfolio"
    
    # Extract metrics if available
    metrics = raw.get("metrics", {})
    
    # Extract series if available
    series = {}
    if report_type == "strategy":
        # Try to get equity/drawdown series from artifacts
        pass
    
    return JobAnalysisVM(
        job_id=job_id,
        payload=raw,  # Keep full raw data for analysis
        report_type=report_type,
        metrics=metrics,
        series=series
    )