"""Unit tests for SocketIOPathNormalizeMiddleware."""
import pytest
from unittest.mock import AsyncMock

from src.gui.nicegui.asgi.socketio_path_normalize import SocketIOPathNormalizeMiddleware


@pytest.mark.asyncio
async def test_normalize_http_path():
    """SocketIOPathNormalizeMiddleware should add trailing slash to /_nicegui_ws/socket.io for HTTP."""
    seen = {}
    async def app(scope, receive, send):
        seen["path"] = scope["path"]
    mw = SocketIOPathNormalizeMiddleware(app)

    scope = {"type": "http", "path": "/_nicegui_ws/socket.io"}
    async def receive(): return {"type": "http.request"}
    async def send(msg): pass

    await mw(scope, receive, send)
    assert seen["path"] == "/_nicegui_ws/socket.io/"


@pytest.mark.asyncio
async def test_normalize_websocket_path():
    """SocketIOPathNormalizeMiddleware should add trailing slash to /_nicegui_ws/socket.io for WebSocket."""
    seen = {}
    async def app(scope, receive, send):
        seen["path"] = scope["path"]
    mw = SocketIOPathNormalizeMiddleware(app)

    scope = {"type": "websocket", "path": "/_nicegui_ws/socket.io"}
    async def receive(): return {"type": "websocket.connect"}
    async def send(msg): pass

    await mw(scope, receive, send)
    assert seen["path"] == "/_nicegui_ws/socket.io/"


@pytest.mark.asyncio
async def test_no_change_for_other_paths():
    """SocketIOPathNormalizeMiddleware should not modify other paths."""
    seen = {}
    async def app(scope, receive, send):
        seen["path"] = scope["path"]
    mw = SocketIOPathNormalizeMiddleware(app)

    scope = {"type": "http", "path": "/_nicegui_ws/socket.io/"}  # already has slash
    async def receive(): return {"type": "http.request"}
    async def send(msg): pass

    await mw(scope, receive, send)
    assert seen["path"] == "/_nicegui_ws/socket.io/"

    # Different path
    scope = {"type": "http", "path": "/health"}
    await mw(scope, receive, send)
    assert seen["path"] == "/health"


@pytest.mark.asyncio
async def test_no_change_for_other_scope_types():
    """SocketIOPathNormalizeMiddleware should ignore non-http/non-websocket scopes."""
    seen = {}
    async def app(scope, receive, send):
        seen["path"] = scope.get("path")
    mw = SocketIOPathNormalizeMiddleware(app)

    scope = {"type": "lifespan", "path": "/_nicegui_ws/socket.io"}
    async def receive(): return {"type": "lifespan.startup"}
    async def send(msg): pass

    await mw(scope, receive, send)
    assert seen["path"] == "/_nicegui_ws/socket.io"  # unchanged


if __name__ == "__main__":
    # Quick manual test
    import asyncio
    asyncio.run(test_normalize_http_path())
    asyncio.run(test_normalize_websocket_path())
    print("All tests passed (manual run)")