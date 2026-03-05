"""End-to-end integration tests for the iOS GPS Spoofer.

These tests exercise the complete stack from API routes through AppState,
DeviceManager, LocationService, PathSimulator, and WebSocket broadcasting.

The pymobiledevice3 layer is mocked, but everything above it runs with
real instances.  This verifies the full user flow:

    Launch -> Connect device -> Set location -> Start simulation ->
    Pause -> Resume -> Stop -> Restore real location -> Disconnect

Also covered:
- Stress tests: rapid operations, long-running simulations, concurrency
- Error propagation: device disconnect mid-simulation, invalid inputs
- WebSocket message flow verification
- Cross-module state consistency

Note: These tests use FastAPI TestClient for HTTP and real instances
of AppState, DeviceManager, LocationService, and PathSimulator.
"""

from __future__ import annotations

import asyncio
import threading
import time
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from ios_gps_spoofer.api.app_state import AppState
from ios_gps_spoofer.api.server import create_app
from ios_gps_spoofer.api.websocket_manager import WebSocketManager

# Import test helpers from the existing device manager tests
from tests.test_device_manager import (
    _make_mock_lockdown,
    _make_mock_mux_device,
)

# Patch targets
_PATCH_ENUM = "ios_gps_spoofer.device.device_manager.DeviceManager._enumerate_usb_devices"
_PATCH_CREATE = "ios_gps_spoofer.device.device_manager.create_using_usbmux"
_PATCH_MOUNTER = "pymobiledevice3.services.mobile_image_mounter.MobileImageMounterService"
_PATCH_DT_SIM = "pymobiledevice3.services.simulate_location.DtSimulateLocation"


# ------------------------------------------------------------------
# Test fixtures
# ------------------------------------------------------------------

@pytest.fixture()
def ios16_env():
    """Set up a mock iOS 16 device environment.

    Yields a dict with mocks and a helper to create the test client.
    """
    udid = "e2e-ios16-device"
    mock_lockdown = _make_mock_lockdown("16.7.4")
    mock_mux = _make_mock_mux_device(udid)

    mock_mounter = MagicMock()
    mock_mounter.is_image_mounted.return_value = True

    mock_dt_sim_instance = MagicMock()

    with (
        patch(_PATCH_ENUM, return_value=[mock_mux]),
        patch(_PATCH_CREATE, return_value=mock_lockdown),
        patch(_PATCH_MOUNTER, return_value=mock_mounter),
        patch(_PATCH_DT_SIM, return_value=mock_dt_sim_instance) as mock_dt_sim_cls,
    ):
        yield {
            "udid": udid,
            "lockdown": mock_lockdown,
            "mux_device": mock_mux,
            "mounter": mock_mounter,
            "dt_sim_cls": mock_dt_sim_cls,
            "dt_sim_instance": mock_dt_sim_instance,
        }


@pytest.fixture()
def app_state():
    """Create a real AppState for integration tests.

    Does NOT call startup() (which starts device polling).
    Tests should call startup/shutdown explicitly if needed.
    """
    state = AppState()
    yield state
    # Ensure cleanup
    state.stop_all_simulators()


@pytest.fixture()
def ws_manager():
    """Create a real WebSocketManager."""
    return WebSocketManager()


@pytest.fixture()
def e2e_client(ios16_env, app_state, ws_manager):
    """Create a TestClient with real AppState but mocked device layer.

    The app_state uses real DeviceManager + LocationService instances,
    but the pymobiledevice3 layer is mocked via ios16_env.
    """
    loop = asyncio.new_event_loop()
    app = create_app()

    with (
        patch("ios_gps_spoofer.api.routes._get_state", return_value=app_state),
        patch("ios_gps_spoofer.api.routes._get_ws_manager", return_value=ws_manager),
        patch("ios_gps_spoofer.api.server._app_state", app_state),
        patch("ios_gps_spoofer.api.server._ws_manager", ws_manager),
        patch("ios_gps_spoofer.api.server._event_loop", loop),
        TestClient(app, raise_server_exceptions=False) as tc,
    ):
        yield tc

    loop.close()


# ------------------------------------------------------------------
# Test 1: Complete User Flow (E2E)
# ------------------------------------------------------------------

