"""Test WebSocketGuardMiddleware."""
import asyncio
import os
from unittest.mock import AsyncMock, Mock

import pytest

from src.gui.nicegui.asgi.ws_guard import (
    WebSocketGuardMiddleware,
    WebSocketGuardConfig,
    default_ws_guard_config_from_env,
)


async def dummy_app(scope, receive, send):
    """Dummy ASGI app that echoes websocket messages."""
    if scope["type"] == "websocket":
        await send({"type": "websocket.accept"})
        while True:
            msg = await receive()
            if msg["type"] == "websocket.receive":
                await send({"type": "websocket.send", "text": "echo"})
            elif msg["type"] == "websocket.disconnect":
                break
    else:
        await send({"type": "http.response.start", "status": 200})
        await send({"type": "http.response.body", "body": b"OK"})


@pytest.mark.anyio
async def test_guard_passes_http():
    """WebSocketGuardMiddleware should pass through HTTP scopes unchanged."""
    config = WebSocketGuardConfig(allowed_path_prefixes=("/_nicegui_ws",))
    guard = WebSocketGuardMiddleware(dummy_app, config)
    
    send = AsyncMock()
    await guard(
        {"type": "http", "path": "/any"},
        AsyncMock(return_value={"type": "http.request"}),
        send,
    )
    
    # Should have called send with http response
    assert send.call_count >= 1
    first_call = send.call_args_list[0][0][0]
    assert first_call["type"] == "http.response.start"


@pytest.mark.anyio
async def test_guard_allows_nicegui_ws():
    """WebSocketGuardMiddleware should allow NiceGUI WebSocket paths."""
    config = WebSocketGuardConfig(allowed_path_prefixes=("/_nicegui_ws", "/socket.io"))
    guard = WebSocketGuardMiddleware(dummy_app, config)
    
    send = AsyncMock()
    receive = AsyncMock(side_effect=[
        {"type": "websocket.connect"},
        {"type": "websocket.disconnect"},
    ])
    
    await guard(
        {"type": "websocket", "path": "/_nicegui_ws/123"},
        receive,
        send,
    )
    
    # Should have called websocket.accept (passed through)
    assert send.call_count >= 1
    first_call = send.call_args_list[0][0][0]
    assert first_call["type"] == "websocket.accept"


@pytest.mark.anyio
async def test_guard_denies_unknown_ws():
    """WebSocketGuardMiddleware should deny unknown WebSocket paths."""
    config = WebSocketGuardConfig(allowed_path_prefixes=("/_nicegui_ws",))
    guard = WebSocketGuardMiddleware(dummy_app, config)
    
    send = AsyncMock()
    receive = AsyncMock(return_value={"type": "websocket.connect"})
    
    await guard(
        {"type": "websocket", "path": "/unknown/ws"},
        receive,
        send,
    )
    
    # Should send websocket.close and NOT call dummy_app
    assert send.call_count == 1
    call = send.call_args[0][0]
    assert call["type"] == "websocket.close"
    assert call["code"] == 1008  # default close code


@pytest.mark.anyio
async def test_guard_close_code_configurable():
    """WebSocketGuardMiddleware should respect configured close code."""
    config = WebSocketGuardConfig(allowed_path_prefixes=(), close_code=4000)
    guard = WebSocketGuardMiddleware(dummy_app, config)
    
    send = AsyncMock()
    receive = AsyncMock(return_value={"type": "websocket.connect"})
    
    await guard(
        {"type": "websocket", "path": "/any"},
        receive,
        send,
    )
    
    call = send.call_args[0][0]
    assert call["type"] == "websocket.close"
    assert call["code"] == 4000


@pytest.mark.anyio
async def test_guard_env_override():
    """default_ws_guard_config_from_env should read environment variables."""
    os.environ["FISHBRO_ALLOWED_WS_PREFIXES"] = "/custom,/another"
    os.environ["FISHBRO_WS_GUARD_CLOSE_CODE"] = "1234"
    os.environ["FISHBRO_WS_GUARD_LOG_DENIES"] = "1"
    
    try:
        config = default_ws_guard_config_from_env()
        assert set(config.allowed_path_prefixes) == {
            "/_nicegui_ws",
            "/socket.io",
            "/_nicegui",
            "/custom",
            "/another",
        }
        assert config.close_code == 1234
        assert config.log_denies is True
    finally:
        del os.environ["FISHBRO_ALLOWED_WS_PREFIXES"]
        del os.environ["FISHBRO_WS_GUARD_CLOSE_CODE"]
        del os.environ["FISHBRO_WS_GUARD_LOG_DENIES"]


@pytest.mark.anyio
async def test_guard_no_env():
    """default_ws_guard_config_from_env should use defaults when env not set."""
    # Ensure env vars are not set
    os.environ.pop("FISHBRO_ALLOWED_WS_PREFIXES", None)
    os.environ.pop("FISHBRO_WS_GUARD_CLOSE_CODE", None)
    os.environ.pop("FISHBRO_WS_GUARD_LOG_DENIES", None)
    
    config = default_ws_guard_config_from_env()
    assert config.allowed_path_prefixes == ("/_nicegui_ws", "/socket.io", "/_nicegui")
    assert config.close_code == 1008
    assert config.log_denies is False