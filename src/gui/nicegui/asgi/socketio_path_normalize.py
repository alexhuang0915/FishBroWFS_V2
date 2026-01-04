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
            raw = scope.get("raw_path", None)
            # Debug print
            print(f"[SocketIOPathNormalize] type={t}, path={path}, raw_path={raw}", flush=True)
            if path == "/_nicegui_ws/socket.io":
                print(f"[SocketIOPathNormalize] Normalizing path {path} to include trailing slash", flush=True)
                scope["path"] = "/_nicegui_ws/socket.io/"
                if isinstance(raw, (bytes, bytearray)):
                    # raw_path may include query string, e.g., b"/_nicegui_ws/socket.io?transport=websocket"
                    # We need to add slash before query if path part matches.
                    # Split on b'?' to isolate path part.
                    if raw.startswith(b"/_nicegui_ws/socket.io"):
                        # Check if the path part is exactly b"/_nicegui_ws/socket.io" (no slash)
                        # There may be a query separator '?' or end of bytes.
                        if raw == b"/_nicegui_ws/socket.io":
                            scope["raw_path"] = b"/_nicegui_ws/socket.io/"
                        elif raw.startswith(b"/_nicegui_ws/socket.io?"):
                            # Insert slash before '?'
                            scope["raw_path"] = b"/_nicegui_ws/socket.io/?" + raw.split(b'?', 1)[1]
                        elif raw.startswith(b"/_nicegui_ws/socket.io/"):
                            # Already has slash, do nothing
                            pass
                        else:
                            # Some other variation, ignore
                            pass
        await self.app(scope, receive, send)