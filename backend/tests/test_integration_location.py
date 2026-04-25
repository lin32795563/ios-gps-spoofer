"""Integration tests: DeviceManager + LocationService end-to-end.

These tests verify that LocationService correctly obtains service providers
from DeviceManager and sends location commands to the device layer.
Both iOS 16 (DDI path) and iOS 17+ (DVT path) are exercised.

Unlike the unit tests that mock DeviceManager entirely, these tests use
a real DeviceManager instance with only the pymobiledevice3 layer mocked.
This ensures the two modules integrate correctly.

Flow tested:
    Connect device -> Set location -> Verify state -> Clear location ->
    Verify state -> Set again -> Cleanup device -> Verify state cleared

iOS version routing:
    - iOS 14-16: DtSimulateLocation via lockdown client (DDI path)
    - iOS 17+: DvtSecureSocketProxyService + LocationSimulation via tunneld RSD (DVT path)
"""

from unittest.mock import MagicMock, patch

import pytest

from ios_gps_spoofer.device.device_manager import DeviceManager
from ios_gps_spoofer.device.models import ConnectionState
from ios_gps_spoofer.location.coordinates import Coordinate
from ios_gps_spoofer.location.exceptions import (
    LocationServiceNotReadyError,
    LocationSetError,
)
from ios_gps_spoofer.location.location_service import LocationService

# Reuse helpers from device manager tests
from tests.test_device_manager import (
    TunnelMockContext,
    _make_mock_lockdown,
    _make_mock_mux_device,
)

_PATCH_ENUM = "ios_gps_spoofer.device.device_manager.DeviceManager._enumerate_usbmux_devices"
_PATCH_CREATE = "ios_gps_spoofer.device.device_manager.create_using_usbmux"
_PATCH_MOUNTER = "pymobiledevice3.services.mobile_image_mounter.MobileImageMounterService"
_PATCH_DT_SIM = "pymobiledevice3.services.simulate_location.DtSimulateLocation"
_PATCH_DVT_PROXY = "pymobiledevice3.services.dvt.dvt_secure_socket_proxy.DvtSecureSocketProxyService"
_PATCH_LOC_SIM = "pymobiledevice3.services.dvt.instruments.location_simulation.LocationSimulation"


