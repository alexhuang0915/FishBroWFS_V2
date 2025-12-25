"""ActionQueue - FIFO queue with idempotency for Attack #9 – Headless Intent-State Contract.

ActionQueue is the single queue that all intents must go through. It enforces
FIFO ordering and idempotency (duplicate intents are rejected). StateProcessor
is the single consumer that reads from this queue.
"""

from __future__ import annotations

import asyncio
import threading
import time
from collections import deque
from datetime import datetime
from typing import Dict, List, Optional, Set, Deque
from concurrent.futures import Future

from FishBroWFS_V2.core.intents import UserIntent, IntentStatus, IntentType


class ActionQueue:
    """FIFO queue with idempotency enforcement.
    
    All intents must go through this single queue. It ensures:
    1. FIFO ordering (first in, first out)
    2. Idempotency (duplicate intents are rejected based on idempotency_key)
    3. Thread-safe operations
    4. Async support for waiting on intent completion
    """
    
    def __init__(self, max_size: int = 1000):
        self.max_size = max_size
        self.queue: Deque[UserIntent] = deque(maxlen=max_size)
        self.intent_by_id: Dict[str, UserIntent] = {}
        self.seen_idempotency_keys: Set[str] = set()
        self.completion_futures: Dict[str, Future] = {}
        self.lock = threading.RLock()
        self.condition = threading.Condition(self.lock)
        self.metrics = {
            "submitted": 0,
            "processed": 0,
            "duplicate_rejected": 0,
            "queue_full_rejected": 0,
        }
    
    def submit(self, intent: UserIntent) -> str:
        """Submit an intent to the queue.
        
        Args:
            intent: The UserIntent to submit
            
        Returns:
            intent_id: The ID of the submitted intent
            
        Raises:
            ValueError: If queue is full or intent is invalid
        """
        with self.lock:
            # Check if queue is full
            if len(self.queue) >= self.max_size:
                self.metrics["queue_full_rejected"] += 1
                raise ValueError(f"ActionQueue is full (max_size={self.max_size})")
            
            # Check idempotency
            if intent.idempotency_key in self.seen_idempotency_keys:
                # Mark as duplicate
                intent.status = IntentStatus.DUPLICATE
                self.intent_by_id[intent.intent_id] = intent
                self.metrics["duplicate_rejected"] += 1
                
                # Still return the intent ID so caller can check status
                return intent.intent_id
            
            # Add to queue
            self.queue.append(intent)
            self.intent_by_id[intent.intent_id] = intent
            self.seen_idempotency_keys.add(intent.idempotency_key)
            self.metrics["submitted"] += 1
            
            # Create completion future
            self.completion_futures[intent.intent_id] = Future()
            
            # Notify waiting consumers
            with self.condition:
                self.condition.notify_all()
            
            return intent.intent_id
    
    def get_next(self, block: bool = True, timeout: Optional[float] = None) -> Optional[UserIntent]:
        """Get the next intent from the queue.
        
        Args:
            block: If True, block until an intent is available
            timeout: Maximum time to block in seconds
            
        Returns:
            The next UserIntent, or None if queue is empty and block=False
        """
        with self.lock:
            if self.queue:
                return self.queue[0]
            
            if not block:
                return None
            
            # Wait for an intent to become available
            with self.condition:
                if timeout is None:
                    self.condition.wait()
                else:
                    self.condition.wait(timeout)
                
                if self.queue:
                    return self.queue[0]
                else:
                    return None
    
    def mark_processing(self, intent_id: str) -> None:
        """Mark an intent as being processed.
        
        Should be called by StateProcessor when it starts processing an intent.
        """
        with self.lock:
            if intent_id in self.intent_by_id:
                intent = self.intent_by_id[intent_id]
                intent.status = IntentStatus.PROCESSING
                intent.processed_at = datetime.now()
    
    def mark_completed(self, intent_id: str, result: Optional[Dict] = None) -> None:
        """Mark an intent as completed.
        
        Should be called by StateProcessor when it finishes processing an intent.
        """
        with self.lock:
            if intent_id in self.intent_by_id:
                intent = self.intent_by_id[intent_id]
                intent.status = IntentStatus.COMPLETED
                intent.result = result
                
                # Remove from queue if it's still there
                if self.queue and self.queue[0].intent_id == intent_id:
                    self.queue.popleft()
                
                # Set completion future result
                if intent_id in self.completion_futures:
                    self.completion_futures[intent_id].set_result(intent)
                    del self.completion_futures[intent_id]
                
                self.metrics["processed"] += 1
    
    def mark_failed(self, intent_id: str, error_message: str) -> None:
        """Mark an intent as failed.
        
        Should be called by StateProcessor when intent processing fails.
        """
        with self.lock:
            if intent_id in self.intent_by_id:
                intent = self.intent_by_id[intent_id]
                intent.status = IntentStatus.FAILED
                intent.error_message = error_message
                
                # Remove from queue if it's still there
                if self.queue and self.queue[0].intent_id == intent_id:
                    self.queue.popleft()
                
                # Set completion future result
                if intent_id in self.completion_futures:
                    self.completion_futures[intent_id].set_result(intent)
                    del self.completion_futures[intent_id]
                
                self.metrics["processed"] += 1
    
    def get_intent(self, intent_id: str) -> Optional[UserIntent]:
        """Get intent by ID."""
        with self.lock:
            return self.intent_by_id.get(intent_id)
    
    def wait_for_intent(self, intent_id: str, timeout: Optional[float] = None) -> Optional[UserIntent]:
        """Wait for an intent to complete.
        
        Args:
            intent_id: ID of the intent to wait for
            timeout: Maximum time to wait in seconds
            
        Returns:
            The completed UserIntent, or None if timeout
        """
        with self.lock:
            # Check if already completed
            intent = self.intent_by_id.get(intent_id)
            if intent and intent.status in [IntentStatus.COMPLETED, IntentStatus.FAILED, IntentStatus.DUPLICATE]:
                return intent
            
            # Wait for completion future
            future = self.completion_futures.get(intent_id)
            if not future:
                # Intent not found or no future created
                return None
        
        # Wait for future outside of lock
        try:
            if timeout is None:
                result = future.result()
            else:
                result = future.result(timeout=timeout)
            return result
        except Exception:
            return None
    
    async def wait_for_intent_async(self, intent_id: str, timeout: Optional[float] = None) -> Optional[UserIntent]:
        """Async version of wait_for_intent."""
        loop = asyncio.get_event_loop()
        
        with self.lock:
            # Check if already completed
            intent = self.intent_by_id.get(intent_id)
            if intent and intent.status in [IntentStatus.COMPLETED, IntentStatus.FAILED, IntentStatus.DUPLICATE]:
                return intent
            
            future = self.completion_futures.get(intent_id)
            if not future:
                return None
        
        # Wait for future asynchronously
        try:
            if timeout is None:
                result = await loop.run_in_executor(None, future.result)
            else:
                result = await asyncio.wait_for(
                    loop.run_in_executor(None, future.result),
                    timeout
                )
            return result
        except (asyncio.TimeoutError, Exception):
            return None
    
    def get_queue_size(self) -> int:
        """Get current queue size."""
        with self.lock:
            return len(self.queue)
    
    def get_metrics(self) -> Dict[str, int]:
        """Get queue metrics."""
        with self.lock:
            return self.metrics.copy()
    
    def clear(self) -> None:
        """Clear the queue (for testing)."""
        with self.lock:
            self.queue.clear()
            self.intent_by_id.clear()
            self.seen_idempotency_keys.clear()
            for future in self.completion_futures.values():
                future.cancel()
            self.completion_futures.clear()
            self.metrics = {
                "submitted": 0,
                "processed": 0,
                "duplicate_rejected": 0,
                "queue_full_rejected": 0,
            }
    
    def get_queue_state(self) -> List[Dict]:
        """Get current queue state for debugging."""
        with self.lock:
            return [
                {
                    "intent_id": intent.intent_id,
                    "type": intent.intent_type.value,
                    "status": intent.status.value,
                    "created_at": intent.created_at.isoformat() if intent.created_at else None,
                }
                for intent in self.queue
            ]


