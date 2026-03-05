"""Tests for DeviceManager.get_service_provider method.

This verifies the service provider abstraction that routes to either
LockdownClient (iOS <=16) or RemoteServiceDiscoveryService (iOS 17+).
"""

from unittest.mock import MagicMock, patch

import pytest

from ios_gps_spoofer.device.device_manager import DeviceManager
from ios_gps_spoofer.device.exceptions import (
    DeviceConnectionError,
    DeviceNotFoundError,
)
from ios_gps_spoofer.device.models import ConnectionState, IOSVersionCategory

# Reuse test helpers from test_device_manager
from tests.test_device_manager import (
    TunnelMockContext,
    _make_mock_lockdown,
    _make_mock_mux_device,
)

_PATCH_ENUM = "ios_gps_spoofer.device.device_manager.DeviceManager._enumerate_usb_devices"
_PATCH_CREATE = "ios_gps_spoofer.device.device_manager.create_using_usbmux"
_PATCH_MOUNTER = "pymobiledevice3.services.mobile_image_mounter.MobileImageMounterService"


class TestGetServiceProvider:
    """Tests for DeviceManager.get_service_provider."""

    def test_unknown_device_raises_not_found(self) -> None:
        manager = DeviceManager()
        with pytest.raises(DeviceNotFoundError, match="nonexistent"):
            manager.get_service_provider("nonexistent")

    @patch(_PATCH_MOUNTER)
    @patch(_PATCH_CREATE)
    @patch(_PATCH_ENUM)
    def test_ios16_returns_lockdown_client(
        self,
        mock_enum: MagicMock,
        mock_create: MagicMock,
        mock_mounter_cls: MagicMock,
    ) -> None:
        """For iOS 16 (DDI path), get_service_provider returns LockdownClient."""
        mock_lockdown = _make_mock_lockdown("16.7.4")
        mock_enum.return_value = [_make_mock_mux_device("ios16")]
        mock_create.return_value = mock_lockdown
        mock_mounter = MagicMock()
        mock_mounter.is_image_mounted.return_value = True
        mock_mounter_cls.return_value = mock_mounter

        manager = DeviceManager()
        conn = manager.connect_device(udid="ios16")
        assert conn.state == ConnectionState.READY

        provider = manager.get_service_provider("ios16")
        assert provider is mock_lockdown

    @patch(_PATCH_CREATE)
    @patch(_PATCH_ENUM)
    def test_ios17_returns_rsd(
        self,
        mock_enum: MagicMock,
        mock_create: MagicMock,
    ) -> None:
        """For iOS 17+ (tunnel path), get_service_provider returns the RSD."""
        mock_enum.return_value = [_make_mock_mux_device("ios17")]
        mock_create.return_value = _make_mock_lockdown("17.2.1")

        with TunnelMockContext() as ctx:
            manager = DeviceManager()
            conn = manager.connect_device(udid="ios17")
            assert conn.state == ConnectionState.READY

            provider = manager.get_service_provider("ios17")
            assert provider is ctx.mock_rsd
            manager.disconnect_all()

    @patch(_PATCH_CREATE)
    @patch(_PATCH_ENUM)
    def test_device_not_ready_raises_connection_error(
        self,
        mock_enum: MagicMock,
        mock_create: MagicMock,
    ) -> None:
        """If device is connected but not READY, should raise."""
        mock_enum.return_value = [_make_mock_mux_device("d1")]
        mock_create.return_value = _make_mock_lockdown("17.0")

        manager = DeviceManager()
        # Manually add a connection in non-ready state
        from ios_gps_spoofer.device.models import DeviceConnection, DeviceInfo

        device_info = DeviceInfo(
            udid="d1",
            name="Test",
            product_type="iPhone16,1",
            product_version="17.0",
            build_version="21A",
            chip_id=0,
            hardware_model="D83AP",
        )
        connection = DeviceConnection(
            device_info=device_info,
            state=ConnectionState.CONNECTING,
            ios_category=IOSVersionCategory.TUNNEL,
        )
        manager._connections["d1"] = connection

        with pytest.raises(DeviceConnectionError, match="not ready"):
            manager.get_service_provider("d1")

    @patch(_PATCH_MOUNTER)
    @patch(_PATCH_CREATE)
    @patch(_PATCH_ENUM)
    def test_ios16_lockdown_missing_raises(
        self,
        mock_enum: MagicMock,
        mock_create: MagicMock,
        mock_mounter_cls: MagicMock,
    ) -> None:
        """If iOS 16 device is READY but lockdown was somehow lost, raise."""
        mock_lockdown = _make_mock_lockdown("16.7.4")
        mock_enum.return_value = [_make_mock_mux_device("d1")]
        mock_create.return_value = mock_lockdown
        mock_mounter = MagicMock()
        mock_mounter.is_image_mounted.return_value = True
        mock_mounter_cls.return_value = mock_mounter

        manager = DeviceManager()
        manager.connect_device(udid="d1")

        # Simulate lockdown being lost
        manager._lockdown_clients.pop("d1", None)

        with pytest.raises(DeviceConnectionError, match="not available"):
            manager.get_service_provider("d1")

    @patch(_PATCH_CREATE)
    @patch(_PATCH_ENUM)
    def test_ios17_rsd_missing_raises(
        self,
        mock_enum: MagicMock,
        mock_create: MagicMock,
    ) -> None:
        """If iOS 17 device is READY but RSD was somehow lost, raise."""
        mock_enum.return_value = [_make_mock_mux_device("d1")]
        mock_create.return_value = _make_mock_lockdown("17.0")

        with TunnelMockContext():
            manager = DeviceManager()
            manager.connect_device(udid="d1")

            # Simulate RSD being lost
            manager._rsd_services.pop("d1", None)

            with pytest.raises(
                DeviceConnectionError, match="RemoteServiceDiscoveryService"
            ):
                manager.get_service_provider("d1")
            manager.disconnect_all()
