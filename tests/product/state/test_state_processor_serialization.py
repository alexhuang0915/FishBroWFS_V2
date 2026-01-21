"""Test StateProcessor serial execution for Attack #9.

Tests that StateProcessor executes intents sequentially (single consumer)
and produces consistent SystemState snapshots.
"""

import pytest
import asyncio
import time
from datetime import date, datetime
from concurrent.futures import ThreadPoolExecutor

from core.intents import (
    CreateJobIntent, CalculateUnitsIntent, DataSpecIntent,
    IntentStatus, IntentType
)
from control.action_queue import ActionQueue, reset_action_queue
from core.processor import StateProcessor, ProcessingError, get_processor
from core.state import SystemState, JobStatus, create_initial_state


@pytest.fixture
def action_queue():
    """Create a fresh ActionQueue for each test."""
    reset_action_queue()
    queue = ActionQueue(max_size=100)
    yield queue
    queue.clear()


@pytest.fixture
def processor(action_queue):
    """Create a StateProcessor with fresh queue."""
    return StateProcessor(action_queue)


@pytest.fixture
def sample_data_spec():
    """Create a sample DataSpecIntent for testing."""
    return DataSpecIntent(
        dataset_id="test_dataset",
        symbols=["MNQ", "MXF"],
        timeframes=["60m", "120m"],
        start_date=date(2020, 1, 1),
        end_date=date(2024, 12, 31)
    )


@pytest.mark.skip(reason="Async tests require pytest-asyncio")
async def test_processor_sequential_execution(processor, action_queue, sample_data_spec):
    """Test that processor executes intents sequentially."""
    # Start processor
    await processor.start()
    
    # Submit multiple intents
    intent_ids = []
    for i in range(5):
        intent = CalculateUnitsIntent(
            season=f"2024Q{i}",
            data1=sample_data_spec,
            data2=None,
            strategy_id="sma_cross_v1",
            params={"window_fast": i}
        )
        intent_id = processor.submit_intent(intent)
        intent_ids.append(intent_id)
    
    # Wait for all intents to complete
    completed_count = 0
    start_time = time.time()
    timeout = 5.0
    
    while completed_count < 5 and time.time() - start_time < timeout:
        completed_count = 0
        for intent_id in intent_ids:
            intent = action_queue.get_intent(intent_id)
            if intent and intent.status in [IntentStatus.COMPLETED, IntentStatus.FAILED]:
                completed_count += 1
        await asyncio.sleep(0.1)
    
    # All intents should be completed
    assert completed_count == 5
    
    # Check that they were processed in order (FIFO)
    # Since we can't easily track exact order without timestamps in test,
    # we at least verify all were processed
    metrics = action_queue.get_metrics()
    assert metrics["processed"] == 5
    
    await processor.stop()


@pytest.mark.skip(reason="Async tests require pytest-asyncio")
async def test_processor_state_updates(processor, action_queue, sample_data_spec):
    """Test that processor updates system state correctly."""
    # Start processor
    await processor.start()
    
    # Get initial state
    initial_state = processor.get_state()
    assert initial_state.metrics.total_jobs == 0
    
    # Submit a job creation intent
    intent = CreateJobIntent(
        season="2024Q1",
        data1=sample_data_spec,
        data2=None,
        strategy_id="sma_cross_v1",
        params={"window_fast": 10, "window_slow": 30}
    )
    
    intent_id = processor.submit_intent(intent)
    
    # Wait for completion
    completed = await processor.wait_for_intent(intent_id, timeout=5.0)
    assert completed is not None
    assert completed.status == IntentStatus.COMPLETED
    
    # Check that state was updated
    final_state = processor.get_state()
    assert final_state.metrics.total_jobs == 1
    assert final_state.metrics.queued_jobs == 1
    
    # Job should be in state
    job_id = completed.result["job_id"]
    job = final_state.get_job(job_id)
    assert job is not None
    assert job.season == "2024Q1"
    assert job.status == JobStatus.QUEUED
    
    await processor.stop()


@pytest.mark.skip(reason="Async tests require pytest-asyncio")
async def test_processor_error_handling(processor, action_queue):
    """Test that processor handles errors gracefully."""
    # Start processor
    await processor.start()
    
    # Submit an invalid intent (missing required fields)
    # We'll create a malformed intent by directly manipulating a valid one
    from core.intents import CreateJobIntent, DataSpecIntent
    
    # Create a data spec with empty symbols (should fail validation)
    invalid_data_spec = DataSpecIntent(
        dataset_id="test_dataset",
        symbols=[],  # Empty - should fail validation
        timeframes=["60m"],
        start_date=date(2020, 1, 1),
        end_date=date(2024, 12, 31)
    )
    
    intent = CreateJobIntent(
        season="2024Q1",
        data1=invalid_data_spec,
        data2=None,
        strategy_id="sma_cross_v1",
        params={"window_fast": 10}
    )
    
    intent_id = processor.submit_intent(intent)
    
    # Wait for completion (should fail)
    completed = await processor.wait_for_intent(intent_id, timeout=5.0)
    assert completed is not None
    assert completed.status == IntentStatus.FAILED
    assert completed.error_message is not None
    assert "validation" in completed.error_message.lower() or "empty" in completed.error_message.lower()
    
    # Check metrics
    state = processor.get_state()
    assert state.intent_queue.failed_count == 1
    
    await processor.stop()


