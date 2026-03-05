"""Tests for WebSocket connection manager."""

from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from ios_gps_spoofer.api.models import WSHeartbeat
from ios_gps_spoofer.api.websocket_manager import (
    HEARTBEAT_TIMEOUT_S,
    WebSocketManager,
)


def _make_mock_websocket() -> MagicMock:
    """Create a mock WebSocket with async methods."""
    ws = MagicMock()
    ws.accept = AsyncMock()
    ws.send_text = AsyncMock()
    ws.close = AsyncMock()
    ws.receive_json = AsyncMock()
    return ws


# ------------------------------------------------------------------
# Connection management
# ------------------------------------------------------------------

class TestConnectionManagement:
    """Tests for connect/disconnect lifecycle."""

    @pytest.mark.asyncio
    async def test_connect_accepts_websocket(self):
        manager = WebSocketManager()
        ws = _make_mock_websocket()
        await manager.connect(ws)
        ws.accept.assert_awaited_once()
        assert manager.connection_count == 1

    @pytest.mark.asyncio
    async def test_connect_multiple(self):
        manager = WebSocketManager()
        ws1 = _make_mock_websocket()
        ws2 = _make_mock_websocket()
        await manager.connect(ws1)
        await manager.connect(ws2)
        assert manager.connection_count == 2

    @pytest.mark.asyncio
    async def test_disconnect_removes_websocket(self):
        manager = WebSocketManager()
        ws = _make_mock_websocket()
        await manager.connect(ws)
        manager.disconnect(ws)
        assert manager.connection_count == 0

    @pytest.mark.asyncio
    async def test_disconnect_unknown_is_safe(self):
        manager = WebSocketManager()
        ws = _make_mock_websocket()
        manager.disconnect(ws)  # should not raise
        assert manager.connection_count == 0

    @pytest.mark.asyncio
    async def test_disconnect_async(self):
        manager = WebSocketManager()
        ws = _make_mock_websocket()
        await manager.connect(ws)
        await manager.disconnect_async(ws)
        assert manager.connection_count == 0


# ------------------------------------------------------------------
# Broadcasting
# ------------------------------------------------------------------

class TestBroadcast:
    """Tests for message broadcasting."""

    @pytest.mark.asyncio
    async def test_broadcast_sends_to_all(self):
        manager = WebSocketManager()
        ws1 = _make_mock_websocket()
        ws2 = _make_mock_websocket()
        await manager.connect(ws1)
        await manager.connect(ws2)

        msg = WSHeartbeat(timestamp=123.0)
        await manager.broadcast(msg)

        ws1.send_text.assert_awaited_once()
        ws2.send_text.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_broadcast_no_connections(self):
        manager = WebSocketManager()
        msg = WSHeartbeat(timestamp=123.0)
        await manager.broadcast(msg)  # should not raise

    @pytest.mark.asyncio
    async def test_broadcast_removes_dead_connections(self):
        manager = WebSocketManager()
        ws_good = _make_mock_websocket()
        ws_dead = _make_mock_websocket()
        ws_dead.send_text = AsyncMock(side_effect=ConnectionError("closed"))

        await manager.connect(ws_good)
        await manager.connect(ws_dead)
        assert manager.connection_count == 2

        msg = WSHeartbeat(timestamp=123.0)
        await manager.broadcast(msg)

        # Dead connection should have been removed
        assert manager.connection_count == 1
        ws_good.send_text.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_broadcast_sends_json(self):
        manager = WebSocketManager()
        ws = _make_mock_websocket()
        await manager.connect(ws)

        msg = WSHeartbeat(timestamp=42.0)
        await manager.broadcast(msg)

        call_args = ws.send_text.call_args[0][0]
        assert '"heartbeat"' in call_args
        assert "42.0" in call_args


# ------------------------------------------------------------------
# Throttling
# ------------------------------------------------------------------

