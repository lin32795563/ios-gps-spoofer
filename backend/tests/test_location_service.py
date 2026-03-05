"""Tests for ios_gps_spoofer.location.location_service module.

All pymobiledevice3 interactions are mocked.  Tests cover:

- LocationService initialization
- set_location: valid coordinate, device not ready, pymobiledevice3 error
- clear_location: success, device not ready, pymobiledevice3 error
- get_current_location: before/after set, after clear
- is_simulation_active: before/after set, after clear
- cleanup_device: removes state, no crash on unknown device
- get_status: format, values before/after set
- Thread safety: concurrent set_location calls
- Type checking: reject non-Coordinate arguments
- Integration with DeviceManager.get_service_provider
- DVT path (iOS 17+): DvtSecureSocketProxyService + LocationSimulation routing

Patch target conventions:
- DtSimulateLocation is imported locally inside methods, so we patch it at
  its source: pymobiledevice3.services.simulate_location.DtSimulateLocation
- DvtSecureSocketProxyService and LocationSimulation are imported locally for
  iOS 17+, patched at their source packages.
"""

import threading
from unittest.mock import MagicMock, patch

import pytest

from ios_gps_spoofer.device.exceptions import (
    DeviceConnectionError,
    DeviceNotFoundError,
)
from ios_gps_spoofer.device.models import IOSVersionCategory
from ios_gps_spoofer.location.coordinates import Coordinate
from ios_gps_spoofer.location.exceptions import (
    LocationClearError,
    LocationServiceNotReadyError,
    LocationSetError,
)
from ios_gps_spoofer.location.location_service import LocationService

_PATCH_DT_SIM = "pymobiledevice3.services.simulate_location.DtSimulateLocation"
_PATCH_DVT_PROXY = "pymobiledevice3.services.dvt.dvt_secure_socket_proxy.DvtSecureSocketProxyService"
_PATCH_LOC_SIM = "pymobiledevice3.services.dvt.instruments.location_simulation.LocationSimulation"


def _make_mock_device_manager(
    service_provider: MagicMock | None = None,
    raise_on_get: Exception | None = None,
    ios_category: IOSVersionCategory = IOSVersionCategory.DDI,
) -> MagicMock:
    """Create a mock DeviceManager with configurable get_service_provider.

    Args:
        service_provider: The mock to return from get_service_provider.
        raise_on_get: If set, get_service_provider will raise this exception.
        ios_category: The iOS version category to return from get_ios_category.
    """
    dm = MagicMock()
    if raise_on_get is not None:
        dm.get_service_provider.side_effect = raise_on_get
    elif service_provider is not None:
        dm.get_service_provider.return_value = service_provider
    else:
        dm.get_service_provider.return_value = MagicMock()
    dm.get_ios_category.return_value = ios_category
    return dm


# =====================================================================
# Initialization
# =====================================================================

class TestLocationServiceInit:
    """Tests for LocationService.__init__."""

    def test_init_with_valid_device_manager(self) -> None:
        dm = MagicMock()
        service = LocationService(dm)
        assert service._device_manager is dm

    def test_init_with_none_raises(self) -> None:
        with pytest.raises(ValueError, match="device_manager must not be None"):
            LocationService(None)  # type: ignore[arg-type]


# =====================================================================
# set_location
# =====================================================================