class TestIntegrationIOS16:
    """Integration tests for the iOS 16 (DDI) code path."""

    @patch(_PATCH_DT_SIM)
    @patch(_PATCH_MOUNTER)
    @patch(_PATCH_CREATE)
    @patch(_PATCH_ENUM)
    def test_full_lifecycle_set_clear_set_cleanup(
        self,
        mock_enum: MagicMock,
        mock_create: MagicMock,
        mock_mounter_cls: MagicMock,
        mock_dt_sim_cls: MagicMock,
    ) -> None:
        """Complete lifecycle: connect -> set -> clear -> set -> cleanup."""
        udid = "ios16-integration"
        mock_lockdown = _make_mock_lockdown("16.7.4")
        mock_enum.return_value = [_make_mock_mux_device(udid)]
        mock_create.return_value = mock_lockdown

        mock_mounter = MagicMock()
        mock_mounter.is_image_mounted.return_value = True
        mock_mounter_cls.return_value = mock_mounter

        manager = DeviceManager()
        location_service = LocationService(manager)

        # Step 1: Connect device
        conn = manager.connect_device(udid=udid)
        assert conn.state == ConnectionState.READY

        # Step 2: Set location
        coord = Coordinate(latitude=25.0330, longitude=121.5654)
        location_service.set_location(udid, coord)

        mock_dt_sim_cls.assert_called_with(mock_lockdown)
        mock_dt_sim_cls.return_value.set.assert_called_with(25.0330, 121.5654)
        assert location_service.is_simulation_active(udid) is True
        assert location_service.get_current_location(udid) is coord

        # Step 3: Get status
        status = location_service.get_status(udid)
        assert status["simulation_active"] is True
        assert status["current_location"] == {
            "latitude": 25.0330,
            "longitude": 121.5654,
        }

        # Step 4: Clear location
        location_service.clear_location(udid)

        mock_dt_sim_cls.return_value.clear.assert_called_once()
        assert location_service.is_simulation_active(udid) is False
        assert location_service.get_current_location(udid) is None

        # Step 5: Set location again with different coords
        coord2 = Coordinate(latitude=35.6762, longitude=139.6503)
        location_service.set_location(udid, coord2)

        assert location_service.get_current_location(udid) is coord2
        assert location_service.is_simulation_active(udid) is True

        # Step 6: Cleanup device state (simulating disconnect)
        location_service.cleanup_device(udid)

        assert location_service.get_current_location(udid) is None
        assert location_service.is_simulation_active(udid) is False

    @patch(_PATCH_DT_SIM)
    @patch(_PATCH_MOUNTER)
    @patch(_PATCH_CREATE)
    @patch(_PATCH_ENUM)
    def test_set_location_after_device_disconnect_raises(
        self,
        mock_enum: MagicMock,
        mock_create: MagicMock,
        mock_mounter_cls: MagicMock,
        mock_dt_sim_cls: MagicMock,
    ) -> None:
        """After disconnecting a device, set_location should fail gracefully."""
        udid = "ios16-disconnect"
        mock_lockdown = _make_mock_lockdown("16.7.4")
        mock_enum.return_value = [_make_mock_mux_device(udid)]
        mock_create.return_value = mock_lockdown

        mock_mounter = MagicMock()
        mock_mounter.is_image_mounted.return_value = True
        mock_mounter_cls.return_value = mock_mounter

        manager = DeviceManager()
        location_service = LocationService(manager)

        # Connect and set location
        manager.connect_device(udid=udid)
        coord = Coordinate(latitude=25.0, longitude=121.0)
        location_service.set_location(udid, coord)
        assert location_service.is_simulation_active(udid) is True

        # Disconnect
        manager.disconnect_device(udid)

        # Now set_location should fail because device is gone
        with pytest.raises(LocationServiceNotReadyError):
            location_service.set_location(udid, coord)

    @patch(_PATCH_DT_SIM)
    @patch(_PATCH_MOUNTER)
    @patch(_PATCH_CREATE)
    @patch(_PATCH_ENUM)
    def test_clear_location_after_device_disconnect_raises(
        self,
        mock_enum: MagicMock,
        mock_create: MagicMock,
        mock_mounter_cls: MagicMock,
        mock_dt_sim_cls: MagicMock,
    ) -> None:
        """After disconnecting, clear_location should also fail gracefully."""
        udid = "ios16-disconnect-clear"
        mock_lockdown = _make_mock_lockdown("16.7.4")
        mock_enum.return_value = [_make_mock_mux_device(udid)]
        mock_create.return_value = mock_lockdown

        mock_mounter = MagicMock()
        mock_mounter.is_image_mounted.return_value = True
        mock_mounter_cls.return_value = mock_mounter

        manager = DeviceManager()
        location_service = LocationService(manager)

        manager.connect_device(udid=udid)
        coord = Coordinate(latitude=25.0, longitude=121.0)
        location_service.set_location(udid, coord)

        manager.disconnect_device(udid)

        with pytest.raises(LocationServiceNotReadyError):
            location_service.clear_location(udid)

    @patch(_PATCH_DT_SIM)
    @patch(_PATCH_MOUNTER)
    @patch(_PATCH_CREATE)
    @patch(_PATCH_ENUM)
    def test_device_error_during_set_preserves_internal_state(
        self,
        mock_enum: MagicMock,
        mock_create: MagicMock,
        mock_mounter_cls: MagicMock,
        mock_dt_sim_cls: MagicMock,
    ) -> None:
        """If DtSimulateLocation.set() fails, LocationService internal
        state should not be corrupted."""
        udid = "ios16-error"
        mock_lockdown = _make_mock_lockdown("16.7.4")
        mock_enum.return_value = [_make_mock_mux_device(udid)]
        mock_create.return_value = mock_lockdown

        mock_mounter = MagicMock()
        mock_mounter.is_image_mounted.return_value = True
        mock_mounter_cls.return_value = mock_mounter

        manager = DeviceManager()
        location_service = LocationService(manager)

        manager.connect_device(udid=udid)

        # First set succeeds
        coord1 = Coordinate(latitude=25.0, longitude=121.0)
        location_service.set_location(udid, coord1)
        assert location_service.get_current_location(udid) is coord1

        # Second set fails (device error)
        mock_dt_sim_cls.return_value.set.side_effect = OSError("USB disconnected")
        coord2 = Coordinate(latitude=35.0, longitude=139.0)

        with pytest.raises(LocationSetError, match="USB disconnected"):
            location_service.set_location(udid, coord2)

        # Internal state should still reflect the first successful set
        assert location_service.get_current_location(udid) is coord1
        assert location_service.is_simulation_active(udid) is True


