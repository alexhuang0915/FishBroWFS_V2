"""Test UI race condition defense for Attack #9 – Headless Intent-State Contract.

Tests that UI cannot cause race conditions because:
1. UI only creates intents (no business logic)
2. All intents go through single ActionQueue
3. StateProcessor is single consumer (sequential execution)
4. UI only reads SystemState snapshots (immutable)
"""

import pytest
import asyncio
import threading
import time
from datetime import date
from concurrent.futures import ThreadPoolExecutor

from FishBroWFS_V2.core.intents import (
    CreateJobIntent, CalculateUnitsIntent, DataSpecIntent,
    IntentStatus
)
from FishBroWFS_V2.control.action_queue import ActionQueue, reset_action_queue
from FishBroWFS_V2.core.processor import StateProcessor, get_processor, start_processor, stop_processor
from FishBroWFS_V2.gui.adapters.intent_bridge import IntentBridge, get_intent_bridge
from FishBroWFS_V2.core.state import SystemState


@pytest.fixture
def clean_system():
    """Clean system state before each test."""
    reset_action_queue()
    # Note: We can't easily reset the singleton processor, so we'll create new instances
    yield
    reset_action_queue()


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


def test_ui_only_creates_intents():
    """Test that UI code only creates intents, doesn't execute logic."""
    bridge = IntentBridge()
    
    # UI creates intents through bridge
    data_spec = bridge.create_data_spec_intent(
        dataset_id="test",
        symbols=["MNQ"],
        timeframes=["60m"]
    )
    
    intent = bridge.create_job_intent(
        season="2024Q1",
        data1=data_spec,
        data2=None,
        strategy_id="test",
        params={}
    )
    
    # Intent should be created but not executed
    assert intent.intent_type.value == "create_job"
    assert intent.status == IntentStatus.PENDING
    assert intent.result is None
    
    # UI cannot directly call backend logic through bridge
    # (bridge only has intent creation and submission methods)


@pytest.mark.asyncio
async def test_single_consumer_sequential(clean_system, sample_data_spec):
    """Test that StateProcessor is single consumer (sequential execution)."""
    queue = ActionQueue()
    processor = StateProcessor(queue)
    
    await processor.start()
    
    # Track processing order
    processing_order = []
    processing_times = []
    
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
        intent_id = queue.submit(intent)
        intent_ids.append(intent_id)
    
    # Wait for all to complete
    for intent_id in intent_ids:
        completed = await queue.wait_for_intent_async(intent_id, timeout=5.0)
        assert completed is not None
        assert completed.status == IntentStatus.COMPLETED
    
    # Check that they were processed sequentially
    # (We can't easily verify exact order without instrumentation,
    # but we can verify all were processed)
    metrics = queue.get_metrics()
    assert metrics["processed"] == 5
    
    await processor.stop()


@pytest.mark.asyncio
async def test_concurrent_ui_submissions(clean_system, sample_data_spec):
    """Test that concurrent UI submissions don't cause race conditions."""
    queue = ActionQueue()
    processor = StateProcessor(queue)
    
    await processor.start()
    
    # Simulate multiple UI threads submitting intents concurrently
    results = []
    errors = []
    
    async def ui_thread_submit(thread_id: int):
        """Simulate a UI thread submitting intents."""
        try:
            # UI creates intent
            intent = CalculateUnitsIntent(
                season=f"2024Q{thread_id}",
                data1=sample_data_spec,
                data2=None,
                strategy_id="sma_cross_v1",
                params={"window_fast": thread_id}
            )
            
            # Submit to queue
            intent_id = queue.submit(intent)
            
            # Wait for result
            completed = await queue.wait_for_intent_async(intent_id, timeout=5.0)
            if completed and completed.status == IntentStatus.COMPLETED:
                results.append((thread_id, completed.result))
            else:
                errors.append((thread_id, "Failed"))
                
        except Exception as e:
            errors.append((thread_id, str(e)))
    
    # Launch multiple UI threads
    tasks = [ui_thread_submit(i) for i in range(10)]
    await asyncio.gather(*tasks)
    
    # All should succeed without race conditions
    assert len(errors) == 0
    assert len(results) == 10
    
    # Check that queue processed all intents
    metrics = queue.get_metrics()
    assert metrics["processed"] == 10
    
    await processor.stop()


def test_immutable_state_snapshots():
    """Test that UI only reads immutable state snapshots."""
    from FishBroWFS_V2.core.state import create_initial_state
    
    # Create initial state
    state = create_initial_state()
    
    # UI reads state (this is allowed)
    total_jobs = state.metrics.total_jobs
    is_healthy = state.is_healthy
    
    # UI cannot modify state (should raise exception)
    with pytest.raises(Exception):
        state.metrics.total_jobs = 100  # Should fail
    
    # Verify state hasn't changed
    assert state.metrics.total_jobs == total_jobs
    assert state.is_healthy == is_healthy
    
    # UI can create new state objects through processor, but not modify existing ones


@pytest.mark.asyncio
async def test_state_consistency_during_concurrent_reads(clean_system, sample_data_spec):
    """Test that concurrent state reads are consistent."""
    queue = ActionQueue()
    processor = StateProcessor(queue)
    
    await processor.start()
    
    # Submit a job to change state
    intent = CreateJobIntent(
        season="2024Q1",
        data1=sample_data_spec,
        data2=None,
        strategy_id="sma_cross_v1",
        params={"window_fast": 10}
    )
    
    intent_id = processor.submit_intent(intent)
    
    # Multiple UI threads reading state concurrently
    read_values = []
    
    async def ui_thread_read(thread_id: int):
        """UI thread reads state."""
        # Get state snapshot
        state = processor.get_state()
        read_values.append((thread_id, state.metrics.total_jobs))
    
    # Launch concurrent reads
    tasks = [ui_thread_read(i) for i in range(10)]
    await asyncio.gather(*tasks)
    
    # All reads should see consistent state
    # (either all see 0 jobs or all see 1 job, depending on timing)
    unique_values = set(value for _, value in read_values)
    assert len(unique_values) == 1  # All threads see same value
    
    # Wait for intent to complete
    await processor.wait_for_intent(intent_id, timeout=5.0)
    
    # Now all threads should see updated state
    final_state = processor.get_state()
    assert final_state.metrics.total_jobs == 1
    
    await processor.stop()