@pytest.mark.skip(reason="Async tests require pytest-asyncio")
async def test_processor_concurrent_submission(processor, action_queue, sample_data_spec):
    """Test that processor handles concurrent intent submissions correctly."""
    # Start processor
    await processor.start()
    
    # Submit intents from multiple threads
    intent_ids = []
    
    async def submit_intent(i: int):
        intent = CalculateUnitsIntent(
            season=f"2024Q{i}",
            data1=sample_data_spec,
            data2=None,
            strategy_id="sma_cross_v1",
            params={"window_fast": i}
        )
        intent_id = processor.submit_intent(intent)
        intent_ids.append(intent_id)
        return intent_id
    
    # Submit concurrently
    tasks = [submit_intent(i) for i in range(10)]
    await asyncio.gather(*tasks)
    
    # Wait for all to complete
    for intent_id in intent_ids:
        completed = await processor.wait_for_intent(intent_id, timeout=5.0)
        assert completed is not None
        assert completed.status == IntentStatus.COMPLETED
    
    # All should be processed
    state = processor.get_state()
    assert state.intent_queue.completed_count == 10
    
    await processor.stop()


def test_state_immutability():
    """Test that SystemState is immutable (read-only)."""
    # Create initial state
    state = create_initial_state()
    
    # Try to modify attributes (should fail or create new object)
    # Since Pydantic models with frozen=True raise ValidationError on modification
    with pytest.raises(Exception):
        state.metrics.total_jobs = 100  # Should fail
    
    # Verify state hasn't changed
    assert state.metrics.total_jobs == 0


def test_state_snapshot_creation():
    """Test creating state snapshots with updates."""
    # Create initial state
    state = create_initial_state()
    
    # Create snapshot with updates
    from core.state import create_state_snapshot, SystemMetrics
    
    new_metrics = SystemMetrics(
        total_jobs=5,
        active_jobs=2,
        queued_jobs=3,
        completed_jobs=0,
        failed_jobs=0,
        total_units_processed=100,
        units_per_second=10.0,
        memory_usage_mb=512.0,
        cpu_usage_percent=25.0,
        disk_usage_gb=5.0,
        snapshot_timestamp=datetime.now(),
        uptime_seconds=3600.0
    )
    
    new_state = create_state_snapshot(
        state,
        metrics=new_metrics,
        is_healthy=True
    )
    
    # New state should have updated values
    assert new_state.metrics.total_jobs == 5
    assert new_state.metrics.active_jobs == 2
    assert new_state.is_healthy is True
    
    # Original state should be unchanged
    assert state.metrics.total_jobs == 0
    assert state.metrics.active_jobs == 0


@pytest.mark.skip(reason="Async tests require pytest-asyncio")
async def test_processor_get_state_snapshot(processor):
    """Test that get_state() returns consistent snapshots."""
    # Start processor
    await processor.start()
    
    # Get multiple state snapshots
    state1 = processor.get_state()
    await asyncio.sleep(0.1)
    state2 = processor.get_state()
    
    # Snapshots should be different objects
    assert state1 is not state2
    assert state1.state_id != state2.state_id
    
    # But should have same basic structure
    assert isinstance(state1, SystemState)
    assert isinstance(state2, SystemState)
    
    await processor.stop()


@pytest.mark.skip(reason="Async tests require pytest-asyncio")
async def test_processor_queue_status_updates(processor, action_queue, sample_data_spec):
    """Test that processor updates queue status in state."""
    # Start processor
    await processor.start()
    
    # Submit some intents
    for i in range(3):
        intent = CalculateUnitsIntent(
            season=f"2024Q{i}",
            data1=sample_data_spec,
            data2=None,
            strategy_id="sma_cross_v1",
            params={"window_fast": i}
        )
        processor.submit_intent(intent)
    
    # Wait a bit for processing to start
    await asyncio.sleep(0.5)
    
    # Check queue status in state
    state = processor.get_state()
    assert state.intent_queue.queue_size >= 0
    assert state.intent_queue.completed_count >= 0
    
    # Wait for all to complete
    await asyncio.sleep(2.0)
    
    # Final state should show all completed
    final_state = processor.get_state()
    assert final_state.intent_queue.completed_count == 3
    
    await processor.stop()


def test_processor_singleton():
    """Test that get_processor() returns singleton instance."""
    # Reset to ensure clean state
    reset_action_queue()
    
    # First call should create instance
    processor1 = get_processor()
    assert processor1 is not None
    
    # Second call should return same instance
    processor2 = get_processor()
    assert processor2 is processor1


@pytest.mark.skip(reason="Async tests require pytest-asyncio")
async def test_processor_stop_before_start():
    """Test that processor can be stopped even if not started."""
    from control.action_queue import ActionQueue
    from core.processor import StateProcessor
    
    queue = ActionQueue()
    processor = StateProcessor(queue)
    
    # Should not raise exception
    await processor.stop()


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v"])