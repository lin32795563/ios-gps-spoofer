"""WebSocket connection manager with heartbeat and throttled broadcasts.

Manages a set of active WebSocket connections and provides methods for
broadcasting messages to all clients.  Includes:

- Connection lifecycle management (connect/disconnect)
- Heartbeat/ping-pong for connection health monitoring
- Message throttling to avoid overwhelming clients with high-frequency
  simulation progress updates
- JSON serialization of Pydantic models for wire transport

Thread Safety
-------------
All connection mutations are protected by an ``asyncio.Lock`` since
FastAPI WebSocket handlers run on the asyncio event loop.  The broadcast
methods are safe to call from any coroutine on that loop.

Throttling
----------
Simulation progress updates can arrive every 0.01-1.0 seconds per device.
The throttle mechanism ensures at most one progress update per device is
sent within the configured ``throttle_interval_s`` window (default 0.1s).
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time

from fastapi import WebSocket
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# Default throttle interval for simulation progress updates
DEFAULT_THROTTLE_INTERVAL_S = 0.1

# Heartbeat interval (seconds)
HEARTBEAT_INTERVAL_S = 15.0

# Maximum time without a pong before considering the connection dead
HEARTBEAT_TIMEOUT_S = 45.0


class WebSocketManager:
    """Manages active WebSocket connections with heartbeat and throttling.

    Usage::

        manager = WebSocketManager()

        # In a WebSocket endpoint:
        await manager.connect(websocket)
        try:
            while True:
                data = await websocket.receive_text()
                # handle client messages...
        except WebSocketDisconnect:
            manager.disconnect(websocket)

        # Broadcasting from device callbacks:
        await manager.broadcast(some_pydantic_model)
    """

    def __init__(
        self,
        throttle_interval_s: float = DEFAULT_THROTTLE_INTERVAL_S,
    ) -> None:
        """Initialize the WebSocket manager.

        Args:
            throttle_interval_s: Minimum interval between progress
                updates for the same device (in seconds).
        """
        self._connections: list[WebSocket] = []
        self._lock = asyncio.Lock()
        self._throttle_interval_s = throttle_interval_s

        # Throttle state: {udid: last_send_time}
        self._last_progress_send: dict[str, float] = {}

        # Heartbeat tracking: {websocket_id: last_pong_time}
        self._last_pong: dict[int, float] = {}

    @property
    def connection_count(self) -> int:
        """Number of active WebSocket connections."""
        return len(self._connections)

    async def connect(self, websocket: WebSocket) -> None:
        """Accept a new WebSocket connection.

        Args:
            websocket: The FastAPI WebSocket instance.
        """
        await websocket.accept()
        async with self._lock:
            self._connections.append(websocket)
            self._last_pong[id(websocket)] = time.monotonic()
        logger.info(
            "WebSocket connected (total: %d)", len(self._connections)
        )

    def disconnect(self, websocket: WebSocket) -> None:
        """Remove a WebSocket connection (synchronous).

        Safe to call even if the websocket is not in the list.

        Args:
            websocket: The WebSocket to remove.
        """
        with contextlib.suppress(ValueError):
            self._connections.remove(websocket)
        self._last_pong.pop(id(websocket), None)
        logger.info(
            "WebSocket disconnected (total: %d)", len(self._connections)
        )

    async def disconnect_async(self, websocket: WebSocket) -> None:
        """Remove a WebSocket connection (async, lock-safe).

        Args:
            websocket: The WebSocket to remove.
        """
        async with self._lock:
            with contextlib.suppress(ValueError):
                self._connections.remove(websocket)
            self._last_pong.pop(id(websocket), None)
        logger.info(
            "WebSocket disconnected (total: %d)", len(self._connections)
        )

    async def broadcast(self, message: BaseModel) -> None:
        """Send a Pydantic model as JSON to all connected clients.

        Connections that fail to receive the message are silently
        removed.

        Args:
            message: A Pydantic BaseModel to serialize and send.
        """
        if not self._connections:
            return

        data = message.model_dump_json()
        dead_connections: list[WebSocket] = []

        async with self._lock:
            for ws in self._connections:
                try:
                    await ws.send_text(data)
                except Exception:
                    dead_connections.append(ws)

            for ws in dead_connections:
                with contextlib.suppress(ValueError):
                    self._connections.remove(ws)
                self._last_pong.pop(id(ws), None)

        if dead_connections:
            logger.debug(
                "Removed %d dead connections during broadcast",
                len(dead_connections),
            )

    async def broadcast_throttled(
        self,
        message: BaseModel,
        throttle_key: str,
    ) -> bool:
        """Send a message, throttled by key (e.g., device UDID).

        If a message with the same throttle_key was sent within the
        throttle interval, this message is silently dropped.

        Args:
            message: A Pydantic BaseModel to serialize and send.
            throttle_key: Key for throttling (usually device UDID).

        Returns:
            True if the message was sent, False if throttled.
        """
        now = time.monotonic()
        last_send = self._last_progress_send.get(throttle_key, 0.0)

        if now - last_send < self._throttle_interval_s:
            return False

        self._last_progress_send[throttle_key] = now
        await self.broadcast(message)
        return True

    def record_pong(self, websocket: WebSocket) -> None:
        """Record that a pong was received from a client.

        Args:
            websocket: The WebSocket that sent the pong.
        """
        self._last_pong[id(websocket)] = time.monotonic()

    async def check_heartbeats(self) -> list[WebSocket]:
        """Check for connections that have not responded to heartbeats.

        Returns:
            List of WebSocket connections that are considered dead
            (no pong within HEARTBEAT_TIMEOUT_S).
        """
        now = time.monotonic()
        dead: list[WebSocket] = []

        async with self._lock:
            for ws in self._connections:
                last_pong = self._last_pong.get(id(ws), 0.0)
                if now - last_pong > HEARTBEAT_TIMEOUT_S:
                    dead.append(ws)

        return dead

    async def send_heartbeat(self) -> None:
        """Send a heartbeat ping to all connected clients.

        Clients should respond with a pong message.  Connections that
        fail to send are cleaned up.
        """
        if not self._connections:
            return

        from ios_gps_spoofer.api.models import WSHeartbeat

        heartbeat = WSHeartbeat(timestamp=time.time())
        await self.broadcast(heartbeat)

    async def close_all(self) -> None:
        """Close all active WebSocket connections gracefully."""
        async with self._lock:
            for ws in list(self._connections):
                with contextlib.suppress(Exception):
                    await ws.close()
            self._connections.clear()
            self._last_pong.clear()
            self._last_progress_send.clear()
        logger.info("All WebSocket connections closed")