class TestIntegrationIOS17:
    """Integration tests for the iOS 17+ (DVT) code path.

    iOS 17+ uses DvtSecureSocketProxyService + LocationSimulation instead of
    DtSimulateLocation.  The RSD (from tunneld) is passed to the DVT service.
    """

    @patch(_PATCH_LOC_SIM)
    @patch(_PATCH_DVT_PROXY)
    @patch(_PATCH_CREATE)
    @patch(_PATCH_ENUM)
    def test_full_lifecycle_set_clear(
        self,
        mock_enum: MagicMock,
        mock_create: MagicMock,
        mock_dvt_cls: MagicMock,
        mock_loc_sim_cls: MagicMock,
    ) -> None:
        """iOS 17+: connect via tunneld -> set (DVT) -> clear (DVT) -> disconnect."""
        udid = "ios17-integration"
        mock_enum.return_value = [_make_mock_mux_device(udid)]
        mock_create.return_value = _make_mock_lockdown("17.2.1")

        # Set up DVT mock as context manager
        mock_dvt_instance = MagicMock()
        mock_dvt_cls.return_value.__enter__ = MagicMock(return_value=mock_dvt_instance)
        mock_dvt_cls.return_value.__exit__ = MagicMock(return_value=False)

        mock_loc_sim_instance = MagicMock()
        mock_loc_sim_cls.return_value = mock_loc_sim_instance

        with TunnelMockContext() as ctx:
            manager = DeviceManager()
            location_service = LocationService(manager)

            # Connect device (uses tunneld for iOS 17+)
            conn = manager.connect_device(udid=udid)
            assert conn.state == ConnectionState.READY

            # Set location -- should use DVT path with RSD
            coord = Coordinate(latitude=48.8566, longitude=2.3522)
            location_service.set_location(udid, coord)

            # Verify DVT service was created with RSD as the lockdown provider
            mock_dvt_cls.assert_called_with(lockdown=ctx.mock_rsd)
            # Verify LocationSimulation was called on the DVT instance
            mock_loc_sim_cls.assert_called_with(mock_dvt_instance)
            mock_loc_sim_instance.set.assert_called_with(48.8566, 2.3522)
            assert location_service.is_simulation_active(udid) is True

            # Clear location (also uses DVT)
            mock_loc_sim_cls.reset_mock()
            mock_dvt_cls.reset_mock()
            mock_dvt_cls.return_value.__enter__ = MagicMock(return_value=mock_dvt_instance)
            mock_dvt_cls.return_value.__exit__ = MagicMock(return_value=False)

            location_service.clear_location(udid)
            mock_loc_sim_instance.clear.assert_called_once()
            assert location_service.is_simulation_active(udid) is False

            # Clean disconnect
            location_service.cleanup_device(udid)
            manager.disconnect_all()

    @patch(_PATCH_LOC_SIM)
    @patch(_PATCH_DVT_PROXY)
    @patch(_PATCH_CREATE)
    @patch(_PATCH_ENUM)
    def test_set_location_uses_dvt_not_dt_sim(
        self,
        mock_enum: MagicMock,
        mock_create: MagicMock,
        mock_dvt_cls: MagicMock,
        mock_loc_sim_cls: MagicMock,
    ) -> None:
        """Verify that iOS 17+ routes through DVT, not DtSimulateLocation."""
        udid = "ios17-dvt-verify"
        mock_lockdown = _make_mock_lockdown("17.0")
        mock_enum.return_value = [_make_mock_mux_device(udid)]
        mock_create.return_value = mock_lockdown

        # Set up DVT mock
        mock_dvt_instance = MagicMock()
        mock_dvt_cls.return_value.__enter__ = MagicMock(return_value=mock_dvt_instance)
        mock_dvt_cls.return_value.__exit__ = MagicMock(return_value=False)

        with (
            TunnelMockContext() as ctx,
            patch(_PATCH_DT_SIM) as mock_dt_sim_cls,
        ):
            manager = DeviceManager()
            location_service = LocationService(manager)

            manager.connect_device(udid=udid)

            coord = Coordinate(latitude=0.0, longitude=0.0)
            location_service.set_location(udid, coord)

            # DVT service should have been used (not DtSimulateLocation)
            mock_dvt_cls.assert_called_with(lockdown=ctx.mock_rsd)
            # DtSimulateLocation should NOT have been called
            mock_dt_sim_cls.assert_not_called()

            manager.disconnect_all()

    @patch(_PATCH_LOC_SIM)
    @patch(_PATCH_DVT_PROXY)
    @patch(_PATCH_CREATE)
    @patch(_PATCH_ENUM)
    def test_ios26_device_set_clear_lifecycle(
        self,
        mock_enum: MagicMock,
        mock_create: MagicMock,
        mock_dvt_cls: MagicMock,
        mock_loc_sim_cls: MagicMock,
    ) -> None:
        """iOS 26.2.1 (iPhone 17 Pro): connect via tunneld, set/clear via DVT."""
        udid = "00008150-001E58A83428401C"
        mock_enum.return_value = [_make_mock_mux_device(udid)]
        mock_create.return_value = _make_mock_lockdown("26.2.1")

        # Set up DVT mock
        mock_dvt_instance = MagicMock()
        mock_dvt_cls.return_value.__enter__ = MagicMock(return_value=mock_dvt_instance)
        mock_dvt_cls.return_value.__exit__ = MagicMock(return_value=False)

        mock_loc_sim_instance = MagicMock()
        mock_loc_sim_cls.return_value = mock_loc_sim_instance

        with TunnelMockContext(udid=udid, product_version="26.2.1") as ctx:
            manager = DeviceManager()
            location_service = LocationService(manager)

            conn = manager.connect_device(udid=udid)
            assert conn.state == ConnectionState.READY
            assert conn.device_info.product_version == "26.2.1"

            # Set location
            coord = Coordinate(latitude=25.0330, longitude=121.5654)
            location_service.set_location(udid, coord)

            mock_dvt_cls.assert_called_with(lockdown=ctx.mock_rsd)
            mock_loc_sim_instance.set.assert_called_with(25.0330, 121.5654)

            # Clear location
            location_service.clear_location(udid)
            mock_loc_sim_instance.clear.assert_called_once()

            manager.disconnect_all()


