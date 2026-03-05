"""Tests for FastAPI REST API routes.

Uses FastAPI's TestClient for synchronous HTTP testing without needing
a running server.  All backend services (DeviceManager, LocationService)
are mocked.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from ios_gps_spoofer.api.models import (
    FavoriteLocation,
)
from ios_gps_spoofer.api.server import create_app

# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------

@pytest.fixture()
def mock_app_state():
    """Create a mock AppState."""
    state = MagicMock()
    state.device_manager = MagicMock()
    state.location_service = MagicMock()
    state._favorites = []
    state.get_favorites.return_value = []
    state.get_simulator.return_value = None
    state.get_simulator_status.return_value = None
    return state


@pytest.fixture()
def mock_ws_manager():
    """Create a mock WebSocketManager."""
    ws = MagicMock()
    ws.broadcast = AsyncMock()
    ws.broadcast_throttled = AsyncMock(return_value=True)
    ws.connect = AsyncMock()
    ws.disconnect = MagicMock()
    ws.close_all = AsyncMock()
    ws.send_heartbeat = AsyncMock()
    ws.check_heartbeats = AsyncMock(return_value=[])
    ws.connection_count = 0
    return ws


@pytest.fixture()
def client(mock_app_state, mock_ws_manager):
    """Create a TestClient with mocked dependencies."""
    app = create_app()

    with (
        patch("ios_gps_spoofer.api.routes._get_state", return_value=mock_app_state),
        patch("ios_gps_spoofer.api.routes._get_ws_manager", return_value=mock_ws_manager),
        patch("ios_gps_spoofer.api.server._app_state", mock_app_state),
        patch("ios_gps_spoofer.api.server._ws_manager", mock_ws_manager),
        patch("ios_gps_spoofer.api.server._event_loop", asyncio.new_event_loop()),
        TestClient(app, raise_server_exceptions=False) as tc,
    ):
        yield tc


# ------------------------------------------------------------------
# Health check
# ------------------------------------------------------------------

class TestHealthCheck:
    """Tests for the health check endpoint."""

    def test_health_check(self, client):
        resp = client.get("/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["message"] == "OK"


# ------------------------------------------------------------------
# Device endpoints
# ------------------------------------------------------------------

class TestDeviceEndpoints:
    """Tests for device-related endpoints."""

    def test_list_devices_empty(self, client, mock_app_state):
        mock_app_state.device_manager.list_connected_devices.return_value = []
        resp = client.get("/api/devices")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 0
        assert data["devices"] == []

    def test_list_devices_with_device(self, client, mock_app_state):
        device_conn = MagicMock()
        device_conn.to_dict.return_value = {
            "udid": "abc123",
            "name": "iPhone",
            "product_type": "iPhone16,1",
            "product_version": "17.2",
            "build_version": "21C66",
            "device_class": "iPhone",
            "state": "ready",
            "ios_category": "tunnel",
            "is_ready": True,
            "error_message": None,
            "connected_at": "2024-01-01T00:00:00+00:00",
            "last_seen_at": "2024-01-01T00:00:00+00:00",
        }
        mock_app_state.device_manager.list_connected_devices.return_value = [
            device_conn
        ]
        resp = client.get("/api/devices")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 1
        assert data["devices"][0]["udid"] == "abc123"

    def test_get_device_found(self, client, mock_app_state):
        device_conn = MagicMock()
        device_conn.to_dict.return_value = {
            "udid": "abc123",
            "name": "iPhone",
            "product_type": "iPhone16,1",
            "product_version": "17.2",
            "build_version": "21C66",
            "device_class": "iPhone",
            "state": "ready",
            "ios_category": "tunnel",
            "is_ready": True,
            "error_message": None,
            "connected_at": "2024-01-01T00:00:00+00:00",
            "last_seen_at": "2024-01-01T00:00:00+00:00",
        }
        mock_app_state.device_manager.get_device.return_value = device_conn
        resp = client.get("/api/devices/abc123")
        assert resp.status_code == 200
        data = resp.json()
        assert data["udid"] == "abc123"

    def test_get_device_not_found(self, client, mock_app_state):
        from ios_gps_spoofer.device.exceptions import DeviceNotFoundError

        mock_app_state.device_manager.get_device.side_effect = DeviceNotFoundError(
            "xyz"
        )
        resp = client.get("/api/devices/xyz")
        assert resp.status_code == 404
        data = resp.json()
        assert data["success"] is False
        assert "not found" in data["error"].lower()


# ------------------------------------------------------------------
# Location endpoints
# ------------------------------------------------------------------

class TestLocationEndpoints:
    """Tests for location setting/clearing endpoints."""

    def test_set_location_success(self, client, mock_app_state):
        resp = client.post(
            "/api/location/set",
            json={"udid": "d1", "latitude": 25.0, "longitude": 121.5},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        mock_app_state.location_service.set_location.assert_called_once()

    def test_set_location_invalid_coords(self, client):
        resp = client.post(
            "/api/location/set",
            json={"udid": "d1", "latitude": 100.0, "longitude": 121.5},
        )
        assert resp.status_code == 422  # Pydantic validation error

    def test_set_location_missing_udid(self, client):
        resp = client.post(
            "/api/location/set",
            json={"latitude": 25.0, "longitude": 121.5},
        )
        assert resp.status_code == 422

    def test_set_location_device_error(self, client, mock_app_state):
        mock_app_state.location_service.set_location.side_effect = RuntimeError(
            "Device not ready"
        )
        resp = client.post(
            "/api/location/set",
            json={"udid": "d1", "latitude": 25.0, "longitude": 121.5},
        )
        assert resp.status_code == 400
        data = resp.json()
        assert data["success"] is False
        assert "Device not ready" in data["detail"]

    def test_clear_location_success(self, client, mock_app_state):
        mock_app_state.stop_simulator.return_value = False
        resp = client.post(
            "/api/location/clear",
            json={"udid": "d1"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        mock_app_state.location_service.clear_location.assert_called_once()

    def test_get_location_status(self, client, mock_app_state):
        mock_app_state.location_service.get_status.return_value = {
            "udid": "d1",
            "simulation_active": True,
            "current_location": {"latitude": 25.0, "longitude": 121.5},
        }
        resp = client.get("/api/location/d1")
        assert resp.status_code == 200
        data = resp.json()
        assert data["simulation_active"] is True
        assert data["current_location"]["latitude"] == 25.0

    def test_get_location_status_no_location(self, client, mock_app_state):
        mock_app_state.location_service.get_status.return_value = {
            "udid": "d1",
            "simulation_active": False,
            "current_location": None,
        }
        resp = client.get("/api/location/d1")
        assert resp.status_code == 200
        data = resp.json()
        assert data["simulation_active"] is False
        assert data["current_location"] is None


# ------------------------------------------------------------------
# Simulation endpoints
# ------------------------------------------------------------------

class TestSimulationEndpoints:
    """Tests for simulation control endpoints."""

    def test_start_simulation_success(self, client, mock_app_state):
        resp = client.post(
            "/api/simulation/start",
            json={
                "udid": "d1",
                "path": [
                    {"latitude": 25.0, "longitude": 121.5},
                    {"latitude": 25.1, "longitude": 121.6},
                ],
                "speed_kmh": 15.0,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        mock_app_state.register_simulator.assert_called_once()

    def test_start_simulation_single_point_rejected(self, client):
        resp = client.post(
            "/api/simulation/start",
            json={
                "udid": "d1",
                "path": [{"latitude": 25.0, "longitude": 121.5}],
            },
        )
        assert resp.status_code == 422

    def test_pause_simulation_no_active(self, client, mock_app_state):
        mock_app_state.get_simulator.return_value = None
        resp = client.post(
            "/api/simulation/pause",
            json={"udid": "d1"},
        )
        assert resp.status_code == 400
        data = resp.json()
        assert data["success"] is False

    def test_pause_simulation_success(self, client, mock_app_state):
        sim = MagicMock()
        mock_app_state.get_simulator.return_value = sim
        resp = client.post(
            "/api/simulation/pause",
            json={"udid": "d1"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        sim.pause.assert_called_once()

    def test_resume_simulation_success(self, client, mock_app_state):
        sim = MagicMock()
        mock_app_state.get_simulator.return_value = sim
        resp = client.post(
            "/api/simulation/resume",
            json={"udid": "d1"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        sim.resume.assert_called_once()

    def test_stop_simulation_success(self, client, mock_app_state):
        mock_app_state.stop_simulator.return_value = True
        resp = client.post(
            "/api/simulation/stop",
            json={"udid": "d1"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True

    def test_stop_simulation_no_active(self, client, mock_app_state):
        mock_app_state.stop_simulator.return_value = False
        resp = client.post(
            "/api/simulation/stop",
            json={"udid": "d1"},
        )
        assert resp.status_code == 400
        data = resp.json()
        assert data["success"] is False

    def test_set_speed_success(self, client, mock_app_state):
        sim = MagicMock()
        mock_app_state.get_simulator.return_value = sim
        resp = client.post(
            "/api/simulation/speed",
            json={"udid": "d1", "speed_kmh": 30.0},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True

    def test_set_speed_no_simulation(self, client, mock_app_state):
        mock_app_state.get_simulator.return_value = None
        resp = client.post(
            "/api/simulation/speed",
            json={"udid": "d1", "speed_kmh": 30.0},
        )
        assert resp.status_code == 400
        data = resp.json()
        assert data["success"] is False

    def test_get_simulation_status_idle(self, client, mock_app_state):
        mock_app_state.get_simulator_status.return_value = None
        resp = client.get("/api/simulation/d1")
        assert resp.status_code == 200
        data = resp.json()
        assert data["state"] == "idle"

    def test_get_simulation_status_running(self, client, mock_app_state):
        mock_app_state.get_simulator_status.return_value = {
            "udid": "d1",
            "state": "running",
            "speed_kmh": 15.0,
        }
        resp = client.get("/api/simulation/d1")
        assert resp.status_code == 200
        data = resp.json()
        assert data["state"] == "running"


# ------------------------------------------------------------------
# GPX endpoints
# ------------------------------------------------------------------

class TestGPXEndpoints:
    """Tests for GPX parsing endpoint."""

    def test_parse_gpx_success(self, client):
        gpx_content = """<?xml version="1.0"?>
        <gpx version="1.1" xmlns="http://www.topografix.com/GPX/1/1">
          <trk><trkseg>
            <trkpt lat="25.0" lon="121.5"/>
            <trkpt lat="25.1" lon="121.6"/>
          </trkseg></trk>
        </gpx>"""
        resp = client.post(
            "/api/gpx/parse",
            json={"gpx_content": gpx_content},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 2
        assert len(data["waypoints"]) == 2

    def test_parse_gpx_invalid_xml(self, client):
        resp = client.post(
            "/api/gpx/parse",
            json={"gpx_content": "NOT XML AT ALL"},
        )
        assert resp.status_code == 400
        data = resp.json()
        assert data["success"] is False
        assert "GPX parse failed" in data["error"]

    def test_parse_gpx_empty_rejected(self, client):
        resp = client.post(
            "/api/gpx/parse",
            json={"gpx_content": ""},
        )
        assert resp.status_code == 422


# ------------------------------------------------------------------
# Favorites endpoints
# ------------------------------------------------------------------

class TestFavoritesEndpoints:
    """Tests for favorites CRUD endpoints."""

    def test_list_favorites_empty(self, client, mock_app_state):
        mock_app_state.get_favorites.return_value = []
        resp = client.get("/api/favorites")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 0

    def test_list_favorites_with_items(self, client, mock_app_state):
        mock_app_state.get_favorites.return_value = [
            FavoriteLocation(name="Home", latitude=25.0, longitude=121.5),
        ]
        resp = client.get("/api/favorites")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 1
        assert data["favorites"][0]["name"] == "Home"

    def test_add_favorite(self, client, mock_app_state):
        resp = client.post(
            "/api/favorites",
            json={"name": "Office", "latitude": 25.05, "longitude": 121.55},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        mock_app_state.add_favorite.assert_called_once()

    def test_remove_favorite_success(self, client, mock_app_state):
        mock_app_state.remove_favorite.return_value = FavoriteLocation(
            name="Home", latitude=25.0, longitude=121.5
        )
        resp = client.delete("/api/favorites/0")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True

    def test_remove_favorite_not_found(self, client, mock_app_state):
        mock_app_state.remove_favorite.return_value = None
        resp = client.delete("/api/favorites/99")
        assert resp.status_code == 404
        data = resp.json()
        assert data["success"] is False
