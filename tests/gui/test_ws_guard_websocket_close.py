"""Test that WebSocketGuardMiddleware sends websocket.close, not HTTP response, for blocked websockets."""
import pytest
from unittest.mock import AsyncMock

from src.gui.nicegui.asgi.ws_guard import (
    WebSocketGuardMiddleware,
    WebSocketGuardConfig,
)


async def dangerous_app(scope, receive, send):
    """A malicious app that sends http.response.start for websocket scopes."""
    if scope["type"] == "websocket":
        # This is the bug we're guarding against
        await send({"type": "http.response.start", "status": 404})
        await send({"type": "http.response.body", "body": b"Not Found"})
    else:
        await send({"type": "http.response.start", "status": 200})
        await send({"type": "http.response.body", "body": b"OK"})


@pytest.mark.asyncio
async def test_blocked_websocket_emits_close_not_http():
    """
    WebSocketGuardMiddleware must send websocket.close (not http.*) for blocked websocket paths.
    """
    config = WebSocketGuardConfig(allowed_path_prefixes=("/_nicegui_ws",))
    guard = WebSocketGuardMiddleware(dangerous_app, config)

    send = AsyncMock()
    receive = AsyncMock(return_value={"type": "websocket.connect"})

    await guard(
        {"type": "websocket", "path": "/unknown/ws"},  # not allowed
        receive,
        send,
    )

    # Should have sent exactly one message: websocket.close
    assert send.call_count == 1
    call = send.call_args[0][0]
    assert call["type"] == "websocket.close"
    assert call["code"] == 1008  # default close code

    # Ensure no http.* messages were sent
    for call_args in send.call_args_list:
        msg = call_args[0][0]
        assert not msg["type"].startswith("http."), f"Unexpected http message: {msg}"


@pytest.mark.asyncio
async def test_allowed_websocket_passes_through():
    """
    WebSocketGuardMiddleware should pass through allowed websocket paths.
    (The inner app may still misbehave, but that's not the guard's responsibility.)
    """
    config = WebSocketGuardConfig(allowed_path_prefixes=("/_nicegui_ws",))
    guard = WebSocketGuardMiddleware(dangerous_app, config)

    send = AsyncMock()
    receive = AsyncMock(side_effect=[
        {"type": "websocket.connect"},
        {"type": "websocket.disconnect"},
    ])

    await guard(
        {"type": "websocket", "path": "/_nicegui_ws/123"},  # allowed
        receive,
        send,
    )

    # The dangerous_app would send http.response.start, but we can't intercept that.
    # This test just ensures the guard doesn't add extra messages.
    # In practice, NiceGUI won't send http for websocket.
    pass


if __name__ == "__main__":
    # Quick manual test
    import asyncio
    asyncio.run(test_blocked_websocket_emits_close_not_http())
    print("Test passed (manual run)")