class TestIntegrationMultiDevice:
    """Integration tests for managing multiple devices simultaneously."""

    @patch(_PATCH_DT_SIM)
    @patch(_PATCH_MOUNTER)
    @patch(_PATCH_CREATE)
    @patch(_PATCH_ENUM)
    def test_two_ios16_devices_independent_locations(
        self,
        mock_enum: MagicMock,
        mock_create: MagicMock,
        mock_mounter_cls: MagicMock,
        mock_dt_sim_cls: MagicMock,
    ) -> None:
        """Two devices can have independent simulated locations."""
        udid_a = "device-a"
        udid_b = "device-b"

        mock_lockdown_a = _make_mock_lockdown("16.7.4")
        mock_lockdown_b = _make_mock_lockdown("16.5")

        # Create per-device return values
        mock_create.side_effect = [mock_lockdown_a, mock_lockdown_b]
        mock_enum.return_value = [
            _make_mock_mux_device(udid_a),
            _make_mock_mux_device(udid_b),
        ]

        mock_mounter = MagicMock()
        mock_mounter.is_image_mounted.return_value = True
        mock_mounter_cls.return_value = mock_mounter

        manager = DeviceManager()
        location_service = LocationService(manager)

        # Connect both devices
        manager.connect_device(udid=udid_a)
        manager.connect_device(udid=udid_b)

        # Set different locations on each device
        coord_a = Coordinate(latitude=25.0, longitude=121.0)
        coord_b = Coordinate(latitude=35.0, longitude=139.0)

        location_service.set_location(udid_a, coord_a)
        location_service.set_location(udid_b, coord_b)

        assert location_service.get_current_location(udid_a) is coord_a
        assert location_service.get_current_location(udid_b) is coord_b

        # Clear only device A
        location_service.clear_location(udid_a)
        assert location_service.get_current_location(udid_a) is None
        assert location_service.get_current_location(udid_b) is coord_b
        assert location_service.is_simulation_active(udid_a) is False
        assert location_service.is_simulation_active(udid_b) is True