class TestSetLocation:
    """Tests for LocationService.set_location."""

    @patch(_PATCH_DT_SIM)
    def test_set_location_success(self, mock_dt_sim_cls: MagicMock) -> None:
        """Setting a valid coordinate should call DtSimulateLocation.set."""
        mock_provider = MagicMock()
        dm = _make_mock_device_manager(service_provider=mock_provider)
        service = LocationService(dm)
        coord = Coordinate(latitude=25.0330, longitude=121.5654)

        service.set_location("device1", coord)

        dm.get_service_provider.assert_called_once_with("device1")
        mock_dt_sim_cls.assert_called_once_with(mock_provider)
        mock_dt_sim_cls.return_value.set.assert_called_once_with(
            25.0330, 121.5654
        )

    @patch(_PATCH_DT_SIM)
    def test_set_location_updates_current(
        self, mock_dt_sim_cls: MagicMock
    ) -> None:
        dm = _make_mock_device_manager()
        service = LocationService(dm)
        coord = Coordinate(latitude=10.0, longitude=20.0)

        service.set_location("d1", coord)

        assert service.get_current_location("d1") is coord

    @patch(_PATCH_DT_SIM)
    def test_set_location_marks_active(
        self, mock_dt_sim_cls: MagicMock
    ) -> None:
        dm = _make_mock_device_manager()
        service = LocationService(dm)
        coord = Coordinate(latitude=10.0, longitude=20.0)

        assert service.is_simulation_active("d1") is False
        service.set_location("d1", coord)
        assert service.is_simulation_active("d1") is True

    def test_set_location_device_not_found_raises(self) -> None:
        dm = _make_mock_device_manager(
            raise_on_get=DeviceNotFoundError("missing")
        )
        service = LocationService(dm)
        coord = Coordinate(latitude=0.0, longitude=0.0)

        with pytest.raises(LocationServiceNotReadyError, match="missing"):
            service.set_location("missing", coord)

    def test_set_location_device_not_ready_raises(self) -> None:
        dm = _make_mock_device_manager(
            raise_on_get=DeviceConnectionError("d1", "not ready")
        )
        service = LocationService(dm)
        coord = Coordinate(latitude=0.0, longitude=0.0)

        with pytest.raises(LocationServiceNotReadyError, match="not ready"):
            service.set_location("d1", coord)

    @patch(_PATCH_DT_SIM)
    def test_set_location_pymobiledevice_error_raises_set_error(
        self, mock_dt_sim_cls: MagicMock
    ) -> None:
        """Errors from DtSimulateLocation should be wrapped in LocationSetError."""
        mock_dt_sim_cls.return_value.set.side_effect = OSError("USB lost")
        dm = _make_mock_device_manager()
        service = LocationService(dm)
        coord = Coordinate(latitude=0.0, longitude=0.0)

        with pytest.raises(LocationSetError, match="USB lost"):
            service.set_location("d1", coord)

    @patch(_PATCH_DT_SIM)
    def test_set_location_constructor_error_raises_set_error(
        self, mock_dt_sim_cls: MagicMock
    ) -> None:
        """Error constructing DtSimulateLocation should be LocationSetError."""
        mock_dt_sim_cls.side_effect = ConnectionError("service unavailable")
        dm = _make_mock_device_manager()
        service = LocationService(dm)
        coord = Coordinate(latitude=0.0, longitude=0.0)

        with pytest.raises(LocationSetError, match="service unavailable"):
            service.set_location("d1", coord)

    def test_set_location_non_coordinate_raises_type_error(self) -> None:
        dm = _make_mock_device_manager()
        service = LocationService(dm)

        with pytest.raises(TypeError, match="Coordinate instance"):
            service.set_location("d1", (25.0, 121.0))  # type: ignore[arg-type]

    def test_set_location_dict_raises_type_error(self) -> None:
        dm = _make_mock_device_manager()
        service = LocationService(dm)

        with pytest.raises(TypeError, match="Coordinate instance"):
            service.set_location("d1", {"lat": 25.0, "lon": 121.0})  # type: ignore[arg-type]

    @patch(_PATCH_DT_SIM)
    def test_set_location_state_not_updated_on_error(
        self, mock_dt_sim_cls: MagicMock
    ) -> None:
        """If DtSimulateLocation.set() fails, internal state should not change."""
        mock_dt_sim_cls.return_value.set.side_effect = OSError("fail")
        dm = _make_mock_device_manager()
        service = LocationService(dm)
        coord = Coordinate(latitude=0.0, longitude=0.0)

        with pytest.raises(LocationSetError):
            service.set_location("d1", coord)

        assert service.get_current_location("d1") is None
        assert service.is_simulation_active("d1") is False

    @patch(_PATCH_DT_SIM)
    def test_set_location_overwrites_previous(
        self, mock_dt_sim_cls: MagicMock
    ) -> None:
        """Setting location twice should overwrite the first."""
        dm = _make_mock_device_manager()
        service = LocationService(dm)
        coord1 = Coordinate(latitude=10.0, longitude=20.0)
        coord2 = Coordinate(latitude=30.0, longitude=40.0)

        service.set_location("d1", coord1)
        service.set_location("d1", coord2)

        assert service.get_current_location("d1") is coord2

    @patch(_PATCH_DT_SIM)
    def test_set_location_boundary_coordinates(
        self, mock_dt_sim_cls: MagicMock
    ) -> None:
        """Setting location at boundary coordinates should work."""
        dm = _make_mock_device_manager()
        service = LocationService(dm)

        for lat, lon in [(90.0, 180.0), (-90.0, -180.0), (0.0, 0.0)]:
            coord = Coordinate(latitude=lat, longitude=lon)
            service.set_location("d1", coord)
            mock_dt_sim_cls.return_value.set.assert_called_with(lat, lon)