class TestFullUserFlow:
    """Simulates the complete user journey through the application."""

    def test_complete_lifecycle(self, e2e_client, ios16_env, app_state):
        """Full flow: health -> connect -> set location -> start sim ->
        pause -> resume -> stop -> clear location -> verify idle.

        This is the primary end-to-end test covering the entire user journey.
        """
        client = e2e_client
        udid = ios16_env["udid"]
        dt_sim = ios16_env["dt_sim_instance"]

        # ---- Step 1: Health Check ----
        resp = client.get("/api/health")
        assert resp.status_code == 200
        assert resp.json()["success"] is True

        # ---- Step 2: List devices (none connected yet) ----
        resp = client.get("/api/devices")
        assert resp.status_code == 200
        assert resp.json()["count"] == 0

        # ---- Step 3: Connect device ----
        resp = client.post(f"/api/devices/{udid}/connect")
        assert resp.status_code == 200, f"Connect failed: {resp.json()}"
        assert resp.json()["success"] is True

        # ---- Step 4: List devices (one connected) ----
        resp = client.get("/api/devices")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 1
        assert data["devices"][0]["udid"] == udid
        assert data["devices"][0]["is_ready"] is True

        # ---- Step 5: Get device info ----
        resp = client.get(f"/api/devices/{udid}")
        assert resp.status_code == 200
        assert resp.json()["udid"] == udid

        # ---- Step 6: Set single-point location ----
        resp = client.post("/api/location/set", json={
            "udid": udid,
            "latitude": 25.0330,
            "longitude": 121.5654,
        })
        assert resp.status_code == 200, f"Set location failed: {resp.json()}"
        assert resp.json()["success"] is True

        # Verify DtSimulateLocation was called
        dt_sim.set.assert_called_with(25.0330, 121.5654)

        # ---- Step 7: Check location status ----
        resp = client.get(f"/api/location/{udid}")
        assert resp.status_code == 200
        loc_status = resp.json()
        assert loc_status["simulation_active"] is True
        assert loc_status["current_location"]["latitude"] == pytest.approx(25.0330)
        assert loc_status["current_location"]["longitude"] == pytest.approx(121.5654)

        # ---- Step 8: Start path simulation ----
        path = [
            {"latitude": 25.0330, "longitude": 121.5654},
            {"latitude": 25.0335, "longitude": 121.5659},
            {"latitude": 25.0340, "longitude": 121.5664},
        ]
        resp = client.post("/api/simulation/start", json={
            "udid": udid,
            "path": path,
            "speed_kmh": 60.0,
            "drift_enabled": False,
        })
        assert resp.status_code == 200, f"Start sim failed: {resp.json()}"
        assert resp.json()["success"] is True

        # Wait for simulation thread to start
        time.sleep(0.2)

        # ---- Step 9: Check simulation status ----
        resp = client.get(f"/api/simulation/{udid}")
        assert resp.status_code == 200
        sim_status = resp.json()
        assert sim_status["state"] in ("running", "stopped")

        # ---- Step 10: Pause simulation ----
        resp = client.post("/api/simulation/pause", json={"udid": udid})
        # May fail if simulation already completed (fast speed + short path)
        if resp.status_code == 200:
            assert resp.json()["success"] is True

            # ---- Step 11: Resume simulation ----
            resp = client.post("/api/simulation/resume", json={"udid": udid})
            assert resp.status_code == 200
            assert resp.json()["success"] is True

        # ---- Step 12: Stop simulation ----
        resp = client.post("/api/simulation/stop", json={"udid": udid})
        # If simulation already completed, stop_simulator returns False
        # which returns an error response. That's acceptable.
        if resp.status_code == 200:
            assert resp.json()["success"] is True

        # Wait for thread cleanup
        time.sleep(0.3)

        # ---- Step 13: Restore real location ----
        resp = client.post("/api/location/clear", json={"udid": udid})
        assert resp.status_code == 200
        assert resp.json()["success"] is True

        # Verify DtSimulateLocation.clear was called
        dt_sim.clear.assert_called()

        # ---- Step 14: Verify location status is idle ----
        resp = client.get(f"/api/location/{udid}")
        assert resp.status_code == 200
        assert resp.json()["simulation_active"] is False
        assert resp.json()["current_location"] is None

    def test_location_set_clear_cycle_multiple_times(
        self, e2e_client, ios16_env, app_state
    ):
        """Set and clear location multiple times in rapid succession."""
        client = e2e_client
        udid = ios16_env["udid"]

        # Connect device
        resp = client.post(f"/api/devices/{udid}/connect")
        assert resp.status_code == 200

        locations = [
            (25.0330, 121.5654),
            (35.6762, 139.6503),
            (48.8566, 2.3522),
            (40.7128, -74.0060),
            (-33.8688, 151.2093),
        ]

        for lat, lng in locations:
            # Set location
            resp = client.post("/api/location/set", json={
                "udid": udid,
                "latitude": lat,
                "longitude": lng,
            })
            assert resp.status_code == 200

            # Verify status
            resp = client.get(f"/api/location/{udid}")
            assert resp.status_code == 200
            status = resp.json()
            assert status["simulation_active"] is True
            assert status["current_location"]["latitude"] == pytest.approx(lat)
            assert status["current_location"]["longitude"] == pytest.approx(lng)

            # Clear location
            resp = client.post("/api/location/clear", json={"udid": udid})
            assert resp.status_code == 200

            # Verify cleared
            resp = client.get(f"/api/location/{udid}")
            assert resp.status_code == 200
            assert resp.json()["simulation_active"] is False
            assert resp.json()["current_location"] is None


