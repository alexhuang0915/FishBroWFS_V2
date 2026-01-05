"""
BaseGovernedHandler - Template method pattern for governed job execution.
"""
from __future__ import annotations
import time
import sys
import io
from typing import Dict, Any, Optional
from pathlib import Path
import traceback

from ..db import SupervisorDB
from ..models import JobSpec
from ..job_handler import BaseJobHandler, JobContext
from ..evidence import (
    job_evidence_dir,
    write_manifest,
    write_policy_check,
    write_inputs_fingerprint,
    write_outputs_fingerprint,
    write_runtime_metrics,
    capture_stdout_tail,
    get_code_fingerprint,
    get_dependencies_fingerprint,
    discover_outputs,
    stable_params_hash,
    now_iso,
)
from ..admission import AdmissionController
from ..policies.post_flight import QualityGate
from src.contracts.supervisor.evidence_schemas import (
    PolicyCheckBundle,
    RuntimeMetrics,
)


class BaseGovernedHandler(BaseJobHandler):
    """
    Template method pattern for governed job execution.
    
    Execution order (LOCKED):
    1) start timer, capture stdout
    2) compute inputs_fingerprint (params_hash, deps, code_fingerprint)
    3) core_logic(...)
    4) post_flight_checks = quality_gate(...)
    5) discover outputs
    6) write ALL evidence files
    7) finalize job state SUCCEEDED or FAILED
    """
    
    def __init__(self, evidence_base_dir: Path):
        self.evidence_base_dir = evidence_base_dir
    
    def validate_params(self, params: Dict[str, Any]) -> None:
        """Validate job parameters before execution."""
        # Default implementation does nothing
        pass
    
    def execute(self, params: Dict[str, Any], context: JobContext) -> Dict[str, Any]:
        """
        Governed execution template method.
        
        This method MUST NOT be overridden by subclasses.
        Subclasses should implement core_logic() instead.
        """
        job_id = context.job_id
        evidence_dir = job_evidence_dir(self.evidence_base_dir, job_id)
        evidence_dir.mkdir(parents=True, exist_ok=True)
        
        # 1) Start timer, capture stdout
        start_time = time.time()
        start_time_iso = now_iso()
        
        # Capture stdout
        old_stdout = sys.stdout
        captured_stdout = io.StringIO()
        sys.stdout = captured_stdout
        
        try:
            # 2) Compute inputs fingerprint
            params_hash = stable_params_hash(params)
            code_fingerprint = get_code_fingerprint()
            dependencies = get_dependencies_fingerprint()
            
            # 3) core_logic(...)
            result = self.core_logic(params, context)
            
            # 4) Post-flight checks
            quality_gate = QualityGate()
            post_flight_checks = quality_gate.check(job_id, self.__class__.__name__, result, evidence_dir)
            
            # 5) Discover outputs
            outputs = discover_outputs(evidence_dir)
            
            # 6) Write ALL evidence files
            end_time = time.time()
            end_time_iso = now_iso()
            execution_time = end_time - start_time
            
            # Runtime metrics (placeholder for memory usage)
            metrics = RuntimeMetrics(
                job_id=job_id,
                handler_name=self.__class__.__name__,
                execution_time_sec=execution_time,
                peak_memory_mb=0.0,  # TODO: Implement memory monitoring
                custom_metrics={}
            )
            
            # Policy check bundle (pre-flight from admission, post-flight from quality gate)
            # Note: pre-flight checks are written during admission, we need to read them
            policy_bundle = PolicyCheckBundle(
                pre_flight_checks=[],  # Will be populated from existing file
                post_flight_checks=post_flight_checks,
                downstream_admissible=all(check.passed for check in post_flight_checks)
            )
            
            # Read pre-flight checks if they exist
            pre_flight_file = evidence_dir / "policy_check.json"
            if pre_flight_file.exists():
                import json
                with open(pre_flight_file, 'r') as f:
                    existing = json.load(f)
                    # Extract pre-flight checks
                    for check_data in existing.get("pre_flight_checks", []):
                        from src.contracts.supervisor.evidence_schemas import PolicyCheck
                        policy_bundle.pre_flight_checks.append(
                            PolicyCheck(**check_data)
                        )
            
            # Write evidence files
            write_manifest(
                evidence_dir,
                job_id,
                self.get_job_type(),
                "SUCCEEDED",
                start_time_iso,
                end_time_iso
            )
            write_policy_check(evidence_dir, policy_bundle)
            write_inputs_fingerprint(
                evidence_dir,
                params_hash,
                dependencies,
                code_fingerprint
            )
            write_outputs_fingerprint(evidence_dir, outputs)
            write_runtime_metrics(evidence_dir, metrics)
            
            # Capture stdout tail
            stdout_content = captured_stdout.getvalue()
            capture_stdout_tail(evidence_dir, stdout_content)
            
            # 7) Finalize job state (SUCCEEDED)
            return result
            
        except Exception as e:
            # Exception handling - job FAILED
            end_time = time.time()
            end_time_iso = now_iso()
            execution_time = end_time - start_time
            
            # Get error details
            error_msg = str(e)
            traceback_str = traceback.format_exc()
            
            # Runtime metrics for failed job
            metrics = RuntimeMetrics(
                job_id=job_id,
                handler_name=self.__class__.__name__,
                execution_time_sec=execution_time,
                peak_memory_mb=0.0,
                custom_metrics={"error": error_msg, "traceback": traceback_str}
            )
            
            # Write evidence files even for failures
            write_manifest(
                evidence_dir,
                job_id,
                self.get_job_type(),
                "FAILED",
                start_time_iso,
                end_time_iso,
                {"error": error_msg}
            )
            
            # Create empty policy bundle for failed job
            policy_bundle = PolicyCheckBundle(
                pre_flight_checks=[],
                post_flight_checks=[],
                downstream_admissible=False
            )
            
            # Read pre-flight checks if they exist
            pre_flight_file = evidence_dir / "policy_check.json"
            if pre_flight_file.exists():
                import json
                with open(pre_flight_file, 'r') as f:
                    existing = json.load(f)
                    for check_data in existing.get("pre_flight_checks", []):
                        from src.contracts.supervisor.evidence_schemas import PolicyCheck
                        policy_bundle.pre_flight_checks.append(
                            PolicyCheck(**check_data)
                        )
            
            write_policy_check(evidence_dir, policy_bundle)
            
            # Compute and write inputs fingerprint
            params_hash = stable_params_hash(params)
            code_fingerprint = get_code_fingerprint()
            dependencies = get_dependencies_fingerprint()
            write_inputs_fingerprint(
                evidence_dir,
                params_hash,
                dependencies,
                code_fingerprint
            )
            
            # No outputs for failed job
            write_outputs_fingerprint(evidence_dir, {})
            write_runtime_metrics(evidence_dir, metrics)
            
            # Capture stdout tail
            stdout_content = captured_stdout.getvalue()
            capture_stdout_tail(evidence_dir, stdout_content)
            
            # Re-raise the exception
            raise
            
        finally:
            # Restore stdout
            sys.stdout = old_stdout
    
    def core_logic(self, params: Dict[str, Any], context: JobContext) -> Dict[str, Any]:
        """
        Core business logic to be implemented by subclasses.
        
        This method should:
        - Perform the actual job work
        - Write any output artifacts to context.artifacts_dir
        - Return a result dict
        """
        raise NotImplementedError("Subclasses must implement core_logic")
    
    def get_job_type(self) -> str:
        """Return the job type string for this handler."""
        raise NotImplementedError("Subclasses must implement get_job_type")


def governed_handler(evidence_base_dir: Path):
    """
    Decorator to mark a handler as governed.
    
    Usage:
        @governed_handler(Path("outputs/jobs"))
        class MyHandler(BaseGovernedHandler):
            ...
    """
    def decorator(cls):
        cls.__fishbro_governed__ = True
        cls._evidence_base_dir = evidence_base_dir
        return cls
    return decorator