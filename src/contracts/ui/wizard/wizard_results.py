"""
Wizard Result Definitions - Results and outcomes of wizard workflows.

This module defines the result models for wizard completion,
including job submission results and gate fix results.
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, ConfigDict

from .wizard_steps import WizardStep
from .wizard_state import WizardState, WizardType, WizardStatus
from contracts.portfolio.gate_summary_schemas import GateSummaryV1, GateStatus


class WizardResult(BaseModel):
    """Base result for wizard completion."""
    
    wizard_id: str = Field(..., description="Wizard session ID")
    wizard_type: WizardType = Field(..., description="Type of wizard")
    status: WizardStatus = Field(..., description="Final wizard status")
    completed_at: datetime = Field(default_factory=datetime.now, description="Completion timestamp")
    duration_seconds: float = Field(..., description="Total duration in seconds")
    final_step: WizardStep = Field(..., description="Final wizard step")
    
    # Statistics
    total_steps: int = Field(..., description="Total steps attempted")
    completed_steps: int = Field(..., description="Number of completed steps")
    validation_passed: int = Field(..., description="Number of validations passed")
    validation_failed: int = Field(..., description="Number of validations failed")
    
    # Metadata
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")
    
    model_config = ConfigDict(frozen=True)
    
    @classmethod
    def from_wizard_state(
        cls,
        wizard_state: WizardState,
        start_time: datetime,
        end_time: Optional[datetime] = None
    ) -> "WizardResult":
        """Create wizard result from completed wizard state."""
        if end_time is None:
            end_time = datetime.now()
        
        duration = (end_time - start_time).total_seconds()
        
        # Count validations
        validation_passed = sum(1 for v in wizard_state.validation_history if v.is_valid)
        validation_failed = len(wizard_state.validation_history) - validation_passed
        
        return cls(
            wizard_id=wizard_state.wizard_id,
            wizard_type=wizard_state.wizard_type,
            status=wizard_state.status,
            completed_at=end_time,
            duration_seconds=duration,
            final_step=wizard_state.current_step,
            total_steps=len(wizard_state.completed_steps) + 1,  # +1 for current step
            completed_steps=len(wizard_state.completed_steps),
            validation_passed=validation_passed,
            validation_failed=validation_failed,
            metadata=wizard_state.metadata,
        )


class WizardJobResult(BaseModel):
    """Result for Run Job Wizard completion."""
    
    # Job information
    job_id: str = Field(..., description="Submitted job ID")
    job_type: str = Field(..., description="Type of job submitted")
    submission_time: datetime = Field(..., description="Job submission timestamp")
    
    # Job parameters
    strategy_id: str = Field(..., description="Strategy ID")
    instrument: str = Field(..., description="Instrument")
    timeframe: str = Field(..., description="Timeframe")
    run_mode: str = Field(..., description="Run mode")
    season: Optional[str] = Field(default=None, description="Season")
    date_range: Optional[Dict[str, str]] = Field(default=None, description="Date range")
    
    # Gate summary results
    gate_summary: Optional[GateSummaryV1] = Field(default=None, description="Final gate summary")
    gate_status: Optional[GateStatus] = Field(default=None, description="Overall gate status")
    
    # Job status
    job_status: Optional[str] = Field(default=None, description="Final job status")
    completion_time: Optional[datetime] = Field(default=None, description="Job completion timestamp")
    
    # Metrics
    execution_duration_seconds: Optional[float] = Field(default=None, description="Job execution duration")
    
    model_config = ConfigDict(frozen=True)
    
    @classmethod
    def create(
        cls,
        job_id: str,
        job_type: str,
        submission_time: datetime,
        strategy_id: str,
        instrument: str,
        timeframe: str,
        run_mode: str,
        season: Optional[str] = None,
        date_range: Optional[Dict[str, str]] = None,
        gate_summary: Optional[GateSummaryV1] = None,
        job_status: Optional[str] = None,
        completion_time: Optional[datetime] = None,
        execution_duration: Optional[float] = None
    ) -> "WizardJobResult":
        """Create a job result with all fields."""
        gate_status = gate_summary.overall_status if gate_summary else None
        
        return cls(
            job_id=job_id,
            job_type=job_type,
            submission_time=submission_time,
            strategy_id=strategy_id,
            instrument=instrument,
            timeframe=timeframe,
            run_mode=run_mode,
            season=season,
            date_range=date_range,
            gate_summary=gate_summary,
            gate_status=gate_status,
            job_status=job_status,
            completion_time=completion_time,
            execution_duration_seconds=execution_duration,
        )


class WizardGateFixResult(BaseModel):
    """Result for Gate Fix Wizard completion."""
    
    # Job information
    job_id: str = Field(..., description="Job ID that was fixed")
    original_gate_summary: GateSummaryV1 = Field(..., description="Original gate summary before fixes")
    fixed_gate_summary: GateSummaryV1 = Field(..., description="Gate summary after fixes")
    
    # Fix information
    fixed_gate_ids: List[str] = Field(..., description="Gate IDs that were fixed")
    applied_fixes: List[Dict[str, Any]] = Field(..., description="Fixes that were applied")
    fix_timestamp: datetime = Field(default_factory=datetime.now, description="Fix application timestamp")
    
    # Results
    improvement_summary: Dict[str, Any] = Field(..., description="Summary of improvements")
    gates_improved: int = Field(..., description="Number of gates that improved")
    gates_resolved: int = Field(..., description="Number of gates fully resolved")
    gates_unchanged: int = Field(..., description="Number of gates unchanged")
    
    # Verification
    verification_passed: bool = Field(..., description="Whether verification passed")
    verification_details: Optional[Dict[str, Any]] = Field(default=None, description="Verification details")
    
    model_config = ConfigDict(frozen=True)
    
    @classmethod
    def create(
        cls,
        job_id: str,
        original_gate_summary: GateSummaryV1,
        fixed_gate_summary: GateSummaryV1,
        fixed_gate_ids: List[str],
        applied_fixes: List[Dict[str, Any]],
        verification_passed: bool,
        verification_details: Optional[Dict[str, Any]] = None
    ) -> "WizardGateFixResult":
        """Create a gate fix result with calculated metrics."""
        # Calculate improvement summary
        original_counts = original_gate_summary.counts
        fixed_counts = fixed_gate_summary.counts
        
        improvement_summary = {
            "original_counts": original_counts,
            "fixed_counts": fixed_counts,
            "improvement": {
                "pass_change": fixed_counts.get("pass", 0) - original_counts.get("pass", 0),
                "warn_change": fixed_counts.get("warn", 0) - original_counts.get("warn", 0),
                "reject_change": fixed_counts.get("reject", 0) - original_counts.get("reject", 0),
                "unknown_change": fixed_counts.get("unknown", 0) - original_counts.get("unknown", 0),
            }
        }
        
        # Calculate gate improvements
        original_gates = {g.gate_id: g for g in original_gate_summary.gates}
        fixed_gates = {g.gate_id: g for g in fixed_gate_summary.gates}
        
        gates_improved = 0
        gates_resolved = 0
        gates_unchanged = 0
        
        for gate_id in fixed_gate_ids:
            if gate_id in original_gates and gate_id in fixed_gates:
                original_status = original_gates[gate_id].status
                fixed_status = fixed_gates[gate_id].status
                
                if fixed_status.value > original_status.value:  # Using enum ordering: PASS > WARN > REJECT > UNKNOWN
                    gates_improved += 1
                    if fixed_status == GateStatus.PASS:
                        gates_resolved += 1
                elif fixed_status == original_status:
                    gates_unchanged += 1
        
        return cls(
            job_id=job_id,
            original_gate_summary=original_gate_summary,
            fixed_gate_summary=fixed_gate_summary,
            fixed_gate_ids=fixed_gate_ids,
            applied_fixes=applied_fixes,
            improvement_summary=improvement_summary,
            gates_improved=gates_improved,
            gates_resolved=gates_resolved,
            gates_unchanged=gates_unchanged,
            verification_passed=verification_passed,
            verification_details=verification_details,
        )


class WizardCompletionResult(BaseModel):
    """Complete result of wizard completion including both wizard and specific results."""
    
    wizard_result: WizardResult = Field(..., description="Wizard completion result")
    job_result: Optional[WizardJobResult] = Field(default=None, description="Job result (for Run Job Wizard)")
    gate_fix_result: Optional[WizardGateFixResult] = Field(default=None, description="Gate fix result (for Gate Fix Wizard)")
    
    # Success indicators
    success: bool = Field(..., description="Overall success indicator")
    error_message: Optional[str] = Field(default=None, description="Error message if failed")
    
    # Recommendations
    next_actions: List[Dict[str, Any]] = Field(default_factory=list, description="Recommended next actions")
    
    model_config = ConfigDict(frozen=True)
    
    @classmethod
    def create_success(
        cls,
        wizard_result: WizardResult,
        job_result: Optional[WizardJobResult] = None,
        gate_fix_result: Optional[WizardGateFixResult] = None,
        next_actions: Optional[List[Dict[str, Any]]] = None
    ) -> "WizardCompletionResult":
        """Create a successful completion result."""
        return cls(
            wizard_result=wizard_result,
            job_result=job_result,
            gate_fix_result=gate_fix_result,
            success=True,
            next_actions=next_actions or [],
        )
    
    @classmethod
    def create_error(
        cls,
        wizard_result: WizardResult,
        error_message: str,
        next_actions: Optional[List[Dict[str, Any]]] = None
    ) -> "WizardCompletionResult":
        """Create an error completion result."""
        return cls(
            wizard_result=wizard_result,
            success=False,
            error_message=error_message,
            next_actions=next_actions or [],
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        result = {
            "wizard_id": self.wizard_result.wizard_id,
            "wizard_type": self.wizard_result.wizard_type.value,
            "status": self.wizard_result.status.value,
            "success": self.success,
            "duration_seconds": self.wizard_result.duration_seconds,
            "total_steps": self.wizard_result.total_steps,
            "completed_steps": self.wizard_result.completed_steps,
        }
        
        if self.job_result:
            result["job_result"] = {
                "job_id": self.job_result.job_id,
                "strategy_id": self.job_result.strategy_id,
                "instrument": self.job_result.instrument,
                "timeframe": self.job_result.timeframe,
                "run_mode": self.job_result.run_mode,
                "gate_status": self.job_result.gate_status.value if self.job_result.gate_status else None,
            }
        
        if self.gate_fix_result:
            result["gate_fix_result"] = {
                "job_id": self.gate_fix_result.job_id,
                "gates_improved": self.gate_fix_result.gates_improved,
                "gates_resolved": self.gate_fix_result.gates_resolved,
                "verification_passed": self.gate_fix_result.verification_passed,
            }
        
        if self.error_message:
            result["error_message"] = self.error_message
        
        if self.next_actions:
            result["next_actions"] = self.next_actions
        
        return result