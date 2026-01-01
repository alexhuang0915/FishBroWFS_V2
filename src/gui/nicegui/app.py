"""UI root / app shell for Nexus UI.

Responsibilities:
- Apply Nexus Theme once
- Render Global Header
- Render Primary Tab Bar (filtered by UI capabilities)
- Render active page content
"""
import logging
import os
from typing import Optional

from fastapi import FastAPI
from nicegui import ui
from starlette.types import Scope, Receive, Send

from .theme.nexus_theme import apply_nexus_theme
from .layout.header import render_header
from .layout.tabs import render_tab_bar, TAB_IDS, get_tab_content
from .layout.toasts import init_toast_system
from .services.status_service import start_polling
from .constitution.ui_constitution import apply_ui_constitution, UIConstitutionConfig
from .asgi.ws_guard import WebSocketGuardMiddleware, default_ws_guard_config_from_env, ASGIApp
# Hidden forensic page (requires import to register the route)
from .pages import forensics

logger = logging.getLogger(__name__)


class SocketIOPathAdapterMiddleware:
    """
    Governance-Grade ASGI Adapter.
    
    Problem: When mounting Socket.IO under a subpath (e.g., /_nicegui_ws),
    upstream routers may fail to strip the prefix correctly, causing
    Socket.IO to receive '/_nicegui_ws/socket.io' instead of '/socket.io'.
    
    Solution: This middleware explicitly ensures the scope['path'] matches
    what Socket.IO expects, decoupling us from upstream routing behavior.
    """
    def __init__(self, app: ASGIApp, prefix: str):
        self.app = app
        self.prefix = prefix

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] in ("http", "websocket"):
            path = scope.get("path", "")
            if path.startswith(self.prefix):
                # Explicitly strip the prefix
                new_path = path[len(self.prefix):]
                # Ensure path starts with '/'
                if not new_path.startswith("/"):
                    new_path = "/" + new_path
                # Remove any double slashes (should not happen)
                new_path = new_path.replace("//", "/")
                scope["path"] = new_path
                # Standard ASGI behavior: append stripped part to root_path
                scope["root_path"] = scope.get("root_path", "") + self.prefix
        await self.app(scope, receive, send)


class SocketIOProbeMiddleware:
    """ASGI middleware that logs scope details for Socket.IO traffic."""
    
    def __init__(self, app: ASGIApp):
        self.app = app
    
    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        # Only log HTTP and WebSocket requests
        if scope["type"] in ("http", "websocket"):
            path = scope.get("path", "")
            root_path = scope.get("root_path", "")
            raw_path = scope.get("raw_path", b"")
            # If path starts with /_nicegui_ws, log details
            if path.startswith("/_nicegui_ws"):
                import time
                import json
                import os
                log_entry = {
                    "timestamp": time.time(),
                    "type": scope["type"],
                    "path": path,
                    "root_path": root_path,
                    "raw_path": raw_path.decode("utf-8") if isinstance(raw_path, bytes) else raw_path,
                    "query_string": scope.get("query_string", b"").decode("utf-8"),
                    "headers": [(k.decode("utf-8"), v.decode("utf-8")) for k, v in scope.get("headers", [])],
                }
                log_line = json.dumps(log_entry)
                # Ensure directory exists
                os.makedirs("outputs/_dp_evidence", exist_ok=True)
                with open("outputs/_dp_evidence/socketio_probe.log", "a") as f:
                    f.write(log_line + "\n")
                logger.debug("SocketIOProbe: %s", log_line)
            # Also log any request containing "socket.io" for debugging
            elif "socket.io" in path:
                import time
                import json
                import os
                log_entry = {
                    "timestamp": time.time(),
                    "type": scope["type"],
                    "path": path,
                    "root_path": root_path,
                    "raw_path": raw_path.decode("utf-8") if isinstance(raw_path, bytes) else raw_path,
                    "query_string": scope.get("query_string", b"").decode("utf-8"),
                    "headers": [(k.decode("utf-8"), v.decode("utf-8")) for k, v in scope.get("headers", [])],
                }
                log_line = json.dumps(log_entry)
                os.makedirs("outputs/_dp_evidence", exist_ok=True)
                with open("outputs/_dp_evidence/socketio_probe.log", "a") as f:
                    f.write("DEBUG: " + log_line + "\n")
                logger.debug("SocketIOProbe DEBUG: %s", log_line)
        # Continue processing
        await self.app(scope, receive, send)