# =====================================================================
# clear_location
# =====================================================================

class TestClearLocation:
    """Tests for LocationService.clear_location."""

    @patch(_PATCH_DT_SIM)
    def test_clear_location_success(self, mock_dt_sim_cls: MagicMock) -> None:
        mock_provider = MagicMock()
        dm = _make_mock_device_manager(service_provider=mock_provider)
        service = LocationService(dm)

        # Set then clear
        coord = Coordinate(latitude=25.0, longitude=121.0)
        service.set_location("d1", coord)
        service.clear_location("d1")

        mock_dt_sim_cls.return_value.clear.assert_called_once()

    @patch(_PATCH_DT_SIM)
    def test_clear_removes_current_location(
        self, mock_dt_sim_cls: MagicMock
    ) -> None:
        dm = _make_mock_device_manager()
        service = LocationService(dm)
        coord = Coordinate(latitude=25.0, longitude=121.0)

        service.set_location("d1", coord)
        assert service.get_current_location("d1") is not None

        service.clear_location("d1")
        assert service.get_current_location("d1") is None

    @patch(_PATCH_DT_SIM)
    def test_clear_marks_inactive(self, mock_dt_sim_cls: MagicMock) -> None:
        dm = _make_mock_device_manager()
        service = LocationService(dm)
        coord = Coordinate(latitude=25.0, longitude=121.0)

        service.set_location("d1", coord)
        assert service.is_simulation_active("d1") is True

        service.clear_location("d1")
        assert service.is_simulation_active("d1") is False

    def test_clear_location_device_not_found_raises(self) -> None:
        dm = _make_mock_device_manager(
            raise_on_get=DeviceNotFoundError("missing")
        )
        service = LocationService(dm)

        with pytest.raises(LocationServiceNotReadyError, match="missing"):
            service.clear_location("missing")

    @patch(_PATCH_DT_SIM)
    def test_clear_location_pymobiledevice_error_raises(
        self, mock_dt_sim_cls: MagicMock
    ) -> None:
        mock_dt_sim_cls.return_value.clear.side_effect = OSError("USB lost")
        dm = _make_mock_device_manager()
        service = LocationService(dm)

        with pytest.raises(LocationClearError, match="USB lost"):
            service.clear_location("d1")

    @patch(_PATCH_DT_SIM)
    def test_clear_without_prior_set_still_works(
        self, mock_dt_sim_cls: MagicMock
    ) -> None:
        """Clearing without setting first should still send clear to device."""
        dm = _make_mock_device_manager()
        service = LocationService(dm)

        service.clear_location("d1")
        mock_dt_sim_cls.return_value.clear.assert_called_once()

    @patch(_PATCH_DT_SIM)
    def test_clear_state_not_updated_on_error(
        self, mock_dt_sim_cls: MagicMock
    ) -> None:
        """If DtSimulateLocation.clear() fails, state should remain active."""
        dm = _make_mock_device_manager()
        service = LocationService(dm)
        coord = Coordinate(latitude=25.0, longitude=121.0)

        service.set_location("d1", coord)
        mock_dt_sim_cls.return_value.clear.side_effect = OSError("fail")

        with pytest.raises(LocationClearError):
            service.clear_location("d1")

        # State should still show as active since clear failed
        assert service.is_simulation_active("d1") is True
        assert service.get_current_location("d1") is coord


