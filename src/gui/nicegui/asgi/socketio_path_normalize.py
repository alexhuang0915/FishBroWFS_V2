"""ASGI middleware that normalizes NiceGUI Socket.IO path to include trailing slash.

Fixes:
  - HTTP polling 404 at /_nicegui_ws/socket.io
  - WebSocket ASGI crash when engineio not_found sends http.response.start on websocket scope
"""
from __future__ import annotations
import logging
from typing import Callable, Awaitable, Dict, Any

ASGIApp = Callable[
    [Dict[str, Any], Callable[[], Awaitable[dict]], Callable[[dict], Awaitable[None]]],
    Awaitable[None],
]

logger = logging.getLogger(__name__)


class SocketIOPathNormalizeMiddleware:
    """
    Normalize NiceGUI Socket.IO path to include trailing slash.
    Fixes:
      - HTTP polling 404 at /_nicegui_ws/socket.io
      - WebSocket ASGI crash when engineio not_found sends http.response.start on websocket scope
    """

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Dict[str, Any], receive: Callable, send: Callable) -> None:
        t = scope.get("type")
        if t in ("http", "websocket"):
            path = scope.get("path", "")
            if path == "/_nicegui_ws/socket.io":
                logger.debug("Normalizing path %s to include trailing slash", path)
                scope["path"] = "/_nicegui_ws/socket.io/"
        await self.app(scope, receive, send)