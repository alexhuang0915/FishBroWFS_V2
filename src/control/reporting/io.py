"""IO utilities for reading/writing report artifacts."""

import json
from pathlib import Path
from typing import Any, Optional
import logging

from core.paths import get_outputs_root

logger = logging.getLogger(__name__)


def read_job_artifact(job_id: str, filename: str) -> Optional[Any]:
    """Read a job artifact JSON file."""
    job_dir = get_outputs_root() / "jobs" / job_id
    artifact_path = job_dir / filename
    if not artifact_path.exists():
        return None
    try:
        with open(artifact_path, "r") as f:
            return json.load(f)
    except Exception as e:
        logger.warning(f"Failed to read artifact {filename} for job {job_id}: {e}")
        return None


def read_portfolio_admission_artifact(portfolio_id: str, filename: str) -> Optional[Any]:
    """Read a portfolio admission artifact JSON file."""
    admission_dir = Path("outputs/portfolios") / portfolio_id / "admission"
    artifact_path = admission_dir / filename
    if not artifact_path.exists():
        return None
    try:
        with open(artifact_path, "r") as f:
            return json.load(f)
    except Exception as e:
        logger.warning(f"Failed to read artifact {filename} for portfolio {portfolio_id}: {e}")
        return None


def write_job_report(job_id: str, filename: str, model: Any) -> None:
    """Write a report model to the job evidence directory."""
    job_dir = get_outputs_root() / "jobs" / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    
    report_path = job_dir / filename
    with open(report_path, "w") as f:
        if hasattr(model, "model_dump"):
            # Pydantic model
            json.dump(model.model_dump(mode="json", exclude_none=True), f, indent=2, sort_keys=True)
        else:
            # Plain dict
            json.dump(model, f, indent=2, sort_keys=True)
    
    logger.info(f"Written report to {report_path}")


def write_portfolio_report(portfolio_id: str, filename: str, model: Any) -> None:
    """Write a report model to the portfolio admission directory."""
    admission_dir = Path("outputs/portfolios") / portfolio_id / "admission"
    admission_dir.mkdir(parents=True, exist_ok=True)
    
    report_path = admission_dir / filename
    with open(report_path, "w") as f:
        if hasattr(model, "model_dump"):
            # Pydantic model
            json.dump(model.model_dump(mode="json", exclude_none=True), f, indent=2, sort_keys=True)
        else:
            # Plain dict
            json.dump(model, f, indent=2, sort_keys=True)
    
    logger.info(f"Written report to {report_path}")


def job_report_exists(job_id: str, filename: str = "strategy_report_v1.json") -> bool:
    """Check if a report file exists for a job."""
    job_dir = get_outputs_root() / "jobs" / job_id
    report_path = job_dir / filename
    return report_path.exists()


def portfolio_report_exists(portfolio_id: str, filename: str = "portfolio_report_v1.json") -> bool:
    """Check if a report file exists for a portfolio."""
    admission_dir = Path("outputs/portfolios") / portfolio_id / "admission"
    report_path = admission_dir / filename
    return report_path.exists()


def read_job_report(job_id: str, filename: str = "strategy_report_v1.json") -> Optional[Any]:
    """Read a report file for a job."""
    job_dir = get_outputs_root() / "jobs" / job_id
    report_path = job_dir / filename
    if not report_path.exists():
        return None
    try:
        with open(report_path, "r") as f:
            return json.load(f)
    except Exception as e:
        logger.warning(f"Failed to read report {filename} for job {job_id}: {e}")
        return None


def read_portfolio_report(portfolio_id: str, filename: str = "portfolio_report_v1.json") -> Optional[Any]:
    """Read a report file for a portfolio."""
    admission_dir = Path("outputs/portfolios") / portfolio_id / "admission"
    report_path = admission_dir / filename
    if not report_path.exists():
        return None
    try:
        with open(report_path, "r") as f:
            return json.load(f)
    except Exception as e:
        logger.warning(f"Failed to read report {filename} for portfolio {portfolio_id}: {e}")
        return None