# =====================================================================
# get_current_location
# =====================================================================

class TestGetCurrentLocation:
    """Tests for LocationService.get_current_location."""

    def test_returns_none_for_unknown_device(self) -> None:
        dm = _make_mock_device_manager()
        service = LocationService(dm)
        assert service.get_current_location("unknown") is None

    @patch(_PATCH_DT_SIM)
    def test_returns_coordinate_after_set(
        self, mock_dt_sim_cls: MagicMock
    ) -> None:
        dm = _make_mock_device_manager()
        service = LocationService(dm)
        coord = Coordinate(latitude=25.0, longitude=121.0)
        service.set_location("d1", coord)

        result = service.get_current_location("d1")
        assert result is coord


# =====================================================================
# is_simulation_active
# =====================================================================

class TestIsSimulationActive:
    """Tests for LocationService.is_simulation_active."""

    def test_false_for_unknown_device(self) -> None:
        dm = _make_mock_device_manager()
        service = LocationService(dm)
        assert service.is_simulation_active("unknown") is False


# =====================================================================
# cleanup_device
# =====================================================================

class TestCleanupDevice:
    """Tests for LocationService.cleanup_device."""

    @patch(_PATCH_DT_SIM)
    def test_cleanup_removes_all_state(
        self, mock_dt_sim_cls: MagicMock
    ) -> None:
        dm = _make_mock_device_manager()
        service = LocationService(dm)
        coord = Coordinate(latitude=25.0, longitude=121.0)
        service.set_location("d1", coord)

        service.cleanup_device("d1")

        assert service.get_current_location("d1") is None
        assert service.is_simulation_active("d1") is False

    def test_cleanup_unknown_device_does_not_raise(self) -> None:
        dm = _make_mock_device_manager()
        service = LocationService(dm)
        service.cleanup_device("nonexistent")  # should not raise

    @patch(_PATCH_DT_SIM)
    def test_cleanup_does_not_communicate_with_device(
        self, mock_dt_sim_cls: MagicMock
    ) -> None:
        """cleanup_device should only clear internal state."""
        dm = _make_mock_device_manager()
        service = LocationService(dm)
        coord = Coordinate(latitude=25.0, longitude=121.0)
        service.set_location("d1", coord)

        # Reset the mock to track only cleanup calls
        mock_dt_sim_cls.reset_mock()

        service.cleanup_device("d1")

        # DtSimulateLocation should NOT have been called during cleanup
        mock_dt_sim_cls.assert_not_called()


# =====================================================================
# get_status
# =====================================================================

class TestGetStatus:
    """Tests for LocationService.get_status."""

    def test_status_inactive_unknown_device(self) -> None:
        dm = _make_mock_device_manager()
        service = LocationService(dm)
        status = service.get_status("d1")

        assert status["udid"] == "d1"
        assert status["simulation_active"] is False
        assert status["current_location"] is None

    @patch(_PATCH_DT_SIM)
    def test_status_active_with_location(
        self, mock_dt_sim_cls: MagicMock
    ) -> None:
        dm = _make_mock_device_manager()
        service = LocationService(dm)
        coord = Coordinate(latitude=25.0, longitude=121.0)
        service.set_location("d1", coord)

        status = service.get_status("d1")
        assert status["udid"] == "d1"
        assert status["simulation_active"] is True
        assert status["current_location"] == {
            "latitude": 25.0,
            "longitude": 121.0,
        }

    @patch(_PATCH_DT_SIM)
    def test_status_after_clear(self, mock_dt_sim_cls: MagicMock) -> None:
        dm = _make_mock_device_manager()
        service = LocationService(dm)
        coord = Coordinate(latitude=25.0, longitude=121.0)
        service.set_location("d1", coord)
        service.clear_location("d1")

        status = service.get_status("d1")
        assert status["simulation_active"] is False
        assert status["current_location"] is None


