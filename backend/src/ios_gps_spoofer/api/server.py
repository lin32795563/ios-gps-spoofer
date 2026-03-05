"""FastAPI application factory and uvicorn server runner.

Creates the FastAPI app with:
- REST API routes (``/api/*``)
- WebSocket endpoint (``/ws``)
- CORS middleware for Electron frontend
- Lifespan events for startup/shutdown
- Background heartbeat task for WebSocket health monitoring

Usage::

    # As a module:
    python -m ios_gps_spoofer.api.server

    # Programmatically:
    from ios_gps_spoofer.api.server import create_app, run_server
    app = create_app()
    run_server(app)
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ios_gps_spoofer.api.app_state import AppState
from ios_gps_spoofer.api.routes import router
from ios_gps_spoofer.api.websocket_manager import (
    HEARTBEAT_INTERVAL_S,
    WebSocketManager,
)
from ios_gps_spoofer.config import API_HOST, API_PORT, setup_logging

logger = logging.getLogger(__name__)

# Module-level references set during app startup.
# These are accessed by routes via get_app_state() / get_ws_manager().
_app_state: AppState | None = None
_ws_manager: WebSocketManager | None = None
_event_loop: asyncio.AbstractEventLoop | None = None
_heartbeat_task: asyncio.Task | None = None


def get_app_state() -> AppState:
    """Return the current application state.

    Raises:
        RuntimeError: If the app has not been started yet.
    """
    if _app_state is None:
        raise RuntimeError("Application state not initialized. Is the server running?")
    return _app_state


def get_ws_manager() -> WebSocketManager:
    """Return the current WebSocket manager.

    Raises:
        RuntimeError: If the app has not been started yet.
    """
    if _ws_manager is None:
        raise RuntimeError("WebSocket manager not initialized. Is the server running?")
    return _ws_manager


def get_event_loop() -> asyncio.AbstractEventLoop | None:
    """Return the server's asyncio event loop (for scheduling from threads)."""
    return _event_loop


async def _heartbeat_loop() -> None:
    """Background task that sends heartbeats and removes dead connections."""
    assert _ws_manager is not None
    while True:
        try:
            await asyncio.sleep(HEARTBEAT_INTERVAL_S)
            await _ws_manager.send_heartbeat()
            dead = await _ws_manager.check_heartbeats()
            for ws in dead:
                logger.info("Removing dead WebSocket connection (heartbeat timeout)")
                with contextlib.suppress(Exception):
                    await ws.close(code=1001, reason="Heartbeat timeout")
                _ws_manager.disconnect(ws)
        except asyncio.CancelledError:
            break
        except Exception:
            logger.exception("Error in heartbeat loop")


def _setup_device_callbacks(state: AppState, ws_manager: WebSocketManager) -> None:
    """Wire up DeviceManager callbacks to push WebSocket updates.

    Args:
        state: The application state.
        ws_manager: The WebSocket manager for broadcasting.
    """
    from ios_gps_spoofer.api.models import (
        DeviceInfoResponse,
        WSDeviceDisconnected,
        WSDeviceUpdate,
    )

    def on_device_connected(connection):
        """Push device-connected event to WebSocket clients."""
        try:
            device_resp = DeviceInfoResponse(**connection.to_dict())
            msg = WSDeviceUpdate(device=device_resp)
            _schedule_broadcast(ws_manager, msg)
        except Exception:
            logger.exception("Error in device connected callback")

    def on_device_disconnected(connection):
        """Push device-disconnected event to WebSocket clients."""
        try:
            # Stop any running simulation for this device
            state.stop_simulator(connection.udid)
            msg = WSDeviceDisconnected(udid=connection.udid)
            _schedule_broadcast(ws_manager, msg)
        except Exception:
            logger.exception("Error in device disconnected callback")

    def on_state_changed(connection):
        """Push device state change to WebSocket clients."""
        try:
            device_resp = DeviceInfoResponse(**connection.to_dict())
            msg = WSDeviceUpdate(device=device_resp)
            _schedule_broadcast(ws_manager, msg)
        except Exception:
            logger.exception("Error in state changed callback")

    state.device_manager.on_device_connected = on_device_connected
    state.device_manager.on_device_disconnected = on_device_disconnected
    state.device_manager.on_state_changed = on_state_changed


def _schedule_broadcast(ws_manager: WebSocketManager, message) -> None:
    """Schedule a broadcast from a synchronous callback thread.

    Args:
        ws_manager: The WebSocket manager.
        message: The Pydantic model to broadcast.
    """
    loop = _event_loop
    if loop is not None and loop.is_running():
        loop.call_soon_threadsafe(
            asyncio.ensure_future,
            ws_manager.broadcast(message),
        )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan: startup and shutdown logic.

    On startup:
    - Initialize application state and WebSocket manager
    - Start device polling
    - Wire up device callbacks for WebSocket push
    - Start heartbeat background task

    On shutdown:
    - Cancel heartbeat task
    - Stop all simulators
    - Stop device polling
    - Close all WebSocket connections
    """
    global _app_state, _ws_manager, _event_loop, _heartbeat_task

    logger.info("Server starting up...")

    # Capture the event loop for cross-thread scheduling
    _event_loop = asyncio.get_running_loop()

    # Initialize services
    _app_state = AppState()
    _ws_manager = WebSocketManager()

    # Wire device callbacks to WebSocket
    _setup_device_callbacks(_app_state, _ws_manager)

    # Start services
    _app_state.startup()

    # Start heartbeat task
    _heartbeat_task = asyncio.create_task(_heartbeat_loop())

    logger.info("Server startup complete")

    yield

    # Shutdown
    logger.info("Server shutting down...")

    # Cancel heartbeat
    if _heartbeat_task is not None:
        _heartbeat_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await _heartbeat_task

    # Close WebSocket connections
    await _ws_manager.close_all()

    # Shut down application state (stops simulators, device polling)
    _app_state.shutdown()

    # Clear module-level references
    _app_state = None
    _ws_manager = None
    _event_loop = None
    _heartbeat_task = None

    logger.info("Server shutdown complete")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application.

    Returns:
        A fully configured FastAPI app ready to serve.
    """
    app = FastAPI(
        title="iOS GPS Spoofer API",
        version="0.1.0",
        description="Backend API for iOS GPS location simulation",
        lifespan=lifespan,
    )

    # CORS middleware for Electron frontend
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:3000",     # Vite dev server
            "http://localhost:5173",     # Vite default
            "http://127.0.0.1:3000",
            "http://127.0.0.1:5173",
            "app://.",                    # Electron custom protocol
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Mount routes
    app.include_router(router)

    return app


def run_server(
    host: str = API_HOST,
    port: int = API_PORT,
) -> None:
    """Run the server with uvicorn.

    Uses string-based app import (``factory=True``) so that uvicorn
    imports the module by name, avoiding the ``__main__`` vs module
    duality that causes module-level state to be invisible to routes.

    Args:
        host: Host to bind to.
        port: Port to bind to.
    """
    import uvicorn

    setup_logging()
    logger.info("Starting server on %s:%d", host, port)

    uvicorn.run(
        "ios_gps_spoofer.api.server:create_app",
        factory=True,
        host=host,
        port=port,
        log_level="info",
        access_log=False,
    )


# Allow running as: python -m ios_gps_spoofer.api.server
if __name__ == "__main__":
    run_server()
