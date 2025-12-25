"""Test idempotency enforcement in ActionQueue for Attack #9.

Tests that duplicate intents are rejected based on idempotency_key.
"""

import pytest
import asyncio
from datetime import date

from FishBroWFS_V2.core.intents import (
    CreateJobIntent, CalculateUnitsIntent, DataSpecIntent,
    IntentStatus
)
from FishBroWFS_V2.control.action_queue import ActionQueue, reset_action_queue
from FishBroWFS_V2.core.processor import StateProcessor


@pytest.fixture
def action_queue():
    """Create a fresh ActionQueue for each test."""
    reset_action_queue()
    queue = ActionQueue(max_size=10)
    yield queue
    queue.clear()


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


def test_idempotency_basic(action_queue, sample_data_spec):
    """Test basic idempotency: duplicate intents are rejected."""
    # Create first intent
    intent1 = CreateJobIntent(
        season="2024Q1",
        data1=sample_data_spec,
        data2=None,
        strategy_id="sma_cross_v1",
        params={"window_fast": 10, "window_slow": 30}
    )
    
    # Create second intent with same parameters (should have same idempotency_key)
    intent2 = CreateJobIntent(
        season="2024Q1",
        data1=sample_data_spec,
        data2=None,
        strategy_id="sma_cross_v1",
        params={"window_fast": 10, "window_slow": 30}
    )
    
    # Submit first intent
    intent1_id = action_queue.submit(intent1)
    assert intent1_id == intent1.intent_id
    assert action_queue.get_queue_size() == 1
    
    # Submit second intent (should be marked as duplicate)
    intent2_id = action_queue.submit(intent2)
    assert intent2_id == intent2.intent_id
    assert action_queue.get_queue_size() == 1  # Queue size shouldn't increase
    
    # Check that second intent is marked as duplicate
    stored_intent2 = action_queue.get_intent(intent2_id)
    assert stored_intent2 is not None
    assert stored_intent2.status == IntentStatus.DUPLICATE
    
    # Check metrics
    metrics = action_queue.get_metrics()
    assert metrics["submitted"] == 1
    assert metrics["duplicate_rejected"] == 1


def test_idempotency_different_params(action_queue, sample_data_spec):
    """Test that intents with different parameters are not duplicates."""
    # Create first intent
    intent1 = CreateJobIntent(
        season="2024Q1",
        data1=sample_data_spec,
        data2=None,
        strategy_id="sma_cross_v1",
        params={"window_fast": 10, "window_slow": 30}
    )
    
    # Create second intent with different parameters
    intent2 = CreateJobIntent(
        season="2024Q1",
        data1=sample_data_spec,
        data2=None,
        strategy_id="sma_cross_v1",
        params={"window_fast": 5, "window_slow": 20}  # Different params
    )
    
    # Both should be accepted
    intent1_id = action_queue.submit(intent1)
    intent2_id = action_queue.submit(intent2)
    
    assert intent1_id != intent2_id
    assert action_queue.get_queue_size() == 2
    
    # Check metrics
    metrics = action_queue.get_metrics()
    assert metrics["submitted"] == 2
    assert metrics["duplicate_rejected"] == 0


def test_idempotency_calculate_units(action_queue, sample_data_spec):
    """Test idempotency for CalculateUnitsIntent."""
    # Create first calculation intent
    intent1 = CalculateUnitsIntent(
        season="2024Q1",
        data1=sample_data_spec,
        data2=None,
        strategy_id="sma_cross_v1",
        params={"window_fast": 10}
    )
    
    # Create duplicate calculation intent
    intent2 = CalculateUnitsIntent(
        season="2024Q1",
        data1=sample_data_spec,
        data2=None,
        strategy_id="sma_cross_v1",
        params={"window_fast": 10}
    )
    
    # Submit both
    action_queue.submit(intent1)
    action_queue.submit(intent2)
    
    # Only one should be in queue
    assert action_queue.get_queue_size() == 1
    
    metrics = action_queue.get_metrics()
    assert metrics["duplicate_rejected"] == 1


def test_idempotency_manual_key(action_queue, sample_data_spec):
    """Test idempotency with manually set idempotency_key."""
    # Create intents with same manual idempotency_key
    intent1 = CreateJobIntent(
        season="2024Q1",
        data1=sample_data_spec,
        data2=None,
        strategy_id="sma_cross_v1",
        params={"window_fast": 10},
        idempotency_key="manual_key_123"
    )
    
    intent2 = CreateJobIntent(
        season="2024Q2",  # Different season
        data1=sample_data_spec,
        data2=None,
        strategy_id="sma_cross_v1",
        params={"window_fast": 10},
        idempotency_key="manual_key_123"  # Same key
    )
    
    # Second should be duplicate despite different parameters
    action_queue.submit(intent1)
    action_queue.submit(intent2)
    
    assert action_queue.get_queue_size() == 1
    metrics = action_queue.get_metrics()
    assert metrics["duplicate_rejected"] == 1