# Singleton instance for application use
_action_queue_instance: Optional[ActionQueue] = None


def get_action_queue() -> ActionQueue:
    """Get the singleton ActionQueue instance."""
    global _action_queue_instance
    if _action_queue_instance is None:
        _action_queue_instance = ActionQueue()
    return _action_queue_instance


def reset_action_queue() -> None:
    """Reset the singleton ActionQueue (for testing)."""
    global _action_queue_instance
    if _action_queue_instance:
        _action_queue_instance.clear()
    _action_queue_instance = None


class IntentSubmitter:
    """Helper class for submitting intents with retry and timeout."""
    
    def __init__(self, queue: Optional[ActionQueue] = None):
        self.queue = queue or get_action_queue()
        self.default_timeout = 30.0
        self.max_retries = 3
    
    def submit_and_wait(
        self,
        intent: UserIntent,
        timeout: Optional[float] = None,
        retries: int = 0
    ) -> Optional[UserIntent]:
        """Submit an intent and wait for completion.
        
        Args:
            intent: The UserIntent to submit
            timeout: Maximum time to wait in seconds
            retries: Number of retries on failure
            
        Returns:
            The completed UserIntent, or None if failed after retries
        """
        timeout = timeout or self.default_timeout
        
        for attempt in range(retries + 1):
            try:
                # Submit intent
                intent_id = self.queue.submit(intent)
                
                # Wait for completion
                result = self.queue.wait_for_intent(intent_id, timeout)
                
                if result:
                    return result
                
                # Timeout
                if attempt < retries:
                    print(f"Attempt {attempt + 1} timed out, retrying...")
                    continue
                
            except ValueError as e:
                # Queue full or duplicate
                if "duplicate" in str(e).lower() or attempt >= retries:
                    raise
                print(f"Attempt {attempt + 1} failed: {e}, retrying...")
                time.sleep(0.1 * (attempt + 1))  # Exponential backoff
        
        return None
    
    async def submit_and_wait_async(
        self,
        intent: UserIntent,
        timeout: Optional[float] = None,
        retries: int = 0
    ) -> Optional[UserIntent]:
        """Async version of submit_and_wait."""
        timeout = timeout or self.default_timeout
        
        for attempt in range(retries + 1):
            try:
                # Submit intent
                intent_id = self.queue.submit(intent)
                
                # Wait for completion
                result = await self.queue.wait_for_intent_async(intent_id, timeout)
                
                if result:
                    return result
                
                # Timeout
                if attempt < retries:
                    print(f"Attempt {attempt + 1} timed out, retrying...")
                    continue
                
            except ValueError as e:
                # Queue full or duplicate
                if "duplicate" in str(e).lower() or attempt >= retries:
                    raise
                print(f"Attempt {attempt + 1} failed: {e}, retrying...")
                await asyncio.sleep(0.1 * (attempt + 1))  # Exponential backoff
        
        return None