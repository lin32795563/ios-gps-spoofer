"""Tests for AppState application state management."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from ios_gps_spoofer.api.app_state import AppState
from ios_gps_spoofer.api.models import FavoriteLocation
from ios_gps_spoofer.simulation.state_machine import SimulationState

# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _make_mock_simulator(
    udid: str = "test-udid",
    state: SimulationState = SimulationState.RUNNING,
) -> MagicMock:
    """Create a mock PathSimulator."""
    sim = MagicMock()
    sim.udid = udid
    sim.state = state
    sim.speed_controller.speed_ms = 1.39  # ~5 km/h
    sim.stop = MagicMock()
    sim.wait = MagicMock()
    return sim


# ------------------------------------------------------------------
# Construction and lifecycle
# ------------------------------------------------------------------

class TestAppStateLifecycle:
    """Tests for AppState startup and shutdown."""

    @patch("ios_gps_spoofer.api.app_state.DeviceManager")
    @patch("ios_gps_spoofer.api.app_state.LocationService")
    def test_construction(self, mock_ls, mock_dm):
        state = AppState()
        assert state.device_manager is not None
        assert state.location_service is not None

    @patch("ios_gps_spoofer.api.app_state.DeviceManager")
    @patch("ios_gps_spoofer.api.app_state.LocationService")
    def test_startup_starts_polling(self, mock_ls, mock_dm):
        state = AppState()
        state._favorites_file = MagicMock()
        state._favorites_file.exists.return_value = False
        state.startup()
        state.device_manager.start_polling.assert_called_once()

    @patch("ios_gps_spoofer.api.app_state.DeviceManager")
    @patch("ios_gps_spoofer.api.app_state.LocationService")
    def test_shutdown_stops_polling(self, mock_ls, mock_dm):
        state = AppState()
        state._favorites_file = MagicMock()
        state._favorites_file.exists.return_value = False
        state._favorites_file.parent = MagicMock()
        state.startup()
        state.shutdown()
        state.device_manager.stop_polling.assert_called_once()


# ------------------------------------------------------------------
# Simulator management
# ------------------------------------------------------------------

class TestSimulatorManagement:
    """Tests for active simulator tracking."""

    @patch("ios_gps_spoofer.api.app_state.DeviceManager")
    @patch("ios_gps_spoofer.api.app_state.LocationService")
    def test_register_and_get(self, mock_ls, mock_dm):
        state = AppState()
        sim = _make_mock_simulator("d1")
        state.register_simulator("d1", sim)
        assert state.get_simulator("d1") is sim

    @patch("ios_gps_spoofer.api.app_state.DeviceManager")
    @patch("ios_gps_spoofer.api.app_state.LocationService")
    def test_get_nonexistent(self, mock_ls, mock_dm):
        state = AppState()
        assert state.get_simulator("nonexistent") is None

    @patch("ios_gps_spoofer.api.app_state.DeviceManager")
    @patch("ios_gps_spoofer.api.app_state.LocationService")
    def test_unregister(self, mock_ls, mock_dm):
        state = AppState()
        sim = _make_mock_simulator("d1")
        state.register_simulator("d1", sim)
        state.unregister_simulator("d1")
        assert state.get_simulator("d1") is None

    @patch("ios_gps_spoofer.api.app_state.DeviceManager")
    @patch("ios_gps_spoofer.api.app_state.LocationService")
    def test_register_stops_existing(self, mock_ls, mock_dm):
        state = AppState()
        sim1 = _make_mock_simulator("d1")
        sim2 = _make_mock_simulator("d1")
        state.register_simulator("d1", sim1)
        state.register_simulator("d1", sim2)
        # First simulator should have been stopped
        sim1.stop.assert_called_once()
        assert state.get_simulator("d1") is sim2

    @patch("ios_gps_spoofer.api.app_state.DeviceManager")
    @patch("ios_gps_spoofer.api.app_state.LocationService")
    def test_register_does_not_stop_idle_simulator(self, mock_ls, mock_dm):
        state = AppState()
        sim1 = _make_mock_simulator("d1", state=SimulationState.IDLE)
        sim2 = _make_mock_simulator("d1")
        state.register_simulator("d1", sim1)
        state.register_simulator("d1", sim2)
        # IDLE simulator should not call stop
        sim1.stop.assert_not_called()

    @patch("ios_gps_spoofer.api.app_state.DeviceManager")
    @patch("ios_gps_spoofer.api.app_state.LocationService")
    def test_stop_simulator(self, mock_ls, mock_dm):
        state = AppState()
        sim = _make_mock_simulator("d1")
        state.register_simulator("d1", sim)
        result = state.stop_simulator("d1")
        assert result is True
        sim.stop.assert_called_once()
        assert state.get_simulator("d1") is None

    @patch("ios_gps_spoofer.api.app_state.DeviceManager")
    @patch("ios_gps_spoofer.api.app_state.LocationService")
    def test_stop_simulator_nonexistent(self, mock_ls, mock_dm):
        state = AppState()
        result = state.stop_simulator("nonexistent")
        assert result is False

    @patch("ios_gps_spoofer.api.app_state.DeviceManager")
    @patch("ios_gps_spoofer.api.app_state.LocationService")
    def test_stop_all_simulators(self, mock_ls, mock_dm):
        state = AppState()
        sim1 = _make_mock_simulator("d1")
        sim2 = _make_mock_simulator("d2")
        state.register_simulator("d1", sim1)
        state.register_simulator("d2", sim2)
        count = state.stop_all_simulators()
        assert count == 2
        sim1.stop.assert_called_once()
        sim2.stop.assert_called_once()

    @patch("ios_gps_spoofer.api.app_state.DeviceManager")
    @patch("ios_gps_spoofer.api.app_state.LocationService")
    def test_stop_all_empty(self, mock_ls, mock_dm):
        state = AppState()
        count = state.stop_all_simulators()
        assert count == 0

    @patch("ios_gps_spoofer.api.app_state.DeviceManager")
    @patch("ios_gps_spoofer.api.app_state.LocationService")
    def test_get_simulator_status(self, mock_ls, mock_dm):
        state = AppState()
        sim = _make_mock_simulator("d1")
        sim.state = SimulationState.RUNNING
        state.register_simulator("d1", sim)
        status = state.get_simulator_status("d1")
        assert status is not None
        assert status["udid"] == "d1"
        assert status["state"] == "running"

    @patch("ios_gps_spoofer.api.app_state.DeviceManager")
    @patch("ios_gps_spoofer.api.app_state.LocationService")
    def test_get_simulator_status_none(self, mock_ls, mock_dm):
        state = AppState()
        status = state.get_simulator_status("nonexistent")
        assert status is None

    @patch("ios_gps_spoofer.api.app_state.DeviceManager")
    @patch("ios_gps_spoofer.api.app_state.LocationService")
    def test_stop_already_stopped_simulator(self, mock_ls, mock_dm):
        state = AppState()
        sim = _make_mock_simulator("d1", state=SimulationState.STOPPED)
        state.register_simulator("d1", sim)
        state.stop_simulator("d1")
        # Should not call stop on already-stopped simulator
        sim.stop.assert_not_called()


# ------------------------------------------------------------------
# Favorites management
# ------------------------------------------------------------------

class TestFavoritesManagement:
    """Tests for favorites CRUD."""

    @patch("ios_gps_spoofer.api.app_state.DeviceManager")
    @patch("ios_gps_spoofer.api.app_state.LocationService")
    def test_add_and_get_favorites(self, mock_ls, mock_dm):
        state = AppState()
        state._favorites_file = MagicMock()
        state._favorites_file.parent = MagicMock()

        fav = FavoriteLocation(name="Home", latitude=25.0, longitude=121.5)
        state.add_favorite(fav)
        favorites = state.get_favorites()
        assert len(favorites) == 1
        assert favorites[0].name == "Home"

    @patch("ios_gps_spoofer.api.app_state.DeviceManager")
    @patch("ios_gps_spoofer.api.app_state.LocationService")
    def test_remove_favorite(self, mock_ls, mock_dm):
        state = AppState()
        state._favorites_file = MagicMock()
        state._favorites_file.parent = MagicMock()

        fav = FavoriteLocation(name="Home", latitude=25.0, longitude=121.5)
        state.add_favorite(fav)
        removed = state.remove_favorite(0)
        assert removed is not None
        assert removed.name == "Home"
        assert len(state.get_favorites()) == 0

    @patch("ios_gps_spoofer.api.app_state.DeviceManager")
    @patch("ios_gps_spoofer.api.app_state.LocationService")
    def test_remove_invalid_index(self, mock_ls, mock_dm):
        state = AppState()
        removed = state.remove_favorite(0)
        assert removed is None

    @patch("ios_gps_spoofer.api.app_state.DeviceManager")
    @patch("ios_gps_spoofer.api.app_state.LocationService")
    def test_get_favorites_returns_copy(self, mock_ls, mock_dm):
        state = AppState()
        fav = FavoriteLocation(name="Home", latitude=25.0, longitude=121.5)
        state._favorites = [fav]
        copy = state.get_favorites()
        copy.clear()
        assert len(state._favorites) == 1  # original unmodified

    @patch("ios_gps_spoofer.api.app_state.DeviceManager")
    @patch("ios_gps_spoofer.api.app_state.LocationService")
    def test_load_favorites_from_file(self, mock_ls, mock_dm, tmp_path):
        favorites_file = tmp_path / "favorites.json"
        data = [
            {"name": "Home", "latitude": 25.0, "longitude": 121.5},
            {"name": "Work", "latitude": 25.1, "longitude": 121.6},
        ]
        favorites_file.write_text(json.dumps(data), encoding="utf-8")

        state = AppState()
        state._favorites_file = favorites_file
        state._load_favorites()
        assert len(state._favorites) == 2
        assert state._favorites[0].name == "Home"

    @patch("ios_gps_spoofer.api.app_state.DeviceManager")
    @patch("ios_gps_spoofer.api.app_state.LocationService")
    def test_load_favorites_missing_file(self, mock_ls, mock_dm, tmp_path):
        state = AppState()
        state._favorites_file = tmp_path / "nonexistent.json"
        state._load_favorites()
        assert len(state._favorites) == 0

    @patch("ios_gps_spoofer.api.app_state.DeviceManager")
    @patch("ios_gps_spoofer.api.app_state.LocationService")
    def test_save_favorites(self, mock_ls, mock_dm, tmp_path):
        favorites_file = tmp_path / "favorites.json"

        state = AppState()
        state._favorites_file = favorites_file
        fav = FavoriteLocation(name="Home", latitude=25.0, longitude=121.5)
        state._favorites = [fav]
        state._save_favorites()

        assert favorites_file.exists()
        data = json.loads(favorites_file.read_text(encoding="utf-8"))
        assert len(data) == 1
        assert data[0]["name"] == "Home"

    @patch("ios_gps_spoofer.api.app_state.DeviceManager")
    @patch("ios_gps_spoofer.api.app_state.LocationService")
    def test_load_corrupt_file(self, mock_ls, mock_dm, tmp_path):
        favorites_file = tmp_path / "favorites.json"
        favorites_file.write_text("NOT JSON", encoding="utf-8")

        state = AppState()
        state._favorites_file = favorites_file
        state._load_favorites()
        assert len(state._favorites) == 0  # gracefully handles corruption