# =====================================================================
# Thread safety
# =====================================================================

class TestThreadSafety:
    """Tests for concurrent access to LocationService."""

    @patch(_PATCH_DT_SIM)
    def test_concurrent_set_location_no_crash(
        self, mock_dt_sim_cls: MagicMock
    ) -> None:
        """Multiple threads setting location simultaneously should not crash."""
        dm = _make_mock_device_manager()
        service = LocationService(dm)
        errors: list[Exception] = []

        def worker(device_id: str, lat: float) -> None:
            try:
                for _ in range(50):
                    coord = Coordinate(latitude=lat, longitude=121.0)
                    service.set_location(device_id, coord)
            except Exception as exc:
                errors.append(exc)

        threads = [
            threading.Thread(target=worker, args=("d1", 25.0)),
            threading.Thread(target=worker, args=("d2", 35.0)),
            threading.Thread(target=worker, args=("d1", 30.0)),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10.0)

        assert len(errors) == 0, f"Errors occurred: {errors}"

    @patch(_PATCH_DT_SIM)
    def test_concurrent_set_and_clear(
        self, mock_dt_sim_cls: MagicMock
    ) -> None:
        """Interleaved set/clear should not corrupt state."""
        dm = _make_mock_device_manager()
        service = LocationService(dm)
        errors: list[Exception] = []

        def setter() -> None:
            try:
                for _ in range(50):
                    coord = Coordinate(latitude=25.0, longitude=121.0)
                    service.set_location("d1", coord)
            except Exception as exc:
                errors.append(exc)

        def clearer() -> None:
            try:
                for _ in range(50):
                    service.clear_location("d1")
            except Exception as exc:
                errors.append(exc)

        threads = [
            threading.Thread(target=setter),
            threading.Thread(target=clearer),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10.0)

        assert len(errors) == 0, f"Errors occurred: {errors}"


# =====================================================================
# Multiple devices
# =====================================================================

class TestMultipleDevices:
    """Tests for managing location state across multiple devices."""

    @patch(_PATCH_DT_SIM)
    def test_independent_device_state(
        self, mock_dt_sim_cls: MagicMock
    ) -> None:
        """Location state for different devices should be independent."""
        dm = _make_mock_device_manager()
        service = LocationService(dm)

        coord_a = Coordinate(latitude=25.0, longitude=121.0)
        coord_b = Coordinate(latitude=35.0, longitude=139.0)

        service.set_location("device_a", coord_a)
        service.set_location("device_b", coord_b)

        assert service.get_current_location("device_a") is coord_a
        assert service.get_current_location("device_b") is coord_b

        service.clear_location("device_a")
        assert service.get_current_location("device_a") is None
        assert service.get_current_location("device_b") is coord_b

    @patch(_PATCH_DT_SIM)
    def test_cleanup_one_device_does_not_affect_other(
        self, mock_dt_sim_cls: MagicMock
    ) -> None:
        dm = _make_mock_device_manager()
        service = LocationService(dm)

        coord = Coordinate(latitude=25.0, longitude=121.0)
        service.set_location("d1", coord)
        service.set_location("d2", coord)

        service.cleanup_device("d1")

        assert service.get_current_location("d1") is None
        assert service.get_current_location("d2") is coord


# =====================================================================
# DVT path (iOS 17+)
# =====================================================================