def test_queue_full_rejection(action_queue, sample_data_spec):
    """Test that queue rejects intents when full."""
    # Fill the queue
    for i in range(10):  # max_size is 10
        intent = CreateJobIntent(
            season=f"2024Q{i}",
            data1=sample_data_spec,
            data2=None,
            strategy_id="sma_cross_v1",
            params={"window_fast": i}
        )
        action_queue.submit(intent)
    
    assert action_queue.get_queue_size() == 10
    
    # Try to submit one more (should fail)
    extra_intent = CreateJobIntent(
        season="2024Q99",
        data1=sample_data_spec,
        data2=None,
        strategy_id="sma_cross_v1",
        params={"window_fast": 99}
    )
    
    with pytest.raises(ValueError, match="ActionQueue is full"):
        action_queue.submit(extra_intent)
    
    metrics = action_queue.get_metrics()
    assert metrics["queue_full_rejected"] == 1


def test_intent_retrieval(action_queue, sample_data_spec):
    """Test retrieving intents by ID."""
    intent = CreateJobIntent(
        season="2024Q1",
        data1=sample_data_spec,
        data2=None,
        strategy_id="sma_cross_v1",
        params={"window_fast": 10}
    )
    
    intent_id = action_queue.submit(intent)
    
    # Retrieve intent
    retrieved = action_queue.get_intent(intent_id)
    assert retrieved is not None
    assert retrieved.intent_id == intent_id
    assert retrieved.season == "2024Q1"
    assert retrieved.status == IntentStatus.PENDING
    
    # Try to retrieve non-existent intent
    assert action_queue.get_intent("non_existent_id") is None


@pytest.mark.skip(reason="Async tests require pytest-asyncio")
async def test_wait_for_intent(action_queue, sample_data_spec):
    """Test waiting for intent completion."""
    intent = CreateJobIntent(
        season="2024Q1",
        data1=sample_data_spec,
        data2=None,
        strategy_id="sma_cross_v1",
        params={"window_fast": 10}
    )
    
    intent_id = action_queue.submit(intent)
    
    # Mark as completed in background
    async def mark_completed():
        await asyncio.sleep(0.1)
        action_queue.mark_completed(intent_id, {"result": "success"})
    
    # Wait for completion
    task = asyncio.create_task(mark_completed())
    completed = await action_queue.wait_for_intent_async(intent_id, timeout=1.0)
    
    await task
    
    assert completed is not None
    assert completed.status == IntentStatus.COMPLETED
    assert completed.result == {"result": "success"}


@pytest.mark.skip(reason="Async tests require pytest-asyncio")
async def test_wait_for_intent_timeout(action_queue, sample_data_spec):
    """Test timeout when waiting for intent."""
    intent = CreateJobIntent(
        season="2024Q1",
        data1=sample_data_spec,
        data2=None,
        strategy_id="sma_cross_v1",
        params={"window_fast": 10}
    )
    
    intent_id = action_queue.submit(intent)
    
    # Wait with short timeout (intent won't be completed)
    completed = await action_queue.wait_for_intent_async(intent_id, timeout=0.1)
    
    assert completed is None  # Should timeout


def test_queue_state_debugging(action_queue, sample_data_spec):
    """Test queue state debugging method."""
    # Add some intents
    for i in range(3):
        intent = CreateJobIntent(
            season=f"2024Q{i}",
            data1=sample_data_spec,
            data2=None,
            strategy_id="sma_cross_v1",
            params={"window_fast": i}
        )
        action_queue.submit(intent)
    
    # Get queue state
    state = action_queue.get_queue_state()
    
    assert len(state) == 3
    for i, item in enumerate(state):
        assert "intent_id" in item
        assert item["type"] == "create_job"
        assert item["status"] == "pending"


def test_clear_queue(action_queue, sample_data_spec):
    """Test clearing the queue."""
    # Add some intents
    for i in range(5):
        intent = CreateJobIntent(
            season=f"2024Q{i}",
            data1=sample_data_spec,
            data2=None,
            strategy_id="sma_cross_v1",
            params={"window_fast": i}
        )
        action_queue.submit(intent)
    
    assert action_queue.get_queue_size() == 5
    
    # Clear queue
    action_queue.clear()
    
    assert action_queue.get_queue_size() == 0
    assert action_queue.get_metrics()["submitted"] == 0
    
    # Should be able to submit new intents after clear
    new_intent = CreateJobIntent(
        season="2024Q1",
        data1=sample_data_spec,
        data2=None,
        strategy_id="sma_cross_v1",
        params={"window_fast": 10}
    )
    
    action_queue.submit(new_intent)
    assert action_queue.get_queue_size() == 1