def test_intent_bridge_singleton():
    """Test that IntentBridge is singleton."""
    bridge1 = get_intent_bridge()
    bridge2 = get_intent_bridge()
    
    assert bridge1 is bridge2


@pytest.mark.asyncio
async def test_bridge_concurrent_usage(clean_system):
    """Test IntentBridge with concurrent UI access."""
    bridge = IntentBridge()
    
    # Start processor
    await bridge.start_processor()
    
    # Multiple UI threads using bridge concurrently
    results = []
    
    async def ui_thread_use_bridge(thread_id: int):
        """UI thread uses bridge."""
        # Create data spec
        data_spec = bridge.create_data_spec_intent(
            dataset_id=f"dataset_{thread_id}",
            symbols=["MNQ"],
            timeframes=["60m"]
        )
        
        # Create calculation intent
        intent = bridge.calculate_units_intent(
            season=f"2024Q{thread_id}",
            data1=data_spec,
            data2=None,
            strategy_id="test",
            params={"param": thread_id}
        )
        
        # Submit and wait
        completed = await bridge.submit_and_wait_async(intent, timeout=5.0)
        if completed and completed.status == IntentStatus.COMPLETED:
            results.append((thread_id, completed.result))
    
    # Launch concurrent UI threads
    tasks = [ui_thread_use_bridge(i) for i in range(5)]
    await asyncio.gather(*tasks)
    
    # All should succeed
    assert len(results) == 5
    
    await bridge.stop_processor()


def test_no_direct_backend_imports():
    """Test that UI modules shouldn't import backend logic directly."""
    import sys
    
    # Check that intent_bridge doesn't expose backend logic
    bridge_module = sys.modules['FishBroWFS_V2.gui.adapters.intent_bridge']
    
    # Bridge should not expose backend functions directly
    assert not hasattr(bridge_module, 'create_job_from_wizard_direct')
    assert not hasattr(bridge_module, 'calculate_units_direct')
    
    # Bridge should expose intent creation methods
    assert hasattr(bridge_module, 'IntentBridge')
    assert hasattr(bridge_module, 'get_intent_bridge')


@pytest.mark.asyncio
async def test_race_condition_prevention(clean_system, sample_data_spec):
    """Test that race conditions are prevented by design."""
    queue = ActionQueue()
    processor = StateProcessor(queue)
    
    await processor.start()
    
    # Simulate race condition scenario:
    # Multiple UI threads trying to create jobs for same season/dataset
    
    created_job_ids = set()
    lock = threading.Lock()
    
    async def race_condition_thread(thread_id: int):
        """Thread that could cause race condition in traditional system."""
        # All threads use same parameters (potential race)
        intent = CreateJobIntent(
            season="2024Q1",  # Same season
            data1=sample_data_spec,  # Same data
            data2=None,
            strategy_id="sma_cross_v1",
            params={"window_fast": 10}
        )
        
        # Submit intent
        intent_id = processor.submit_intent(intent)
        completed = await processor.wait_for_intent(intent_id, timeout=5.0)
        
        if completed and completed.status == IntentStatus.COMPLETED:
            job_id = completed.result.get("job_id")
            with lock:
                created_job_ids.add(job_id)
    
    # Launch many threads simultaneously
    tasks = [race_condition_thread(i) for i in range(20)]
    await asyncio.gather(*tasks)
    
    # In a system with race conditions, we might get duplicate jobs
    # or inconsistent state. With our intent-based system:
    
    # 1. All intents should be processed
    state = processor.get_state()
    assert state.intent_queue.completed_count == 20
    
    # 2. Idempotency should prevent duplicate job creation
    # (All intents have same idempotency_key, so only first should create job)
    metrics = queue.get_metrics()
    assert metrics["duplicate_rejected"] == 19  # 19 duplicates rejected
    
    # 3. Only one job should be created
    assert len(created_job_ids) == 1
    
    await processor.stop()


def test_ui_cannot_bypass_intent_bridge():
    """Test that UI cannot bypass intent bridge to call backend directly."""
    # This is more of a policy/architectural test
    # In practice, we rely on code review and imports checking
    
    # UI should import from intent_bridge, not job_api directly
    import FishBroWFS_V2.gui.adapters.intent_bridge as intent_bridge
    import FishBroWFS_V2.control.job_api as job_api
    
    # UI code should use:
    # from FishBroWFS_V2.gui.adapters.intent_bridge import get_intent_bridge
    # NOT: from FishBroWFS_V2.control.job_api import create_job_from_wizard
    
    # Bridge provides compatibility layer
    assert hasattr(intent_bridge, 'IntentBackendAdapter')
    assert hasattr(intent_bridge, 'default_adapter')
    
    # Adapter provides same interface as job_api
    adapter = intent_bridge.IntentBackendAdapter()
    assert hasattr(adapter, 'create_job_from_wizard')
    assert hasattr(adapter, 'calculate_units')
    
    # But uses intents internally
    # (We can't easily test this without runtime checks)


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v"])