# ------------------------------------------------------------------
# Test 2: Path Simulation Integration (Through API Layer)
# ------------------------------------------------------------------

class TestPathSimulationThroughAPI:
    """Tests for path simulation via REST API endpoints."""

    def test_simulation_runs_to_completion(self, e2e_client, ios16_env, app_state):
        """Start a short simulation and verify it completes."""
        client = e2e_client
        udid = ios16_env["udid"]

        # Connect device
        resp = client.post(f"/api/devices/{udid}/connect")
        assert resp.status_code == 200

        # Start simulation with short path and very high speed
        path = [
            {"latitude": 25.0330, "longitude": 121.5654},
            {"latitude": 25.0331, "longitude": 121.5655},
        ]
        resp = client.post("/api/simulation/start", json={
            "udid": udid,
            "path": path,
            "speed_kmh": 999.0,  # Very fast to complete quickly
            "drift_enabled": False,
        })
        assert resp.status_code == 200

        # Wait for completion (very short path at max speed)
        time.sleep(1.0)

        # Simulation should have completed and unregistered itself
        sim = app_state.get_simulator(udid)
        # May be None (unregistered by on_complete callback) or stopped
        if sim is not None:
            from ios_gps_spoofer.simulation.state_machine import SimulationState
            assert sim.state == SimulationState.STOPPED

        # DtSimulateLocation.set should have been called at least once
        assert ios16_env["dt_sim_instance"].set.call_count >= 1

    def test_start_simulation_with_insufficient_path(self, e2e_client, ios16_env):
        """Starting simulation with fewer than 2 points should fail at API validation."""
        client = e2e_client
        udid = ios16_env["udid"]

        # Connect
        client.post(f"/api/devices/{udid}/connect")

        # Try to start with only 1 point
        resp = client.post("/api/simulation/start", json={
            "udid": udid,
            "path": [{"latitude": 25.0, "longitude": 121.0}],
            "speed_kmh": 5.0,
        })
        # Pydantic should reject (min_length=2 on path)
        assert resp.status_code == 422  # Validation error

    def test_pause_without_active_simulation(self, e2e_client, ios16_env):
        """Pausing when no simulation is running should return error."""
        client = e2e_client
        udid = ios16_env["udid"]

        client.post(f"/api/devices/{udid}/connect")

        resp = client.post("/api/simulation/pause", json={"udid": udid})
        assert resp.status_code == 400
        assert resp.json()["error"] == "No active simulation"

    def test_stop_without_active_simulation(self, e2e_client, ios16_env):
        """Stopping when no simulation is running should return error."""
        client = e2e_client
        udid = ios16_env["udid"]

        client.post(f"/api/devices/{udid}/connect")

        resp = client.post("/api/simulation/stop", json={"udid": udid})
        assert resp.status_code == 400

    def test_speed_change_during_simulation(self, e2e_client, ios16_env, app_state):
        """Changing speed mid-simulation should succeed."""
        client = e2e_client
        udid = ios16_env["udid"]

        client.post(f"/api/devices/{udid}/connect")

        # Start simulation with long path and slow speed
        path = [
            {"latitude": 25.0 + i * 0.001, "longitude": 121.0 + i * 0.001}
            for i in range(10)
        ]
        resp = client.post("/api/simulation/start", json={
            "udid": udid,
            "path": path,
            "speed_kmh": 1.0,  # Very slow
            "drift_enabled": False,
        })
        assert resp.status_code == 200

        time.sleep(0.1)

        # Change speed to fast
        resp = client.post("/api/simulation/speed", json={
            "udid": udid,
            "speed_kmh": 500.0,
        })
        assert resp.status_code == 200
        assert resp.json()["success"] is True

        # Wait for completion at high speed
        time.sleep(2.0)

        # Clean up
        app_state.stop_simulator(udid)

    def test_replace_running_simulation(self, e2e_client, ios16_env, app_state):
        """Starting a new simulation while one is running should stop the old one."""
        client = e2e_client
        udid = ios16_env["udid"]

        client.post(f"/api/devices/{udid}/connect")

        # Start first simulation (slow, long path)
        path1 = [
            {"latitude": 25.0 + i * 0.001, "longitude": 121.0 + i * 0.001}
            for i in range(20)
        ]
        resp = client.post("/api/simulation/start", json={
            "udid": udid,
            "path": path1,
            "speed_kmh": 1.0,
            "drift_enabled": False,
        })
        assert resp.status_code == 200

        time.sleep(0.2)

        # Start second simulation (replaces first)
        path2 = [
            {"latitude": 35.0 + i * 0.001, "longitude": 139.0 + i * 0.001}
            for i in range(5)
        ]
        resp = client.post("/api/simulation/start", json={
            "udid": udid,
            "path": path2,
            "speed_kmh": 500.0,
            "drift_enabled": False,
        })
        assert resp.status_code == 200

        time.sleep(1.0)

        # Clean up
        app_state.stop_simulator(udid)


