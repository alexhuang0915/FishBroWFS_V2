"""
Test registry context isolation with ContextVar.

Proves that FeatureRegistry instances are isolated per async task
and that ContextVar provides proper isolation for parallel execution.
"""
import asyncio
import pytest
from src.features.registry import (
    FeatureRegistry,
    get_default_registry,
    set_default_registry,
    reset_default_registry,
)


async def task(name: str):
    reg = FeatureRegistry()
    set_default_registry(reg)
    # Register a simple feature (skip verification for test simplicity)
    reg.register_feature(
        name=f"feature_{name}",
        timeframe_min=15,
        lookback_bars=10,
        params={},
        compute_func=lambda x: x,
        skip_verification=False
    )
    current = get_default_registry()
    # Check that the feature was registered by looking at specs
    assert any(spec.name == f"feature_{name}" for spec in current.specs)
    return current


@pytest.mark.anyio
async def test_registry_context_isolation():
    reset_default_registry()

    reg_a, reg_b = await asyncio.gather(
        task("A"),
        task("B"),
    )

    assert reg_a is not reg_b
    assert any(spec.name == "feature_A" for spec in reg_a.specs)
    assert not any(spec.name == "feature_B" for spec in reg_a.specs)
    assert any(spec.name == "feature_B" for spec in reg_b.specs)
    assert not any(spec.name == "feature_A" for spec in reg_b.specs)


@pytest.mark.anyio
async def test_registry_context_inheritance_break():
    """Test that explicit set_default_registry breaks inheritance."""
    reset_default_registry()
    
    # Create parent registry
    parent_reg = FeatureRegistry()
    parent_reg.register_feature(
        name="parent_feature",
        timeframe_min=15,
        lookback_bars=10,
        params={},
        compute_func=lambda x: x,
        skip_verification=False
    )
    set_default_registry(parent_reg)
    
    # Verify parent context
    assert get_default_registry() is parent_reg
    assert any(spec.name == "parent_feature" for spec in parent_reg.specs)
    
    # Create child task with its own registry
    async def child_task():
        child_reg = FeatureRegistry()
        set_default_registry(child_reg)  # Explicitly set, breaking inheritance
        child_reg.register_feature(
            name="child_feature",
            timeframe_min=15,
            lookback_bars=10,
            params={},
            compute_func=lambda x: x,
            skip_verification=False
        )
        return get_default_registry()
    
    # Run child task in separate asyncio task using gather (creates new task)
    [child_reg] = await asyncio.gather(child_task())
    
    # Child should have its own registry
    assert child_reg is not parent_reg
    assert any(spec.name == "child_feature" for spec in child_reg.specs)
    assert not any(spec.name == "parent_feature" for spec in child_reg.specs)
    
    # Parent registry should remain unchanged (we're back in parent context)
    assert get_default_registry() is parent_reg  # Back in parent context
    assert any(spec.name == "parent_feature" for spec in parent_reg.specs)


@pytest.mark.anyio
async def test_reset_clears_context():
    """Test that reset_default_registry clears the context."""
    reg = FeatureRegistry()
    set_default_registry(reg)
    assert get_default_registry() is reg
    
    reset_default_registry()
    
    # After reset, get_default_registry should create a new instance
    new_reg = get_default_registry()
    assert new_reg is not reg


def test_sync_context_isolation():
    """Test isolation in synchronous code using manual context management."""
    reset_default_registry()
    
    # Create first registry in main context
    reg1 = FeatureRegistry()
    set_default_registry(reg1)
    reg1.register_feature(
        name="feature1",
        timeframe_min=15,
        lookback_bars=10,
        params={},
        compute_func=lambda x: x,
        skip_verification=False
    )
    
    # Save token and set new registry
    import contextvars
    from src.features.registry import _registry_ctx
    
    token = _registry_ctx.set(None)  # Temporarily clear
    
    # Create second registry
    reg2 = FeatureRegistry()
    set_default_registry(reg2)
    reg2.register_feature(
        name="feature2",
        timeframe_min=15,
        lookback_bars=10,
        params={},
        compute_func=lambda x: x,
        skip_verification=False
    )
    
    assert get_default_registry() is reg2
    assert any(spec.name == "feature2" for spec in reg2.specs)
    assert not any(spec.name == "feature1" for spec in reg2.specs)
    
    # Restore previous context
    _registry_ctx.reset(token)
    
    # Should be back to reg1
    assert get_default_registry() is reg1
    assert any(spec.name == "feature1" for spec in reg1.specs)
    assert not any(spec.name == "feature2" for spec in reg1.specs)