# Global app state
_current_tab: Optional[str] = None
_tab_panels: Optional[ui.tab_panels] = None
_SHELL_BUILT: bool = False
_SHELL_BUILD_COUNT: int = 0

# Bootstrap guard
_UI_BOOTSTRAPPED: bool = False
_BOOTSTRAP_COUNT: int = 0


def _on_tab_change(tab_id: str) -> None:
    """Handle tab switching."""
    global _current_tab
    logger.debug(f"Tab changed to {tab_id}")
    _current_tab = tab_id
    if _tab_panels:
        _tab_panels.value = tab_id
    # Optionally load page content dynamically
    # For now, content is pre-rendered in tab panels


def bootstrap_app_shell_and_services() -> None:
    """Bootstrap UI constitution, theme, shell, and polling exactly once per process."""
    global _BOOTSTRAP_COUNT
    if _BOOTSTRAP_COUNT > 0:
        logger.debug("UI already bootstrapped, skipping bootstrap")
        return
    _BOOTSTRAP_COUNT += 1
    logger.debug("Starting UI bootstrap with constitution (count = %d)", _BOOTSTRAP_COUNT)
    
    # Apply UI Constitution FIRST (guarantees dark theme coverage, page wrapper invariants, etc.)
    constitution_config = UIConstitutionConfig(
        enforce_dark_root=True,
        enforce_page_shell=True,
        enforce_truth_providers=True,
        enforce_evidence=True,
    )
    apply_ui_constitution(constitution_config)
    
    # Then apply theme (which now includes constitution-enhanced CSS)
    apply_nexus_theme(use_tailwind=False)
    
    # Create app shell (which will use constitution-wrapped pages)
    create_app_shell()
    
    # Start polling for status updates
    start_polling()
    
    logger.info("UI Constitution applied successfully with all guarantees")


def create_app_shell() -> None:
    """Create the main app shell with header, tabs, and content area.
    
    This function should be called after ui.run() setup.
    """
    global _tab_panels, _SHELL_BUILT, _SHELL_BUILD_COUNT
    if _SHELL_BUILT:
        logger.debug("App shell already built, skipping")
        return
    _SHELL_BUILD_COUNT += 1
    logger.info("App shell created (pid=%d, call #%d)", os.getpid(), _SHELL_BUILD_COUNT)
    
    # Initialize toast system
    init_toast_system()
    
    # Global Header (top‑level, no container)
    render_header()
    
    # Main content area (everything below header)
    with ui.column().classes("w-full h-full min-h-screen bg-nexus-primary"):
        # Primary Tab Bar (filtered by capabilities)
        if TAB_IDS:
            initial_tab = TAB_IDS[0]
            tab_bar = render_tab_bar(value=initial_tab, on_change=_on_tab_change)
            
            # Tab content area
            with ui.tab_panels(tab_bar, value=initial_tab).classes("w-full flex-grow") as panels:
                _tab_panels = panels
                for tab_id in TAB_IDS:
                    with ui.tab_panel(tab_id):
                        # Each page is responsible for its own content
                        get_tab_content(tab_id)
        else:
            # No tabs enabled - show a message
            with ui.column().classes("w-full h-full p-8 items-center justify-center"):
                ui.icon("warning").classes("text-6xl text-warning mb-4")
                ui.label("No UI tabs available").classes("text-xl font-bold mb-2")
                ui.label("All UI capabilities are disabled. Check UI configuration.").classes("text-tertiary")
        
        # Footer (optional)
        with ui.row().classes("w-full py-2 px-4 text-center text-tertiary text-sm border-t border-panel-dark"):
            ui.label("Nexus UI · Single-Human System · Machine Must Not Make Mistakes")
    
    _SHELL_BUILT = True