class TestThrottling:
    """Tests for message throttling."""

    @pytest.mark.asyncio
    async def test_first_message_not_throttled(self):
        manager = WebSocketManager(throttle_interval_s=1.0)
        ws = _make_mock_websocket()
        await manager.connect(ws)

        msg = WSHeartbeat(timestamp=1.0)
        sent = await manager.broadcast_throttled(msg, "device-1")
        assert sent is True
        ws.send_text.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_rapid_messages_throttled(self):
        manager = WebSocketManager(throttle_interval_s=1.0)
        ws = _make_mock_websocket()
        await manager.connect(ws)

        msg = WSHeartbeat(timestamp=1.0)
        sent1 = await manager.broadcast_throttled(msg, "device-1")
        sent2 = await manager.broadcast_throttled(msg, "device-1")
        assert sent1 is True
        assert sent2 is False
        # Only one message should have been sent
        assert ws.send_text.await_count == 1

    @pytest.mark.asyncio
    async def test_different_keys_not_throttled(self):
        manager = WebSocketManager(throttle_interval_s=1.0)
        ws = _make_mock_websocket()
        await manager.connect(ws)

        msg = WSHeartbeat(timestamp=1.0)
        sent1 = await manager.broadcast_throttled(msg, "device-1")
        sent2 = await manager.broadcast_throttled(msg, "device-2")
        assert sent1 is True
        assert sent2 is True

    @pytest.mark.asyncio
    async def test_throttle_expires_after_interval(self):
        manager = WebSocketManager(throttle_interval_s=0.05)
        ws = _make_mock_websocket()
        await manager.connect(ws)

        msg = WSHeartbeat(timestamp=1.0)
        sent1 = await manager.broadcast_throttled(msg, "device-1")
        assert sent1 is True

        await asyncio.sleep(0.06)

        sent2 = await manager.broadcast_throttled(msg, "device-1")
        assert sent2 is True
        assert ws.send_text.await_count == 2


# ------------------------------------------------------------------
# Heartbeat
# ------------------------------------------------------------------

class TestHeartbeat:
    """Tests for heartbeat tracking."""

    @pytest.mark.asyncio
    async def test_record_pong(self):
        manager = WebSocketManager()
        ws = _make_mock_websocket()
        await manager.connect(ws)

        # Record a pong
        manager.record_pong(ws)
        # Should not appear in dead list
        dead = await manager.check_heartbeats()
        assert len(dead) == 0

    @pytest.mark.asyncio
    async def test_heartbeat_timeout_detection(self):
        manager = WebSocketManager()
        ws = _make_mock_websocket()
        await manager.connect(ws)

        # Simulate timeout by setting last_pong to far in the past
        manager._last_pong[id(ws)] = time.monotonic() - HEARTBEAT_TIMEOUT_S - 1

        dead = await manager.check_heartbeats()
        assert ws in dead

    @pytest.mark.asyncio
    async def test_send_heartbeat(self):
        manager = WebSocketManager()
        ws = _make_mock_websocket()
        await manager.connect(ws)

        await manager.send_heartbeat()
        ws.send_text.assert_awaited_once()
        call_data = ws.send_text.call_args[0][0]
        assert '"heartbeat"' in call_data

    @pytest.mark.asyncio
    async def test_send_heartbeat_no_connections(self):
        manager = WebSocketManager()
        await manager.send_heartbeat()  # should not raise


# ------------------------------------------------------------------
# Close all
# ------------------------------------------------------------------

class TestCloseAll:
    """Tests for close_all."""

    @pytest.mark.asyncio
    async def test_close_all(self):
        manager = WebSocketManager()
        ws1 = _make_mock_websocket()
        ws2 = _make_mock_websocket()
        await manager.connect(ws1)
        await manager.connect(ws2)

        await manager.close_all()
        assert manager.connection_count == 0
        ws1.close.assert_awaited_once()
        ws2.close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_close_all_handles_errors(self):
        manager = WebSocketManager()
        ws = _make_mock_websocket()
        ws.close = AsyncMock(side_effect=RuntimeError("already closed"))
        await manager.connect(ws)

        await manager.close_all()  # should not raise
        assert manager.connection_count == 0
