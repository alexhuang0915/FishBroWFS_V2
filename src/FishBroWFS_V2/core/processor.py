"""StateProcessor - single executor for Attack #9 – Headless Intent-State Contract.

StateProcessor is the single consumer that processes intents sequentially.
All side effects must happen only inside StateProcessor. It reads intents from
ActionQueue, processes them, and produces new SystemState snapshots.
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple, Callable, Type
from concurrent.futures import ThreadPoolExecutor

from FishBroWFS_V2.core.intents import (
    Intent, UserIntent, IntentType, IntentStatus,
    CreateJobIntent, CalculateUnitsIntent, CheckSeasonIntent,
    GetJobStatusIntent, ListJobsIntent, GetJobLogsIntent,
    SubmitBatchIntent, ValidatePayloadIntent, BuildParquetIntent,
    FreezeSeasonIntent, ExportSeasonIntent, CompareSeasonsIntent,
    DataSpecIntent
)
from FishBroWFS_V2.core.state import (
    SystemState, JobProgress, SeasonInfo, DatasetInfo, SystemMetrics,
    IntentQueueStatus, JobStatus, SeasonStatus, DatasetStatus,
    create_initial_state, create_state_snapshot
)
from FishBroWFS_V2.control.action_queue import ActionQueue


logger = logging.getLogger(__name__)


class ProcessingError(Exception):
    """Error during intent processing."""
    pass


class IntentHandler:
    """Base class for intent handlers."""
    
    def __init__(self, processor: "StateProcessor"):
        self.processor = processor
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
    
    async def handle(self, intent: UserIntent, current_state: SystemState) -> Tuple[SystemState, Dict[str, Any]]:
        """Handle an intent and return new state and result."""
        raise NotImplementedError


class CreateJobHandler(IntentHandler):
    """Handler for CreateJobIntent."""
    
    async def handle(self, intent: CreateJobIntent, current_state: SystemState) -> Tuple[SystemState, Dict[str, Any]]:
        """Create a job from wizard payload."""
        self.logger.info(f"Processing CreateJobIntent: {intent.intent_id}")
        
        # Validate job creation
        errors = current_state.validate_job_creation(intent.season, intent.data1.dataset_id)
        if errors:
            raise ProcessingError(f"Job creation validation failed: {', '.join(errors)}")
        
        # TODO: Integrate with actual job creation logic from job_api.py
        # For now, simulate job creation
        import uuid
        job_id = str(uuid.uuid4())
        
        # Calculate units (simplified)
        symbols_count = len(intent.data1.symbols)
        timeframes_count = len(intent.data1.timeframes)
        units = symbols_count * timeframes_count
        
        # Create job progress
        now = datetime.now()
        job_progress = JobProgress(
            job_id=job_id,
            status=JobStatus.QUEUED,
            units_done=0,
            units_total=units,
            progress=0.0,
            created_at=now,
            updated_at=now,
            season=intent.season,
            dataset_id=intent.data1.dataset_id
        )
        
        # Update state
        new_state = create_state_snapshot(
            current_state,
            jobs={**current_state.jobs, job_id: job_progress},
            active_job_ids={*current_state.active_job_ids, job_id},
            metrics=SystemMetrics(
                total_jobs=current_state.metrics.total_jobs + 1,
                queued_jobs=current_state.metrics.queued_jobs + 1
            )
        )
        
        # Result for UI
        result = {
            "job_id": job_id,
            "units": units,
            "season": intent.season,
            "status": "queued"
        }
        
        return new_state, result


class CalculateUnitsHandler(IntentHandler):
    """Handler for CalculateUnitsIntent."""
    
    async def handle(self, intent: CalculateUnitsIntent, current_state: SystemState) -> Tuple[SystemState, Dict[str, Any]]:
        """Calculate units for wizard payload."""
        self.logger.info(f"Processing CalculateUnitsIntent: {intent.intent_id}")
        
        # Calculate units (same logic as job_api.calculate_units)
        symbols_count = len(intent.data1.symbols)
        timeframes_count = len(intent.data1.timeframes)
        strategies_count = 1  # Single strategy
        filters_count = 1 if intent.data2 is None else len(intent.data2.filters) if hasattr(intent.data2, 'filters') else 1
        
        units = symbols_count * timeframes_count * strategies_count * filters_count
        
        # State doesn't change for calculation
        result = {
            "units": units,
            "breakdown": {
                "symbols": symbols_count,
                "timeframes": timeframes_count,
                "strategies": strategies_count,
                "filters": filters_count
            }
        }
        
        return current_state, result


class CheckSeasonHandler(IntentHandler):
    """Handler for CheckSeasonIntent."""
    
    async def handle(self, intent: CheckSeasonIntent, current_state: SystemState) -> Tuple[SystemState, Dict[str, Any]]:
        """Check if a season is frozen."""
        self.logger.info(f"Processing CheckSeasonIntent: {intent.intent_id}")
        
        is_frozen = current_state.is_season_frozen(intent.season)
        
        result = {
            "season": intent.season,
            "is_frozen": is_frozen,
            "action": intent.action,
            "can_proceed": not is_frozen
        }
        
        if is_frozen:
            result["error"] = f"Season {intent.season} is frozen"
        
        return current_state, result


class GetJobStatusHandler(IntentHandler):
    """Handler for GetJobStatusIntent."""
    
    async def handle(self, intent: GetJobStatusIntent, current_state: SystemState) -> Tuple[SystemState, Dict[str, Any]]:
        """Get job status with units progress."""
        self.logger.info(f"Processing GetJobStatusIntent: {intent.intent_id}")
        
        job = current_state.get_job(intent.job_id)
        if not job:
            raise ProcessingError(f"Job not found: {intent.job_id}")
        
        result = {
            "job_id": job.job_id,
            "status": job.status.value,
            "units_done": job.units_done,
            "units_total": job.units_total,
            "progress": job.progress,
            "created_at": job.created_at.isoformat(),
            "updated_at": job.updated_at.isoformat(),
            "season": job.season,
            "dataset_id": job.dataset_id
        }
        
        return current_state, result


class ListJobsHandler(IntentHandler):
    """Handler for ListJobsIntent."""
    
    async def handle(self, intent: ListJobsIntent, current_state: SystemState) -> Tuple[SystemState, Dict[str, Any]]:
        """List jobs with progress."""
        self.logger.info(f"Processing ListJobsIntent: {intent.intent_id}")
        
        # Get recent jobs
        jobs = list(current_state.jobs.values())
        jobs.sort(key=lambda j: j.updated_at, reverse=True)
        jobs = jobs[:intent.limit]
        
        result = {
            "jobs": [
                {
                    "job_id": job.job_id,
                    "status": job.status.value,
                    "units_done": job.units_done,
                    "units_total": job.units_total,
                    "progress": job.progress,
                    "created_at": job.created_at.isoformat(),
                    "updated_at": job.updated_at.isoformat(),
                    "season": job.season,
                    "dataset_id": job.dataset_id
                }
                for job in jobs
            ],
            "total": len(current_state.jobs),
            "limit": intent.limit
        }
        
        return current_state, result


class ValidatePayloadHandler(IntentHandler):
    """Handler for ValidatePayloadIntent."""
    
    async def handle(self, intent: ValidatePayloadIntent, current_state: SystemState) -> Tuple[SystemState, Dict[str, Any]]:
        """Validate wizard payload."""
        self.logger.info(f"Processing ValidatePayloadIntent: {intent.intent_id}")
        
        # TODO: Integrate with actual validation logic from job_api.validate_wizard_payload
        # For now, do basic validation
        errors = []
        
        payload = intent.payload
        
        # Check required fields
        required_fields = ["season", "data1", "strategy_id", "params"]
        for field in required_fields:
            if field not in payload:
                errors.append(f"Missing required field: {field}")
        
        # Check data1
        if "data1" in payload:
            data1 = payload["data1"]
            if not isinstance(data1, dict):
                errors.append("data1 must be a dictionary")
            else:
                if "dataset_id" not in data1:
                    errors.append("data1 missing dataset_id")
                if "symbols" not in data1:
                    errors.append("data1 missing symbols")
                if "timeframes" not in data1:
                    errors.append("data1 missing timeframes")
        
        result = {
            "is_valid": len(errors) == 0,
            "errors": errors,
            "warnings": []  # Could add warnings here
        }
        
        return current_state, result


class BuildParquetHandler(IntentHandler):
    """Handler for BuildParquetIntent."""
    
    async def handle(self, intent: BuildParquetIntent, current_state: SystemState) -> Tuple[SystemState, Dict[str, Any]]:
        """Build Parquet files for a dataset."""
        self.logger.info(f"Processing BuildParquetIntent: {intent.intent_id}")
        
        # Check if dataset exists
        dataset = current_state.get_dataset(intent.dataset_id)
        if not dataset:
            raise ProcessingError(f"Dataset not found: {intent.dataset_id}")
        
        # Check if already building
        if intent.dataset_id in current_state.active_builds:
            raise ProcessingError(f"Dataset already being built: {intent.dataset_id}")
        
        # Update state to show building in progress
        new_state = create_state_snapshot(
            current_state,
            active_builds={*current_state.active_builds, intent.dataset_id}
        )
        
        # TODO: Actually build Parquet files
        # Simulate building
        await asyncio.sleep(0.1)  # Simulate work
        
        # Update dataset status
        updated_dataset = DatasetInfo(
            **dataset.model_dump(),
            status=DatasetStatus.AVAILABLE,
            has_parquet=True,
            last_built_at=datetime.now()
        )
        
        new_state = create_state_snapshot(
            new_state,
            datasets={**new_state.datasets, intent.dataset_id: updated_dataset},
            active_builds=new_state.active_builds - {intent.dataset_id}
        )
        
        result = {
            "dataset_id": intent.dataset_id,
            "status": "built",
            "has_parquet": True,
            "built_at": datetime.now().isoformat()
        }
        
        return new_state, result


class StateProcessor:
    """Single executor that processes intents sequentially.
    
    All side effects must happen only inside StateProcessor. It reads intents
    from ActionQueue, processes them, and produces new SystemState snapshots.
    """
    
    def __init__(self, action_queue: ActionQueue, initial_state: Optional[SystemState] = None):
        self.action_queue = action_queue
        self.current_state = initial_state or create_initial_state()
        self.is_running = False
        self.processing_task: Optional[asyncio.Task] = None
        self.handlers: Dict[IntentType, IntentHandler] = {}
        self.executor = ThreadPoolExecutor(max_workers=1)  # Single worker for sequential processing
        self.logger = logging.getLogger(__name__)
        
        # Register handlers
        self._register_handlers()
    
    def _register_handlers(self) -> None:
        """Register intent handlers."""
        self.handlers[IntentType.CREATE_JOB] = CreateJobHandler(self)
        self.handlers[IntentType.CALCULATE_UNITS] = CalculateUnitsHandler(self)
        self.handlers[IntentType.CHECK_SEASON] = CheckSeasonHandler(self)
        self.handlers[IntentType.GET_JOB_STATUS] = GetJobStatusHandler(self)
        self.handlers[IntentType.LIST_JOBS] = ListJobsHandler(self)
        self.handlers[IntentType.VALIDATE_PAYLOAD] = ValidatePayloadHandler(self)
        self.handlers[IntentType.BUILD_PARQUET] = BuildParquetHandler(self)
        # TODO: Add handlers for other intent types
    
    async def start(self) -> None:
        """Start the processor."""
        if self.is_running:
            return
        
        self.is_running = True
        self.processing_task = asyncio.create_task(self._process_loop())
        self.logger.info("StateProcessor started")
    
    async def stop(self) -> None:
        """Stop the processor safely without deadlock.

        Contract:
        - Never block the asyncio loop.
        - Idempotent.
        - Always returns promptly.
        """
        # (A) flip running flag
        try:
            self.is_running = False
        except Exception:
            pass

        # (B) cancel and await worker task
        task = self.processing_task
        if task is not None:
            try:
                if not task.done():
                    task.cancel()
                # IMPORTANT: wait_for only works if loop is not frozen.
                # This must return quickly after we remove blocking calls.
                await asyncio.wait_for(task, timeout=1.0)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                pass
            except Exception:
                pass
            finally:
                try:
                    self.processing_task = None
                except Exception:
                    pass

        # (C) shutdown executor without blocking event loop
        ex = self.executor
        if ex is not None:
            try:
                ex.shutdown(wait=False, cancel_futures=True)  # py3.9+
            except TypeError:
                try:
                    ex.shutdown(wait=False)
                except Exception:
                    pass
            except Exception:
                pass
            finally:
                # If the class stores it, clear it to be idempotent
                try:
                    # Note: we don't set self.executor = None because
                    # it's used in _process_intent. But we could create
                    # a new executor on next start() if needed.
                    pass
                except Exception:
                    pass
        
        self.logger.info("StateProcessor stopped")
    
    async def _process_loop(self) -> None:
        """Main processing loop."""
        while self.is_running:
            try:
                # Get next intent from queue (non-blocking)
                # Note: get_next() is synchronous but we call it without await
                # because it returns Optional[UserIntent], not a coroutine
                intent = self.action_queue.get_next(block=False)
                if intent is None:
                    # No intents in queue, sleep a bit
                    await asyncio.sleep(0.1)
                    continue
                
                # Process the intent
                await self._process_intent(intent)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Error in processing loop: {e}", exc_info=True)
                await asyncio.sleep(1)  # Avoid tight error loop
    
    async def _process_intent(self, intent: UserIntent) -> None:
        """Process a single intent."""
        start_time = time.time()
        
        try:
            # Update intent status to processing
            intent.status = IntentStatus.PROCESSING
            intent.processed_at = datetime.now()
            
            # Get handler for this intent type
            handler = self.handlers.get(intent.intent_type)
            if not handler:
                raise ProcessingError(f"No handler for intent type: {intent.intent_type}")
            
            # Process intent with timeout to prevent indefinite hanging
            # Use asyncio.wait_for on the handler execution
            loop = asyncio.get_running_loop()
            
            # Define the handler execution function with timeout
            async def execute_handler_with_timeout():
                # Run handler in thread pool with its own event loop
                return await loop.run_in_executor(
                    self.executor,
                    lambda: asyncio.run(handler.handle(intent, self.current_state))
                )
            
            # Execute with timeout (30 seconds should be plenty for any handler)
            try:
                new_state, result = await asyncio.wait_for(
                    execute_handler_with_timeout(),
                    timeout=30.0
                )
            except asyncio.TimeoutError:
                raise ProcessingError(f"Handler timed out after 30 seconds for intent {intent.intent_id}")
            
            # Update state
            self.current_state = new_state
            
            # Update intent status
            intent.status = IntentStatus.COMPLETED
            intent.result = result
            
            # Notify queue that intent is completed
            self.action_queue.mark_completed(intent.intent_id, result)
            
            processing_time_ms = (time.time() - start_time) * 1000
            self.logger.info(f"Processed intent {intent.intent_id} ({intent.intent_type}) in {processing_time_ms:.1f}ms")
            
        except Exception as e:
            # Handle processing error
            intent.status = IntentStatus.FAILED
            intent.error_message = str(e)
            self.logger.error(f"Failed to process intent {intent.intent_id}: {e}", exc_info=True)
            
            # Notify queue that intent failed
            self.action_queue.mark_failed(intent.intent_id, str(e))
            
            # Update metrics
            intent_queue_dict = self.current_state.intent_queue.model_dump()
            intent_queue_dict['failed_count'] = self.current_state.intent_queue.failed_count + 1
            self.current_state = create_state_snapshot(
                self.current_state,
                intent_queue=IntentQueueStatus(**intent_queue_dict)
            )
    
    def get_state(self) -> SystemState:
        """Get current system state snapshot."""
        return self.current_state
    
    def submit_intent(self, intent: UserIntent) -> str:
        """Submit an intent to the action queue.
        
        Returns the intent ID for tracking.
        """
        return self.action_queue.submit(intent)
    
    def get_intent_status(self, intent_id: str) -> Optional[UserIntent]:
        """Get intent status by ID."""
        return self.action_queue.get_intent(intent_id)
    
    async def wait_for_intent(self, intent_id: str, timeout: Optional[float] = 30.0) -> Optional[UserIntent]:
        """Wait for an intent to complete.
        
        Hard guarantee: never hang forever.
        If timeout is None, uses default 30.0 seconds.
        Returns None on timeout or any exception (UI contract wants "no hang").
        """
        # Enforce a default hard cap in production
        if timeout is None:
            timeout = 30.0
        
        try:
            return await self.action_queue.wait_for_intent_async(intent_id, timeout=timeout)
        except Exception:
            # No propagation; UI contract wants "no hang"
            # Log at debug level to avoid noise in tests
            self.logger.debug(f"wait_for_intent timed out or errored for intent {intent_id}", exc_info=True)
            return None
    
    def get_queue_status(self) -> IntentQueueStatus:
        """Get queue status."""
        return self.current_state.intent_queue


# Singleton instance for application use
_processor_instance: Optional[StateProcessor] = None


def get_processor() -> StateProcessor:
    """Get the singleton StateProcessor instance."""
    global _processor_instance
    if _processor_instance is None:
        from FishBroWFS_V2.control.action_queue import get_action_queue
        action_queue = get_action_queue()
        _processor_instance = StateProcessor(action_queue)
    return _processor_instance


async def start_processor() -> None:
    """Start the singleton processor."""
    processor = get_processor()
    await processor.start()


async def stop_processor() -> None:
    """Stop the singleton processor.
    
    Hard guarantee: never hang forever.
    Uses asyncio.wait_for with timeout to ensure we don't block.
    """
    global _processor_instance
    if _processor_instance:
        try:
            # Use timeout to prevent hanging
            await asyncio.wait_for(_processor_instance.stop(), timeout=2.0)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            # If timeout, log and continue - we must not hang
            import logging
            logger = logging.getLogger(__name__)
            logger.warning("stop_processor timed out after 2 seconds, forcing cleanup")
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error stopping processor: {e}")
        finally:
            _processor_instance = None


def reset_processor() -> None:
    """Reset the singleton processor (for testing).
    
    This stops the processor if it's running and clears the singleton.
    """
    global _processor_instance
    if _processor_instance:
        # Try to stop synchronously (not ideal but works for tests)
        import asyncio
        import warnings
        try:
            # Try to get the running loop first (Python 3.7+)
            try:
                loop = asyncio.get_running_loop()
                # If we're in a running loop, we can't call stop_processor synchronously
                # Just clear the reference and let garbage collection handle it
                _processor_instance = None
                return
            except RuntimeError:
                # No running loop, we need to handle cleanup differently
                pass
            
            # Check if there's an existing event loop
            # Suppress deprecation warning for asyncio.get_event_loop() in Python 3.10+
            with warnings.catch_warnings():
                warnings.filterwarnings("ignore", category=DeprecationWarning, message="There is no current event loop")
                try:
                    loop = asyncio.get_event_loop()
                except RuntimeError:
                    # No event loop exists, create a new one
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
            
            if loop.is_running():
                # If loop is running, we can't call stop_processor synchronously
                # Just clear the reference and let garbage collection handle it
                _processor_instance = None
            else:
                # Run stop_processor in the event loop
                loop.run_until_complete(stop_processor())
        except (RuntimeError, Exception):
            # No event loop or other error, just clear the reference
            _processor_instance = None
    else:
        _processor_instance = None