def _apply_socketio_adapter():
    """
    Apply SocketIOPathAdapterMiddleware to the Socket.IO mount inside NiceGUI's core app.
    This ensures the prefix stripping happens before the Socket.IO ASGI app receives the request.
    """
    import nicegui.core
    from starlette.routing import Mount
    
    # Find the Mount route with path '/_nicegui_ws' (no trailing slash)
    for route in nicegui.core.app.routes:
        if isinstance(route, Mount) and route.path == '/_nicegui_ws':
            logger.debug("Found Socket.IO mount at %s, wrapping with adapter", route.path)
            # Wrap the original app with our adapter
            original_app = route.app
            wrapped_app = SocketIOPathAdapterMiddleware(original_app, prefix="/_nicegui_ws")
            # Replace the app attribute (requires mutable route)
            # Mount's app is a property, but we can hack by replacing the private attribute.
            # Since Mount is a simple class, we can just replace the whole route? Not possible.
            # Instead, we'll monkey-patch the route's __call__ method.
            # Simpler: replace route.app with wrapped_app (if attribute is writable)
            # Let's check if route.app is writable.
            try:
                route.app = wrapped_app
                logger.debug("Successfully wrapped Socket.IO mount with adapter")
                return
            except AttributeError:
                logger.warning("Could not replace route.app, falling back to monkey-patch")
                # Fallback: replace the route's __call__ method
                original_call = route.__call__
                async def wrapped_call(scope, receive, send):
                    # Apply adapter logic inline
                    if scope["type"] in ("http", "websocket"):
                        path = scope.get("path", "")
                        if path.startswith("/_nicegui_ws"):
                            new_path = path[len("/_nicegui_ws"):]
                            if not new_path.startswith("/"):
                                new_path = "/" + new_path
                            scope["path"] = new_path
                            scope["root_path"] = scope.get("root_path", "") + "/_nicegui_ws"
                    await original_call(scope, receive, send)
                route.__call__ = wrapped_call
                logger.debug("Applied adapter via monkey-patch")
                return
    logger.warning("Socket.IO mount not found in nicegui.core.app.routes")


def build_ui_fastapi_app() -> FastAPI:
    """Build the FastAPI app used by the UI server, with middleware and NiceGUI mounted.
    
    This function does NOT bootstrap the UI shell or start polling; it only creates the
    ASGI application. Useful for route inspection and testing.
    """
    # Create FastAPI app
    app = FastAPI(title="FishBro War Room")
    
    # Add health endpoints for monitoring
    @app.get("/health")
    def health():
        return {"status": "ok", "service": "FishBro War Room"}
    
    @app.get("/api/status")
    def status():
        return {"status": "ok", "service": "FishBro War Room"}
    
    # Add Socket.IO probe middleware (diagnostic)
    app.add_middleware(SocketIOProbeMiddleware)

    # Add WebSocket guard middleware FIRST
    guard_config = default_ws_guard_config_from_env()
    app.add_middleware(WebSocketGuardMiddleware, config=guard_config)

    # Apply adapter to Socket.IO mount before mounting NiceGUI
    _apply_socketio_adapter()

    # Mount NiceGUI onto the FastAPI app
    # This ensures NiceGUI registers its Socket.IO routes at /_nicegui_ws/socket.io
    ui.run_with(
        app,
        title="FishBro War Room",
        favicon="🚀",
        dark=True,
        reconnect_timeout=10.0,
    )
    
    logger.debug("Socket.IO routes should be mounted at /_nicegui_ws/socket.io")
    return app


def start_ui(host: str = "0.0.0.0", port: int = 8080, show: bool = True) -> None:
    """Start the Nexus UI server.
    
    Args:
        host: Host to bind.
        port: Port to bind.
        show: Whether to open browser window.
    """
    global _UI_BOOTSTRAPPED
    if _UI_BOOTSTRAPPED:
        logger.warning("UI already bootstrapped, start_ui called again. Ignoring.")
        return
    _UI_BOOTSTRAPPED = True  # guard as early as possible

    # Ensure deterministic single-process mode
    os.environ["WATCHFILES_RELOAD"] = "0"

    # 1) Build FastAPI app FIRST (this calls ui.run_with and mounts NiceGUI internals)
    app = build_ui_fastapi_app()

    # 2) Bootstrap UI shell/services AFTER ui.run_with has mounted NiceGUI onto FastAPI
    bootstrap_app_shell_and_services()

    # Import uvicorn here to avoid extra dependency for CLI usage
    import uvicorn
    
    # Run the app with middleware
    uvicorn.run(
        app,
        host=host,
        port=port,
        log_level="warning",
        reload=False,
    )