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
    debug_env: str = "FISHBRO_DEBUG_WS_GUARD"


class WebSocketGuardMiddleware:
    """ASGI middleware that blackholes non‑allowed WebSocket connections.

    Behaviour:
    - If scope.get("type") != "websocket" → pass through
    - If path matches allowed_prefixes → pass through to downstream app
    - Else send {"type": "websocket.accept"} then {"type": "websocket.close", "code": close_code}
      and return immediately, never calling downstream app.
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
        # Debug all scopes when enabled
        if os.getenv(self.config.debug_env) == "1":
            print(f"[WS_GUARD] ENTER scope type={scope.get('type')} path={scope.get('path')}", flush=True)
        
        if scope.get("type") != "websocket":
            # Not a websocket scope, pass through
            await self.app(scope, receive, send)
            return

        root_path = scope.get("root_path") or ""
        path = scope.get("path") or ""
        effective_path = f"{root_path}{path}"
        
        # Normalize path for comparison (strip trailing slash except for root)
        def _normalize(p: str) -> str:
            if p != "/" and p.endswith("/"):
                return p[:-1]
            return p
        
        normalized_effective = _normalize(effective_path)
        allowed = any(
            normalized_effective == _normalize(prefix) or
            normalized_effective.startswith(_normalize(prefix) + "/")
            for prefix in self.config.allowed_path_prefixes
        )

        # Optional debug logging
        if os.getenv(self.config.debug_env) == "1":
            print(f"[WS_GUARD] WS root_path={root_path} path={path} effective_path={effective_path} normalized={normalized_effective} allowed={allowed} prefixes={self.config.allowed_path_prefixes}", flush=True)
            logger.debug(
                "[WS_GUARD] root_path=%s path=%s effective_path=%s normalized=%s allowed=%s prefixes=%s",
                root_path,
                path,
                effective_path,
                normalized_effective,
                allowed,
                self.config.allowed_path_prefixes,
            )

        if allowed:
            # Pass through to downstream app (NiceGUI's socket.io handler)
            await self.app(scope, receive, send)
            return

        # Blackhole non-allowed websocket paths
        if self.config.log_denies:
            logger.warning(
                "WebSocketGuard: blackholing WebSocket on effective path %s (not in allowed prefixes)",
                effective_path,
            )
        # Accept then immediately close (ASGI spec requires accept before close)
        await send({"type": "websocket.accept"})
        await send({"type": "websocket.close", "code": self.config.close_code})
        # Do NOT call self.app


def default_ws_guard_config_from_env() -> WebSocketGuardConfig:
    """Create a WebSocketGuardConfig with defaults and environment overrides.

    Default allowed prefixes (Phase 14.7: precise socket.io path only):
    - "/_nicegui_ws/socket.io"

    Environment variable FISHBRO_ALLOWED_WS_PREFIXES can extend the list
    (comma‑separated, no spaces).
    """
    default_prefixes = ("/_nicegui_ws/socket.io",)
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
        debug_env="FISHBRO_DEBUG_WS_GUARD",
    )