class TestIntegrationEdgeCases:
    """Edge case integration tests."""

    def test_set_location_without_connecting_first(self) -> None:
        """Attempting to set location on an unconnected device should fail."""
        manager = DeviceManager()
        location_service = LocationService(manager)

        coord = Coordinate(latitude=25.0, longitude=121.0)
        with pytest.raises(LocationServiceNotReadyError):
            location_service.set_location("nonexistent", coord)

    def test_clear_location_without_connecting_first(self) -> None:
        """Attempting to clear location on an unconnected device should fail."""
        manager = DeviceManager()
        location_service = LocationService(manager)

        with pytest.raises(LocationServiceNotReadyError):
            location_service.clear_location("nonexistent")

    @patch(_PATCH_DT_SIM)
    @patch(_PATCH_MOUNTER)
    @patch(_PATCH_CREATE)
    @patch(_PATCH_ENUM)
    def test_rapid_set_location_updates(
        self,
        mock_enum: MagicMock,
        mock_create: MagicMock,
        mock_mounter_cls: MagicMock,
        mock_dt_sim_cls: MagicMock,
    ) -> None:
        """Rapid sequential location updates should all succeed."""
        udid = "rapid-test"
        mock_lockdown = _make_mock_lockdown("16.7.4")
        mock_enum.return_value = [_make_mock_mux_device(udid)]
        mock_create.return_value = mock_lockdown

        mock_mounter = MagicMock()
        mock_mounter.is_image_mounted.return_value = True
        mock_mounter_cls.return_value = mock_mounter

        manager = DeviceManager()
        location_service = LocationService(manager)
        manager.connect_device(udid=udid)

        # Simulate 100 rapid location updates (like a path simulation)
        for i in range(100):
            lat = 25.0 + (i * 0.001)
            lon = 121.0 + (i * 0.001)
            coord = Coordinate(latitude=lat, longitude=lon)
            location_service.set_location(udid, coord)

        # The last location should be reflected
        final_coord = location_service.get_current_location(udid)
        assert final_coord is not None
        assert final_coord.latitude == pytest.approx(25.099, abs=0.001)
        assert final_coord.longitude == pytest.approx(121.099, abs=0.001)

        # DtSimulateLocation.set should have been called 100 times
        assert mock_dt_sim_cls.return_value.set.call_count == 100

    @patch(_PATCH_DT_SIM)
    @patch(_PATCH_MOUNTER)
    @patch(_PATCH_CREATE)
    @patch(_PATCH_ENUM)
    def test_status_reflects_real_time_state(
        self,
        mock_enum: MagicMock,
        mock_create: MagicMock,
        mock_mounter_cls: MagicMock,
        mock_dt_sim_cls: MagicMock,
    ) -> None:
        """get_status should accurately reflect the current state at each step."""
        udid = "status-test"
        mock_lockdown = _make_mock_lockdown("16.7.4")
        mock_enum.return_value = [_make_mock_mux_device(udid)]
        mock_create.return_value = mock_lockdown

        mock_mounter = MagicMock()
        mock_mounter.is_image_mounted.return_value = True
        mock_mounter_cls.return_value = mock_mounter

        manager = DeviceManager()
        location_service = LocationService(manager)
        manager.connect_device(udid=udid)

        # Before any location is set
        status = location_service.get_status(udid)
        assert status["simulation_active"] is False
        assert status["current_location"] is None

        # After set
        coord = Coordinate(latitude=25.0330, longitude=121.5654)
        location_service.set_location(udid, coord)
        status = location_service.get_status(udid)
        assert status["simulation_active"] is True
        assert status["current_location"]["latitude"] == 25.0330  # type: ignore[index]
        assert status["current_location"]["longitude"] == 121.5654  # type: ignore[index]

        # After clear
        location_service.clear_location(udid)
        status = location_service.get_status(udid)
        assert status["simulation_active"] is False
        assert status["current_location"] is None

        # After cleanup
        location_service.cleanup_device(udid)
        status = location_service.get_status(udid)
        assert status["simulation_active"] is False
        assert status["current_location"] is None