class TestDVTPath:
    """Tests for the DVT code path used by iOS 17+ devices.

    When get_ios_category returns IOSVersionCategory.TUNNEL, LocationService
    should use DvtSecureSocketProxyService + LocationSimulation instead of
    DtSimulateLocation.
    """

    @patch(_PATCH_LOC_SIM)
    @patch(_PATCH_DVT_PROXY)
    def test_set_location_dvt_success(
        self,
        mock_dvt_cls: MagicMock,
        mock_loc_sim_cls: MagicMock,
    ) -> None:
        """iOS 17+: set_location should use DVT + LocationSimulation."""
        mock_provider = MagicMock()
        dm = _make_mock_device_manager(
            service_provider=mock_provider,
            ios_category=IOSVersionCategory.TUNNEL,
        )

        # Set up DVT as context manager
        mock_dvt_instance = MagicMock()
        mock_dvt_cls.return_value.__enter__ = MagicMock(return_value=mock_dvt_instance)
        mock_dvt_cls.return_value.__exit__ = MagicMock(return_value=False)

        mock_loc_sim_instance = MagicMock()
        mock_loc_sim_cls.return_value = mock_loc_sim_instance

        service = LocationService(dm)
        coord = Coordinate(latitude=25.0330, longitude=121.5654)

        service.set_location("device1", coord)

        # DVT should have been created with the service provider
        mock_dvt_cls.assert_called_once_with(lockdown=mock_provider)
        # LocationSimulation should have been called on the DVT instance
        mock_loc_sim_cls.assert_called_once_with(mock_dvt_instance)
        mock_loc_sim_instance.set.assert_called_once_with(25.0330, 121.5654)

    @patch(_PATCH_LOC_SIM)
    @patch(_PATCH_DVT_PROXY)
    def test_set_location_dvt_updates_state(
        self,
        mock_dvt_cls: MagicMock,
        mock_loc_sim_cls: MagicMock,
    ) -> None:
        """DVT path should update internal state after successful set."""
        dm = _make_mock_device_manager(ios_category=IOSVersionCategory.TUNNEL)
        mock_dvt_instance = MagicMock()
        mock_dvt_cls.return_value.__enter__ = MagicMock(return_value=mock_dvt_instance)
        mock_dvt_cls.return_value.__exit__ = MagicMock(return_value=False)

        service = LocationService(dm)
        coord = Coordinate(latitude=10.0, longitude=20.0)

        service.set_location("d1", coord)

        assert service.get_current_location("d1") is coord
        assert service.is_simulation_active("d1") is True

    @patch(_PATCH_LOC_SIM)
    @patch(_PATCH_DVT_PROXY)
    def test_clear_location_dvt_success(
        self,
        mock_dvt_cls: MagicMock,
        mock_loc_sim_cls: MagicMock,
    ) -> None:
        """iOS 17+: clear_location should use DVT + LocationSimulation.clear."""
        mock_provider = MagicMock()
        dm = _make_mock_device_manager(
            service_provider=mock_provider,
            ios_category=IOSVersionCategory.TUNNEL,
        )
        mock_dvt_instance = MagicMock()
        mock_dvt_cls.return_value.__enter__ = MagicMock(return_value=mock_dvt_instance)
        mock_dvt_cls.return_value.__exit__ = MagicMock(return_value=False)

        mock_loc_sim_instance = MagicMock()
        mock_loc_sim_cls.return_value = mock_loc_sim_instance

        service = LocationService(dm)

        # Set then clear
        coord = Coordinate(latitude=25.0, longitude=121.0)
        service.set_location("d1", coord)
        service.clear_location("d1")

        mock_loc_sim_instance.clear.assert_called_once()
        assert service.is_simulation_active("d1") is False
        assert service.get_current_location("d1") is None

    @patch(_PATCH_LOC_SIM)
    @patch(_PATCH_DVT_PROXY)
    def test_dvt_error_raises_location_set_error(
        self,
        mock_dvt_cls: MagicMock,
        mock_loc_sim_cls: MagicMock,
    ) -> None:
        """DVT connection error should be wrapped in LocationSetError."""
        dm = _make_mock_device_manager(ios_category=IOSVersionCategory.TUNNEL)
        # DVT context manager raises on __enter__
        mock_dvt_cls.return_value.__enter__ = MagicMock(
            side_effect=ConnectionError("DVT channel failed")
        )
        mock_dvt_cls.return_value.__exit__ = MagicMock(return_value=False)

        service = LocationService(dm)
        coord = Coordinate(latitude=0.0, longitude=0.0)

        with pytest.raises(LocationSetError, match="DVT channel failed"):
            service.set_location("d1", coord)

    @patch(_PATCH_LOC_SIM)
    @patch(_PATCH_DVT_PROXY)
    def test_dvt_set_error_does_not_update_state(
        self,
        mock_dvt_cls: MagicMock,
        mock_loc_sim_cls: MagicMock,
    ) -> None:
        """If DVT set fails, internal state should not change."""
        dm = _make_mock_device_manager(ios_category=IOSVersionCategory.TUNNEL)
        mock_dvt_instance = MagicMock()
        mock_dvt_cls.return_value.__enter__ = MagicMock(return_value=mock_dvt_instance)
        mock_dvt_cls.return_value.__exit__ = MagicMock(return_value=False)
        mock_loc_sim_cls.return_value.set.side_effect = OSError("USB lost")

        service = LocationService(dm)
        coord = Coordinate(latitude=0.0, longitude=0.0)

        with pytest.raises(LocationSetError):
            service.set_location("d1", coord)

        assert service.get_current_location("d1") is None
        assert service.is_simulation_active("d1") is False

    @patch(_PATCH_LOC_SIM)
    @patch(_PATCH_DVT_PROXY)
    def test_dvt_clear_error_raises_location_clear_error(
        self,
        mock_dvt_cls: MagicMock,
        mock_loc_sim_cls: MagicMock,
    ) -> None:
        """DVT clear error should be wrapped in LocationClearError."""
        dm = _make_mock_device_manager(ios_category=IOSVersionCategory.TUNNEL)
        mock_dvt_instance = MagicMock()
        mock_dvt_cls.return_value.__enter__ = MagicMock(return_value=mock_dvt_instance)
        mock_dvt_cls.return_value.__exit__ = MagicMock(return_value=False)

        mock_loc_sim_instance = MagicMock()
        mock_loc_sim_cls.return_value = mock_loc_sim_instance

        service = LocationService(dm)

        # Set succeeds, clear fails
        coord = Coordinate(latitude=25.0, longitude=121.0)
        service.set_location("d1", coord)

        mock_loc_sim_instance.clear.side_effect = OSError("Connection lost")

        with pytest.raises(LocationClearError, match="Connection lost"):
            service.clear_location("d1")

        # State should still show active since clear failed
        assert service.is_simulation_active("d1") is True

    @patch(_PATCH_DT_SIM)
    def test_ddi_device_does_not_use_dvt(
        self,
        mock_dt_sim_cls: MagicMock,
    ) -> None:
        """iOS 16 (DDI) device should use DtSimulateLocation, NOT DVT."""
        dm = _make_mock_device_manager(ios_category=IOSVersionCategory.DDI)
        service = LocationService(dm)
        coord = Coordinate(latitude=25.0, longitude=121.0)

        with patch(_PATCH_DVT_PROXY) as mock_dvt_cls:
            service.set_location("d1", coord)

            # DtSimulateLocation should have been called
            mock_dt_sim_cls.assert_called_once()
            # DVT should NOT have been called
            mock_dvt_cls.assert_not_called()

    @patch(_PATCH_DT_SIM)
    def test_ios_category_fallback_to_ddi(
        self,
        mock_dt_sim_cls: MagicMock,
    ) -> None:
        """If get_ios_category raises, should fall back to DDI (DtSimulateLocation)."""
        dm = _make_mock_device_manager(ios_category=IOSVersionCategory.DDI)
        dm.get_ios_category.side_effect = Exception("Unknown device")

        service = LocationService(dm)
        coord = Coordinate(latitude=25.0, longitude=121.0)

        service.set_location("d1", coord)

        # Should have fallen back to DtSimulateLocation
        mock_dt_sim_cls.assert_called_once()