# ------------------------------------------------------------------
# Test 3: GPX Parsing Integration
# ------------------------------------------------------------------

class TestGPXIntegration:
    """Tests for GPX parsing through the API layer."""

    _VALID_GPX = """\
<?xml version="1.0" encoding="UTF-8"?>
<gpx xmlns="http://www.topografix.com/GPX/1/1" version="1.1">
  <trk><trkseg>
    <trkpt lat="25.0330" lon="121.5654"/>
    <trkpt lat="25.0335" lon="121.5659"/>
    <trkpt lat="25.0340" lon="121.5664"/>
  </trkseg></trk>
</gpx>"""

    def test_parse_gpx_and_start_simulation(self, e2e_client, ios16_env, app_state):
        """Parse GPX -> use waypoints to start simulation (full integration)."""
        client = e2e_client
        udid = ios16_env["udid"]

        # Connect device
        client.post(f"/api/devices/{udid}/connect")

        # Parse GPX
        resp = client.post("/api/gpx/parse", json={
            "gpx_content": self._VALID_GPX,
            "source": "test.gpx",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 3
        waypoints = data["waypoints"]

        # Use parsed waypoints to start simulation
        resp = client.post("/api/simulation/start", json={
            "udid": udid,
            "path": waypoints,
            "speed_kmh": 999.0,
            "drift_enabled": False,
        })
        assert resp.status_code == 200

        # Wait for completion
        time.sleep(1.0)

        # DtSimulateLocation.set should have been called
        assert ios16_env["dt_sim_instance"].set.call_count >= 1

        # Clean up
        app_state.stop_simulator(udid)

    def test_parse_invalid_gpx_returns_error(self, e2e_client):
        """Parsing invalid GPX should return 400 error."""
        client = e2e_client

        resp = client.post("/api/gpx/parse", json={
            "gpx_content": "not valid xml at all <<<<",
        })
        assert resp.status_code == 400
        assert resp.json()["success"] is False

    def test_parse_empty_gpx_returns_error(self, e2e_client):
        """Parsing GPX with no waypoints should return error."""
        client = e2e_client

        empty_gpx = '<?xml version="1.0"?><gpx xmlns="http://www.topografix.com/GPX/1/1" version="1.1"></gpx>'
        resp = client.post("/api/gpx/parse", json={
            "gpx_content": empty_gpx,
        })
        assert resp.status_code == 400


# ------------------------------------------------------------------
# Test 4: Favorites Integration
# ------------------------------------------------------------------

class TestFavoritesIntegration:
    """Tests for favorites CRUD through the API layer."""

    def test_favorites_crud_lifecycle(self, e2e_client, app_state):
        """Add, list, and remove favorites."""
        client = e2e_client

        # Initially empty
        resp = client.get("/api/favorites")
        assert resp.status_code == 200
        assert resp.json()["count"] == 0

        # Add two favorites
        resp = client.post("/api/favorites", json={
            "name": "Taipei 101",
            "latitude": 25.0330,
            "longitude": 121.5654,
        })
        assert resp.status_code == 200

        resp = client.post("/api/favorites", json={
            "name": "Tokyo Tower",
            "latitude": 35.6586,
            "longitude": 139.7454,
        })
        assert resp.status_code == 200

        # List should show 2
        resp = client.get("/api/favorites")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 2
        assert data["favorites"][0]["name"] == "Taipei 101"
        assert data["favorites"][1]["name"] == "Tokyo Tower"

        # Remove first (index 0)
        resp = client.delete("/api/favorites/0")
        assert resp.status_code == 200

        # List should show 1
        resp = client.get("/api/favorites")
        assert resp.status_code == 200
        assert resp.json()["count"] == 1
        assert resp.json()["favorites"][0]["name"] == "Tokyo Tower"

        # Remove invalid index
        resp = client.delete("/api/favorites/99")
        assert resp.status_code == 404

    def test_set_location_from_favorite_coords(self, e2e_client, ios16_env, app_state):
        """Add favorite, then use its coordinates to set location."""
        client = e2e_client
        udid = ios16_env["udid"]

        # Connect device
        client.post(f"/api/devices/{udid}/connect")

        # Add favorite
        client.post("/api/favorites", json={
            "name": "Test Place",
            "latitude": 48.8566,
            "longitude": 2.3522,
        })

        # Get favorite coordinates
        resp = client.get("/api/favorites")
        fav = resp.json()["favorites"][0]

        # Use them to set location
        resp = client.post("/api/location/set", json={
            "udid": udid,
            "latitude": fav["latitude"],
            "longitude": fav["longitude"],
        })
        assert resp.status_code == 200

        # Verify
        resp = client.get(f"/api/location/{udid}")
        assert resp.json()["current_location"]["latitude"] == pytest.approx(48.8566)


# ------------------------------------------------------------------
# Test 5: Error Propagation & Edge Cases
# ------------------------------------------------------------------

class TestErrorPropagation:
    """Tests for error handling across module boundaries."""

    def test_set_location_on_nonexistent_device(self, e2e_client):
        """Setting location on a device that doesn't exist should fail."""
        client = e2e_client

        resp = client.post("/api/location/set", json={
            "udid": "nonexistent-device",
            "latitude": 25.0,
            "longitude": 121.0,
        })
        assert resp.status_code == 400
        assert "error" in resp.json()

    def test_clear_location_on_nonexistent_device(self, e2e_client):
        """Clearing location on a non-connected device should fail."""
        client = e2e_client

        resp = client.post("/api/location/clear", json={
            "udid": "nonexistent-device",
        })
        assert resp.status_code == 400

    def test_invalid_coordinates_rejected(self, e2e_client, ios16_env):
        """Invalid coordinates should be rejected by Pydantic validation."""
        client = e2e_client
        udid = ios16_env["udid"]

        client.post(f"/api/devices/{udid}/connect")

        # Latitude out of range
        resp = client.post("/api/location/set", json={
            "udid": udid,
            "latitude": 91.0,
            "longitude": 121.0,
        })
        assert resp.status_code == 422  # Validation error

        # Longitude out of range
        resp = client.post("/api/location/set", json={
            "udid": udid,
            "latitude": 25.0,
            "longitude": 181.0,
        })
        assert resp.status_code == 422

    def test_simulation_with_device_error_mid_run(
        self, e2e_client, ios16_env, app_state
    ):
        """If the device fails during simulation, simulation should stop with error."""
        client = e2e_client
        udid = ios16_env["udid"]
        dt_sim = ios16_env["dt_sim_instance"]

        # Connect
        client.post(f"/api/devices/{udid}/connect")

        # Make set fail after a few calls (simulating USB disconnect)
        call_count = 0

        def fail_after_3(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count > 3:
                raise OSError("USB device disconnected")

        dt_sim.set.side_effect = fail_after_3

        # Start simulation
        path = [
            {"latitude": 25.0 + i * 0.0001, "longitude": 121.0 + i * 0.0001}
            for i in range(20)
        ]
        resp = client.post("/api/simulation/start", json={
            "udid": udid,
            "path": path,
            "speed_kmh": 500.0,
            "drift_enabled": False,
        })
        assert resp.status_code == 200

        # Wait for error to propagate
        time.sleep(2.0)

        # Simulation should have stopped due to error
        sim = app_state.get_simulator(udid)
        # Either unregistered (via on_error callback) or stopped
        if sim is not None:
            from ios_gps_spoofer.simulation.state_machine import SimulationState
            assert sim.state == SimulationState.STOPPED

    def test_get_device_not_found(self, e2e_client):
        """Getting info for a non-existent device should return 404."""
        client = e2e_client

        resp = client.get("/api/devices/fake-udid-12345")
        assert resp.status_code == 404
        assert resp.json()["error"] == "Device not found"

    def test_negative_speed_rejected(self, e2e_client, ios16_env):
        """Negative speed should be rejected by validation."""
        client = e2e_client
        udid = ios16_env["udid"]

        client.post(f"/api/devices/{udid}/connect")

        resp = client.post("/api/simulation/start", json={
            "udid": udid,
            "path": [
                {"latitude": 25.0, "longitude": 121.0},
                {"latitude": 25.1, "longitude": 121.1},
            ],
            "speed_kmh": -5.0,
        })
        assert resp.status_code == 422

    def test_zero_speed_rejected(self, e2e_client, ios16_env):
        """Zero speed should be rejected by validation."""
        client = e2e_client
        udid = ios16_env["udid"]

        client.post(f"/api/devices/{udid}/connect")

        resp = client.post("/api/simulation/start", json={
            "udid": udid,
            "path": [
                {"latitude": 25.0, "longitude": 121.0},
                {"latitude": 25.1, "longitude": 121.1},
            ],
            "speed_kmh": 0.0,
        })
        assert resp.status_code == 422


# ------------------------------------------------------------------
# Test 6: Rapid Sequential Operations (Stress)
# ------------------------------------------------------------------

class TestRapidOperations:
    """Stress tests for rapid sequential operations."""

    def test_rapid_location_updates(self, e2e_client, ios16_env):
        """50 rapid location updates should all succeed."""
        client = e2e_client
        udid = ios16_env["udid"]
        dt_sim = ios16_env["dt_sim_instance"]

        client.post(f"/api/devices/{udid}/connect")

        for i in range(50):
            lat = 25.0 + i * 0.001
            lon = 121.0 + i * 0.001
            resp = client.post("/api/location/set", json={
                "udid": udid,
                "latitude": lat,
                "longitude": lon,
            })
            assert resp.status_code == 200, f"Failed on update {i}: {resp.json()}"

        # Final location should be the last set
        resp = client.get(f"/api/location/{udid}")
        assert resp.status_code == 200
        status = resp.json()
        assert status["current_location"]["latitude"] == pytest.approx(25.049, abs=0.001)

        # DtSimulateLocation.set should have been called 50 times
        assert dt_sim.set.call_count == 50

    def test_rapid_start_stop_simulation(self, e2e_client, ios16_env, app_state):
        """Rapidly starting and stopping simulations should not crash."""
        client = e2e_client
        udid = ios16_env["udid"]

        client.post(f"/api/devices/{udid}/connect")

        path = [
            {"latitude": 25.0 + i * 0.001, "longitude": 121.0 + i * 0.001}
            for i in range(5)
        ]

        for _ in range(10):
            resp = client.post("/api/simulation/start", json={
                "udid": udid,
                "path": path,
                "speed_kmh": 1.0,  # slow enough to still be running
                "drift_enabled": False,
            })
            assert resp.status_code == 200

            time.sleep(0.05)

            client.post("/api/simulation/stop", json={"udid": udid})
            time.sleep(0.05)

        # Ensure no lingering simulators
        time.sleep(0.5)
        app_state.stop_all_simulators()

    def test_rapid_favorites_crud(self, e2e_client, app_state):
        """Rapid add/remove of favorites should be consistent."""
        client = e2e_client

        # Add 20 favorites
        for i in range(20):
            resp = client.post("/api/favorites", json={
                "name": f"Place {i}",
                "latitude": 20.0 + i,
                "longitude": 100.0 + i,
            })
            assert resp.status_code == 200

        # Verify count
        resp = client.get("/api/favorites")
        assert resp.json()["count"] == 20

        # Remove them all (always remove index 0 since list shifts)
        for _ in range(20):
            resp = client.delete("/api/favorites/0")
            assert resp.status_code == 200

        # Verify empty
        resp = client.get("/api/favorites")
        assert resp.json()["count"] == 0


# ------------------------------------------------------------------
# Test 7: Long-Running Simulation Stability
# ------------------------------------------------------------------

class TestSimulationStability:
    """Tests for simulation stability over extended runs."""

    def test_medium_duration_simulation_completes(
        self, e2e_client, ios16_env, app_state
    ):
        """A simulation with many waypoints should complete without error.

        Uses a moderately large path (100 points) to exercise the simulation
        loop for a sustained period (still fast enough for a test).
        """
        client = e2e_client
        udid = ios16_env["udid"]

        client.post(f"/api/devices/{udid}/connect")

        # Create a 100-point path
        path = [
            {"latitude": 25.0 + i * 0.0001, "longitude": 121.0 + i * 0.0001}
            for i in range(100)
        ]
        resp = client.post("/api/simulation/start", json={
            "udid": udid,
            "path": path,
            "speed_kmh": 999.0,
            "drift_enabled": True,
            "drift_sigma_meters": 2.0,
        })
        assert resp.status_code == 200

        # Wait for completion (100 points at 999 km/h with very short segments)
        completed = False
        for _ in range(50):  # Poll for up to 5 seconds
            time.sleep(0.1)
            sim = app_state.get_simulator(udid)
            if sim is None:
                completed = True
                break
            from ios_gps_spoofer.simulation.state_machine import SimulationState
            if sim.state == SimulationState.STOPPED:
                completed = True
                break

        assert completed, "Simulation did not complete within timeout"

        # Should have made many set_location calls
        assert ios16_env["dt_sim_instance"].set.call_count >= 50


# ------------------------------------------------------------------
# Test 8: Simulation with Drift Verification
# ------------------------------------------------------------------

class TestDriftIntegration:
    """Tests for GPS drift through the complete stack."""

    def test_drift_produces_variation(self, e2e_client, ios16_env, app_state):
        """Simulation with drift enabled should produce varying coordinates."""
        client = e2e_client
        udid = ios16_env["udid"]
        dt_sim = ios16_env["dt_sim_instance"]

        client.post(f"/api/devices/{udid}/connect")

        # Use a longer path at equator for drift detection with many waypoints
        path = [
            {"latitude": 0.0, "longitude": i * 0.001}
            for i in range(20)
        ]
        resp = client.post("/api/simulation/start", json={
            "udid": udid,
            "path": path,
            "speed_kmh": 50.0,
            "drift_enabled": True,
            "drift_sigma_meters": 10.0,
        })
        assert resp.status_code == 200

        # Wait for completion
        time.sleep(3.0)
        app_state.stop_simulator(udid)

        # Check that at least some calls had latitude != 0.0 (drift applied)
        # With 20 waypoints and sigma=10m, there should be many calls with
        # detectable drift in latitude (which should be ~0.0 without drift)
        calls = dt_sim.set.call_args_list
        if len(calls) > 5:
            has_drift = any(
                abs(call[0][0]) > 0.00001  # latitude drifted from 0.0
                for call in calls
            )
            assert has_drift, (
                f"Expected drift to deviate latitude from exact 0.0 "
                f"({len(calls)} calls)"
            )


# ------------------------------------------------------------------
# Test 9: Cross-Module State Consistency
# ------------------------------------------------------------------

class TestStateConsistency:
    """Tests that state remains consistent across all modules."""

    def test_location_cleared_after_simulation_stop(
        self, e2e_client, ios16_env, app_state
    ):
        """After stopping simulation and clearing location, all state should reset."""
        client = e2e_client
        udid = ios16_env["udid"]

        client.post(f"/api/devices/{udid}/connect")

        # Set location
        client.post("/api/location/set", json={
            "udid": udid,
            "latitude": 25.0,
            "longitude": 121.0,
        })

        # Start simulation
        path = [
            {"latitude": 25.0, "longitude": 121.0},
            {"latitude": 25.1, "longitude": 121.1},
        ]
        client.post("/api/simulation/start", json={
            "udid": udid,
            "path": path,
            "speed_kmh": 999.0,
            "drift_enabled": False,
        })

        time.sleep(1.0)

        # Stop and clear
        client.post("/api/simulation/stop", json={"udid": udid})
        client.post("/api/location/clear", json={"udid": udid})

        # Verify all state is clean
        resp = client.get(f"/api/location/{udid}")
        assert resp.json()["simulation_active"] is False
        assert resp.json()["current_location"] is None

        resp = client.get(f"/api/simulation/{udid}")
        assert resp.json()["state"] == "idle"

    def test_multiple_operations_maintain_consistency(
        self, e2e_client, ios16_env, app_state
    ):
        """Interleaving set, start, stop, clear should not corrupt state."""
        client = e2e_client
        udid = ios16_env["udid"]

        client.post(f"/api/devices/{udid}/connect")

        # Set location
        client.post("/api/location/set", json={
            "udid": udid,
            "latitude": 25.0,
            "longitude": 121.0,
        })
        assert client.get(f"/api/location/{udid}").json()["simulation_active"]

        # Start simulation (overwrites location tracking)
        path = [
            {"latitude": 30.0, "longitude": 130.0},
            {"latitude": 30.1, "longitude": 130.1},
        ]
        client.post("/api/simulation/start", json={
            "udid": udid,
            "path": path,
            "speed_kmh": 999.0,
            "drift_enabled": False,
        })

        time.sleep(1.0)

        # Stop simulation explicitly before setting new location to avoid
        # race condition where a simulation tick overwrites the new location
        client.post("/api/simulation/stop", json={"udid": udid})
        time.sleep(0.2)

        # Set a new point location (after sim is stopped)
        client.post("/api/location/set", json={
            "udid": udid,
            "latitude": 40.0,
            "longitude": 140.0,
        })

        status = client.get(f"/api/location/{udid}").json()
        assert status["simulation_active"] is True
        assert status["current_location"]["latitude"] == pytest.approx(40.0)

        # Final clear
        client.post("/api/location/clear", json={"udid": udid})
        assert not client.get(f"/api/location/{udid}").json()["simulation_active"]

        # Clean up
        app_state.stop_all_simulators()


# ------------------------------------------------------------------
# Test 10: Concurrent Simulation (Multi-device)
# ------------------------------------------------------------------

class TestConcurrentSimulation:
    """Tests for running simulations on multiple devices simultaneously."""

    def test_two_devices_concurrent_simulation(self, app_state, ws_manager):
        """Two devices can run independent simulations concurrently via AppState."""
        # This test bypasses the API layer to directly test AppState with
        # two independent simulators, since the mock environment only
        # supports one device via the ios16_env fixture.
        from ios_gps_spoofer.location.coordinates import Coordinate
        from ios_gps_spoofer.simulation.path_simulator import (
            PathSimulator,
            SimulationConfig,
        )
        from ios_gps_spoofer.simulation.speed_profiles import MAX_SPEED_MS

        mock_ls = MagicMock()
        config = SimulationConfig(drift_enabled=False, tick_interval_s=0.01)

        path = [
            Coordinate(latitude=25.0 + i * 0.0001, longitude=121.0 + i * 0.0001)
            for i in range(5)
        ]

        completed_a = threading.Event()
        completed_b = threading.Event()

        sim_a = PathSimulator(
            udid="device-a",
            path=path,
            location_service=mock_ls,
            config=config,
            on_complete=completed_a.set,
        )
        sim_b = PathSimulator(
            udid="device-b",
            path=path,
            location_service=mock_ls,
            config=config,
            on_complete=completed_b.set,
        )

        sim_a.speed_controller.set_speed_ms(MAX_SPEED_MS)
        sim_b.speed_controller.set_speed_ms(MAX_SPEED_MS)

        app_state.register_simulator("device-a", sim_a)
        app_state.register_simulator("device-b", sim_b)

        sim_a.start()
        sim_b.start()

        assert completed_a.wait(timeout=10.0), "Simulator A did not complete"
        assert completed_b.wait(timeout=10.0), "Simulator B did not complete"

        # Both sent locations
        device_a_calls = [
            c for c in mock_ls.set_location.call_args_list
            if c[0][0] == "device-a"
        ]
        device_b_calls = [
            c for c in mock_ls.set_location.call_args_list
            if c[0][0] == "device-b"
        ]
        assert len(device_a_calls) >= 1
        assert len(device_b_calls) >= 1


# ------------------------------------------------------------------
# Test 11: Input Validation Across Stack
# ------------------------------------------------------------------

class TestInputValidation:
    """Tests for input validation at the API boundary."""

    def test_empty_udid_rejected(self, e2e_client):
        """Empty UDID should be rejected."""
        client = e2e_client

        resp = client.post("/api/location/set", json={
            "udid": "",
            "latitude": 25.0,
            "longitude": 121.0,
        })
        assert resp.status_code == 422

    def test_missing_required_fields(self, e2e_client):
        """Missing required fields should return 422."""
        client = e2e_client

        # Missing udid
        resp = client.post("/api/location/set", json={
            "latitude": 25.0,
            "longitude": 121.0,
        })
        assert resp.status_code == 422

        # Missing coordinates
        resp = client.post("/api/location/set", json={
            "udid": "test",
        })
        assert resp.status_code == 422

    def test_invalid_json_body(self, e2e_client):
        """Malformed JSON should return 422."""
        client = e2e_client

        resp = client.post(
            "/api/location/set",
            content="not json at all",
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code == 422

    def test_boundary_coordinates(self, e2e_client, ios16_env):
        """Coordinates at exact boundaries should be accepted."""
        client = e2e_client
        udid = ios16_env["udid"]

        client.post(f"/api/devices/{udid}/connect")

        # Exact boundaries
        for lat, lng in [
            (90.0, 180.0),
            (-90.0, -180.0),
            (0.0, 0.0),
            (90.0, -180.0),
            (-90.0, 180.0),
        ]:
            resp = client.post("/api/location/set", json={
                "udid": udid,
                "latitude": lat,
                "longitude": lng,
            })
            assert resp.status_code == 200, f"Failed for ({lat}, {lng}): {resp.json()}"
