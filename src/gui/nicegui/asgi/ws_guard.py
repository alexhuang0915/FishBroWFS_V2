"""ASGI middleware that hard‑locks WebSocket routing.

Prevents `RuntimeError: Expected ASGI message 'websocket.accept'...' but got 'http.response.start'`
by enforcing a hard boundary: WebSocket scopes must never fall through to HTTP not_found routes.
NiceGUI must be the only owner of WS handling, and any non‑NiceGUI WS traffic must be closed
deterministically.
"""
from __future__ import annotations
import os
import logging
from dataclasses import dataclass
from typing import Callable, Awaitable, Optional, Iterable, Any

ASGIApp = Callable[
    [dict, Callable[[], Awaitable[dict]], Callable[[dict], Awaitable[None]]],
    Awaitable[None],
]

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class WebSocketGuardConfig:
    """Configuration for WebSocketGuardMiddleware."""
    allowed_path_prefixes: tuple[str, ...]
    close_code: int = 1008  # Policy violation default
    log_denies: bool = False


class WebSocketGuardMiddleware:
    """ASGI middleware that rejects WebSocket connections on non‑allowed paths.

    Behaviour:
    - If scope.get("type") != "websocket" → pass through
    - Else check path against allowed_path_prefixes
    - If path matches any prefix → pass through
    - Else send {"type": "websocket.close", "code": config.close_code} and return
    """

    def __init__(self, app: ASGIApp, config: WebSocketGuardConfig) -> None:
        self.app = app
        self.config = config

    async def __call__(
        self,
        scope: dict,
        receive: Callable[[], Awaitable[dict]],
        send: Callable[[dict], Awaitable[None]],
    ) -> None:
        if scope.get("type") != "websocket":
            # Not a websocket scope, pass through
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        if any(path.startswith(prefix) for prefix in self.config.allowed_path_prefixes):
            # Allowed WebSocket path, pass through
            await self.app(scope, receive, send)
            return

        # Deny this WebSocket connection
        if self.config.log_denies:
            logger.warning(
                "WebSocketGuard: rejecting WebSocket on path %s (allowed prefixes: %s)",
                path,
                self.config.allowed_path_prefixes,
            )
        # Send close frame and stop processing
        await send({"type": "websocket.close", "code": self.config.close_code})
        # Do NOT call self.app


def default_ws_guard_config_from_env() -> WebSocketGuardConfig:
    """Create a WebSocketGuardConfig with defaults and environment overrides.

    Default allowed prefixes:
    - "/_nicegui_ws"
    - "/socket.io"
    - "/_nicegui"

    Environment variable FISHBRO_ALLOWED_WS_PREFIXES can extend the list
    (comma‑separated, no spaces).
    """
    default_prefixes = ("/_nicegui_ws", "/socket.io", "/_nicegui")
    env_prefixes = os.environ.get("FISHBRO_ALLOWED_WS_PREFIXES", "")
    if env_prefixes:
        extra = tuple(p.strip() for p in env_prefixes.split(",") if p.strip())
        allowed = default_prefixes + extra
    else:
        allowed = default_prefixes

    log_denies = os.environ.get("FISHBRO_WS_GUARD_LOG_DENIES", "0").strip() in ("1", "true", "yes")

    return WebSocketGuardConfig(
        allowed_path_prefixes=allowed,
        close_code=int(os.environ.get("FISHBRO_WS_GUARD_CLOSE_CODE", "1008")),
        log_denies=log_denies,
    )