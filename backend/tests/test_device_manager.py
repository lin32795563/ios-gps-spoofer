"""Tests for ios_gps_spoofer.device.device_manager module.

All pymobiledevice3 interactions are mocked since tests run without a real
iOS device.  Tests cover:

- Device enumeration (USB filtering, error handling)
- Lockdown client creation (pairing, connection errors)
- Device info reading
- iOS version routing (DDI path for iOS 14-16, tunneld path for iOS 17+)
- Polling lifecycle (start/stop, new device detection, removal detection)
- Callback invocation
- Concurrent access safety
- Resource cleanup
- Service provider abstraction (iOS <=16 lockdown vs iOS 17+ RSD)
- Windows driver check
- Tunneld API integration

Patch target conventions:
- ``usbmux_list_devices`` and ``create_using_usbmux`` are imported at module
  level in device_manager.py, so we patch them in that namespace.
- ``MobileImageMounterService`` is imported locally inside methods, so we
  patch it at its source package (pymobiledevice3.*).
- ``get_tunneld_devices`` and ``get_tunneld_device_by_udid`` are imported
  locally, so we patch at their source (pymobiledevice3.tunneld.api.*).
"""

import threading
import time
from unittest.mock import MagicMock, PropertyMock, patch

import pytest

from ios_gps_spoofer.device.device_manager import DeviceManager
from ios_gps_spoofer.device.exceptions import (
    DeviceConnectionError,
    DeviceNotFoundError,
    DevicePairingError,
    TunnelError,
    UnsupportedIOSVersionError,
)
from ios_gps_spoofer.device.models import ConnectionState, IOSVersionCategory

# Patch targets
_PATCH_ENUM = "ios_gps_spoofer.device.device_manager.DeviceManager._enumerate_usb_devices"
_PATCH_CREATE = "ios_gps_spoofer.device.device_manager.create_using_usbmux"
_PATCH_LIST = "ios_gps_spoofer.device.device_manager.usbmux_list_devices"
_PATCH_MOUNTER = "pymobiledevice3.services.mobile_image_mounter.MobileImageMounterService"
_PATCH_TUNNELD_DEVICES = "pymobiledevice3.tunneld.api.get_tunneld_devices"
_PATCH_TUNNELD_BY_UDID = "pymobiledevice3.tunneld.api.get_tunneld_device_by_udid"


def _make_mock_mux_device(serial: str, is_usb: bool = True) -> MagicMock:
    """Create a mock MuxDevice with given serial and connection type."""
    device = MagicMock()
    device.serial = serial
    type(device).is_usb = PropertyMock(return_value=is_usb)
    return device


def _make_mock_lockdown(product_version: str = "17.2.1") -> MagicMock:
    """Create a mock LockdownClient that returns realistic device values."""
    lockdown = MagicMock()
    lockdown.get_value.return_value = {
        "DeviceName": "Test iPhone",
        "ProductType": "iPhone16,1",
        "ProductVersion": product_version,
        "BuildVersion": "21C66",
        "ChipID": 33056,
        "HardwareModel": "D83AP",
        "DeviceClass": "iPhone",
    }
    type(lockdown).developer_mode_status = PropertyMock(return_value=True)
    return lockdown


def _make_mock_rsd(udid: str = "mock-udid", product_version: str = "17.2.1") -> MagicMock:
    """Create a mock RemoteServiceDiscoveryService (as returned by tunneld).

    The mock simulates the RSD's ``peer_info`` attribute which provides
    device metadata.
    """
    rsd = MagicMock()
    rsd.peer_info = {
        "UDID": udid,
        "DeviceName": "Test iPhone",
        "ProductType": "iPhone16,1",
        "ProductVersion": product_version,
        "BuildVersion": "21C66",
        "ChipID": 33056,
        "HardwareModel": "D83AP",
        "DeviceClass": "iPhone",
    }
    return rsd


class TunneldMockContext:
    """Context manager that mocks tunneld API for iOS 17+ device tests.

    Replaces the old TunnelMockContext (which mocked self-managed tunnels)
    with mocks for the tunneld HTTP API functions.

    Usage::

        with TunneldMockContext(udid="d1") as ctx:
            manager.connect_device(udid="d1")
            assert ctx.mock_rsd is not None
    """

    def __init__(
        self,
        udid: str = "mock-udid",
        product_version: str = "17.2.1",
    ) -> None:
        self._udid = udid
        self._product_version = product_version
        self.mock_rsd = _make_mock_rsd(udid, product_version)
        self._active_patches: list = []

    def __enter__(self) -> "TunneldMockContext":
        # Mock get_tunneld_device_by_udid to return our mock RSD
        p1 = patch(
            _PATCH_TUNNELD_BY_UDID,
            return_value=self.mock_rsd,
        )
        # Mock get_tunneld_devices to return [mock_rsd]
        p2 = patch(
            _PATCH_TUNNELD_DEVICES,
            return_value=[self.mock_rsd],
        )
        for p in [p1, p2]:
            p.start()
            self._active_patches.append(p)
        return self

    def __exit__(self, *args: object) -> None:
        for p in reversed(self._active_patches):
            p.stop()
        self._active_patches.clear()


# Keep backward-compatible alias for other test files
TunnelMockContext = TunneldMockContext


# =====================================================================
# Constructor
# =====================================================================

class TestDeviceManagerInit:
    """Tests for DeviceManager.__init__."""

    def test_default_construction(self) -> None:
        manager = DeviceManager()
        assert manager.is_polling is False
        assert manager.list_connected_devices() == []

    def test_custom_poll_interval(self) -> None:
        manager = DeviceManager(poll_interval=5.0)
        assert manager._poll_interval == 5.0

    def test_zero_poll_interval_raises(self) -> None:
        with pytest.raises(ValueError, match="poll_interval must be positive"):
            DeviceManager(poll_interval=0)

    def test_negative_poll_interval_raises(self) -> None:
        with pytest.raises(ValueError, match="poll_interval must be positive"):
            DeviceManager(poll_interval=-1.0)

    def test_zero_timeout_raises(self) -> None:
        with pytest.raises(ValueError, match="connection_timeout must be positive"):
            DeviceManager(connection_timeout=0)


# =====================================================================
# USB Enumeration
# =====================================================================

class TestEnumerateUsbDevices:
    """Tests for _enumerate_usb_devices static method."""

    @patch(_PATCH_LIST)
    def test_returns_usb_only_devices(self, mock_list: MagicMock) -> None:
        usb_dev = _make_mock_mux_device("aaa", is_usb=True)
        wifi_dev = _make_mock_mux_device("bbb", is_usb=False)
        mock_list.return_value = [usb_dev, wifi_dev]

        result = DeviceManager._enumerate_usb_devices()
        assert len(result) == 1
        assert result[0].serial == "aaa"

    @patch(_PATCH_LIST)
    def test_returns_empty_when_no_devices(self, mock_list: MagicMock) -> None:
        mock_list.return_value = []
        result = DeviceManager._enumerate_usb_devices()
        assert result == []

    @patch(_PATCH_LIST)
    def test_mux_exception_raises_device_connection_error(
        self, mock_list: MagicMock
    ) -> None:
        from pymobiledevice3.exceptions import MuxException

        mock_list.side_effect = MuxException()
        with pytest.raises(DeviceConnectionError, match="usbmux"):
            DeviceManager._enumerate_usb_devices()

    @patch(_PATCH_LIST)
    def test_os_error_raises_device_connection_error(
        self, mock_list: MagicMock
    ) -> None:
        mock_list.side_effect = OSError("connection refused")
        with pytest.raises(DeviceConnectionError):
            DeviceManager._enumerate_usb_devices()


# =====================================================================
# Connect Device
# =====================================================================

class TestConnectDevice:
    """Tests for connect_device and _connect_single_device."""

    @patch(_PATCH_TUNNELD_BY_UDID, return_value=None)
    @patch(_PATCH_TUNNELD_DEVICES, return_value=[])
    @patch(_PATCH_ENUM)
    def test_connect_no_devices_raises_not_found(
        self, mock_enum: MagicMock, _td: MagicMock, _tbu: MagicMock
    ) -> None:
        mock_enum.return_value = []
        manager = DeviceManager()
        with pytest.raises(DeviceNotFoundError):
            manager.connect_device()

    @patch(_PATCH_TUNNELD_BY_UDID, return_value=None)
    @patch(_PATCH_ENUM)
    def test_connect_specific_udid_not_found(
        self, mock_enum: MagicMock, _tbu: MagicMock
    ) -> None:
        mock_enum.return_value = [_make_mock_mux_device("aaa")]
        manager = DeviceManager()
        with pytest.raises(DeviceNotFoundError, match="bbb"):
            manager.connect_device(udid="bbb")

    @patch(_PATCH_CREATE)
    @patch(_PATCH_ENUM)
    def test_connect_ios17_device_via_tunneld(
        self,
        mock_enum: MagicMock,
        mock_create: MagicMock,
    ) -> None:
        """iOS 17+ device found on USB should redirect to tunneld."""
        mock_enum.return_value = [_make_mock_mux_device("udid17")]
        mock_create.return_value = _make_mock_lockdown("17.2.1")

        with TunneldMockContext(udid="udid17") as ctx:
            manager = DeviceManager()
            conn = manager.connect_device(udid="udid17")

            assert conn.udid == "udid17"
            assert conn.state == ConnectionState.READY
            assert conn.ios_category == IOSVersionCategory.TUNNEL
            # Lockdown should have been closed since tunneld is used
            mock_create.return_value.close.assert_called_once()
            # RSD from tunneld should be stored
            assert manager._rsd_services.get("udid17") is ctx.mock_rsd

    @patch(_PATCH_MOUNTER)
    @patch(_PATCH_CREATE)
    @patch(_PATCH_ENUM)
    def test_connect_ios16_device_ddi_already_mounted(
        self,
        mock_enum: MagicMock,
        mock_create: MagicMock,
        mock_mounter_cls: MagicMock,
    ) -> None:
        """iOS 16 device where DDI is already mounted should reach READY."""
        mock_enum.return_value = [_make_mock_mux_device("udid16")]
        mock_create.return_value = _make_mock_lockdown("16.7.4")
        mock_mounter = MagicMock()
        mock_mounter.is_image_mounted.return_value = True
        mock_mounter_cls.return_value = mock_mounter

        manager = DeviceManager()
        conn = manager.connect_device(udid="udid16")

        assert conn.state == ConnectionState.READY
        assert conn.ios_category == IOSVersionCategory.DDI

    @patch(_PATCH_TUNNELD_BY_UDID, return_value=None)
    @patch(_PATCH_CREATE)
    @patch(_PATCH_ENUM)
    def test_connect_unsupported_ios_raises(
        self,
        mock_enum: MagicMock,
        mock_create: MagicMock,
        _tbu: MagicMock,
    ) -> None:
        """iOS 12 device should raise UnsupportedIOSVersionError."""
        mock_enum.return_value = [_make_mock_mux_device("old")]
        mock_create.return_value = _make_mock_lockdown("12.5.7")

        manager = DeviceManager()
        with pytest.raises(UnsupportedIOSVersionError):
            manager.connect_device(udid="old")

    @patch(_PATCH_CREATE)
    @patch(_PATCH_ENUM)
    def test_connect_pairing_error(
        self,
        mock_enum: MagicMock,
        mock_create: MagicMock,
    ) -> None:
        from pymobiledevice3.exceptions import PairingError

        mock_enum.return_value = [_make_mock_mux_device("unpaired")]
        mock_create.side_effect = PairingError()

        manager = DeviceManager()
        with pytest.raises(DevicePairingError):
            manager.connect_device(udid="unpaired")

    @patch(_PATCH_CREATE)
    @patch(_PATCH_ENUM)
    def test_connect_connection_failure(
        self,
        mock_enum: MagicMock,
        mock_create: MagicMock,
    ) -> None:
        from pymobiledevice3.exceptions import ConnectionFailedError

        mock_enum.return_value = [_make_mock_mux_device("fail")]
        mock_create.side_effect = ConnectionFailedError()

        manager = DeviceManager()
        with pytest.raises(DeviceConnectionError):
            manager.connect_device(udid="fail")

    @patch(_PATCH_CREATE)
    @patch(_PATCH_ENUM)
    def test_connect_first_available_device_usb(
        self,
        mock_enum: MagicMock,
        mock_create: MagicMock,
    ) -> None:
        """connect_device(udid=None) should connect to first USB device if iOS <=16."""
        mock_enum.return_value = [
            _make_mock_mux_device("first"),
        ]
        mock_create.return_value = _make_mock_lockdown("16.7.4")

        mock_mounter = MagicMock()
        mock_mounter.is_image_mounted.return_value = True

        with patch(_PATCH_MOUNTER, return_value=mock_mounter):
            manager = DeviceManager()
            conn = manager.connect_device()
            assert conn.udid == "first"

    @patch(_PATCH_ENUM)
    def test_connect_ios17_only_via_tunneld(
        self,
        mock_enum: MagicMock,
    ) -> None:
        """iOS 17+ device found only via tunneld (not on USB)."""
        mock_enum.return_value = []  # No USB devices

        mock_rsd = _make_mock_rsd("tunnel-only-device", "17.2.1")

        with (
            patch(_PATCH_TUNNELD_BY_UDID, return_value=mock_rsd),
            patch(_PATCH_TUNNELD_DEVICES, return_value=[mock_rsd]),
        ):
            manager = DeviceManager()
            conn = manager.connect_device(udid="tunnel-only-device")

            assert conn.udid == "tunnel-only-device"
            assert conn.state == ConnectionState.READY
            assert conn.ios_category == IOSVersionCategory.TUNNEL

    @patch(_PATCH_TUNNELD_BY_UDID, return_value=None)
    @patch(_PATCH_ENUM)
    def test_connect_udid_not_on_usb_or_tunneld(
        self,
        mock_enum: MagicMock,
        _tbu: MagicMock,
    ) -> None:
        """Device not found on USB or tunneld should raise."""
        mock_enum.return_value = []
        manager = DeviceManager()
        with pytest.raises(DeviceNotFoundError):
            manager.connect_device(udid="ghost")


# =====================================================================
# Disconnect
# =====================================================================

class TestDisconnect:
    """Tests for disconnect_device and disconnect_all."""

    @patch(_PATCH_CREATE)
    @patch(_PATCH_ENUM)
    def test_disconnect_device_removes_from_list(
        self,
        mock_enum: MagicMock,
        mock_create: MagicMock,
    ) -> None:
        mock_enum.return_value = [_make_mock_mux_device("d1")]
        mock_create.return_value = _make_mock_lockdown("17.0")

        with TunneldMockContext(udid="d1"):
            manager = DeviceManager()
            manager.connect_device(udid="d1")
            assert len(manager.list_connected_devices()) == 1

            manager.disconnect_device("d1")
            assert len(manager.list_connected_devices()) == 0

    def test_disconnect_nonexistent_device_does_not_raise(self) -> None:
        manager = DeviceManager()
        manager.disconnect_device("nonexistent")  # should not raise

    @patch(_PATCH_CREATE)
    @patch(_PATCH_ENUM)
    def test_disconnect_all_clears_everything(
        self,
        mock_enum: MagicMock,
        mock_create: MagicMock,
    ) -> None:
        mock_create.return_value = _make_mock_lockdown("17.0")

        with TunneldMockContext(udid="d1"):
            manager = DeviceManager()
            for udid in ["d1", "d2"]:
                mock_rsd = _make_mock_rsd(udid, "17.0")
                with patch(_PATCH_TUNNELD_BY_UDID, return_value=mock_rsd):
                    mock_enum.return_value = [_make_mock_mux_device(udid)]
                    manager.connect_device(udid=udid)
            assert len(manager.list_connected_devices()) == 2

            manager.disconnect_all()
            assert len(manager.list_connected_devices()) == 0


# =====================================================================
# Get Device / Get Lockdown Client
# =====================================================================

class TestGetDevice:
    """Tests for get_device and get_lockdown_client."""

    def test_get_device_not_found(self) -> None:
        manager = DeviceManager()
        with pytest.raises(DeviceNotFoundError, match="nonexistent"):
            manager.get_device("nonexistent")

    @patch(_PATCH_CREATE)
    @patch(_PATCH_ENUM)
    def test_get_device_returns_connection(
        self,
        mock_enum: MagicMock,
        mock_create: MagicMock,
    ) -> None:
        mock_enum.return_value = [_make_mock_mux_device("d1")]
        mock_create.return_value = _make_mock_lockdown("17.0")

        with TunneldMockContext(udid="d1"):
            manager = DeviceManager()
            manager.connect_device(udid="d1")

            conn = manager.get_device("d1")
            assert conn.udid == "d1"

    def test_get_lockdown_client_not_found(self) -> None:
        manager = DeviceManager()
        with pytest.raises(DeviceNotFoundError):
            manager.get_lockdown_client("nonexistent")

    @patch(_PATCH_MOUNTER)
    @patch(_PATCH_CREATE)
    @patch(_PATCH_ENUM)
    def test_get_lockdown_client_returns_client_for_ios16(
        self,
        mock_enum: MagicMock,
        mock_create: MagicMock,
        mock_mounter_cls: MagicMock,
    ) -> None:
        """Lockdown client should be available for iOS 16 devices."""
        mock_lockdown = _make_mock_lockdown("16.7")
        mock_enum.return_value = [_make_mock_mux_device("d1")]
        mock_create.return_value = mock_lockdown
        mock_mounter = MagicMock()
        mock_mounter.is_image_mounted.return_value = True
        mock_mounter_cls.return_value = mock_mounter

        manager = DeviceManager()
        manager.connect_device(udid="d1")

        client = manager.get_lockdown_client("d1")
        assert client is mock_lockdown


# =====================================================================
# Callbacks
# =====================================================================

class TestCallbacks:
    """Tests for event callback invocation."""

    @patch(_PATCH_CREATE)
    @patch(_PATCH_ENUM)
    def test_on_device_connected_called(
        self,
        mock_enum: MagicMock,
        mock_create: MagicMock,
    ) -> None:
        mock_enum.return_value = [_make_mock_mux_device("d1")]
        mock_create.return_value = _make_mock_lockdown("17.0")

        callback = MagicMock()

        with TunneldMockContext(udid="d1"):
            manager = DeviceManager()
            manager.on_device_connected = callback

            manager.connect_device(udid="d1")

            callback.assert_called_once()
            conn_arg = callback.call_args[0][0]
            assert conn_arg.udid == "d1"
            assert conn_arg.state == ConnectionState.READY

    @patch(_PATCH_CREATE)
    @patch(_PATCH_ENUM)
    def test_on_state_changed_called_multiple_times(
        self,
        mock_enum: MagicMock,
        mock_create: MagicMock,
    ) -> None:
        mock_enum.return_value = [_make_mock_mux_device("d1")]
        mock_create.return_value = _make_mock_lockdown("17.0")

        callback = MagicMock()

        with TunneldMockContext(udid="d1"):
            manager = DeviceManager()
            manager.on_state_changed = callback

            manager.connect_device(udid="d1")

            # Should be called for: TUNNEL_ESTABLISHED, READY
            assert callback.call_count >= 2

    @patch(_PATCH_CREATE)
    @patch(_PATCH_ENUM)
    def test_callback_exception_does_not_crash_connection(
        self,
        mock_enum: MagicMock,
        mock_create: MagicMock,
    ) -> None:
        """Callback errors should be logged but not propagate."""
        mock_enum.return_value = [_make_mock_mux_device("d1")]
        mock_create.return_value = _make_mock_lockdown("17.0")

        def bad_callback(conn: object) -> None:
            raise RuntimeError("callback error")

        with TunneldMockContext(udid="d1"):
            manager = DeviceManager()
            manager.on_device_connected = bad_callback

            # Should not raise despite callback error
            conn = manager.connect_device(udid="d1")
            assert conn.state == ConnectionState.READY


# =====================================================================
# Polling
# =====================================================================

class TestPolling:
    """Tests for start_polling / stop_polling lifecycle."""

    def test_start_stop_polling(self) -> None:
        manager = DeviceManager(poll_interval=0.1)
        manager.start_polling()
        assert manager.is_polling is True

        manager.stop_polling()
        assert manager.is_polling is False

    def test_double_start_is_idempotent(self) -> None:
        manager = DeviceManager(poll_interval=0.1)
        manager.start_polling()
        manager.start_polling()  # should not raise
        assert manager.is_polling is True
        manager.stop_polling()

    @patch(_PATCH_TUNNELD_DEVICES, return_value=[])
    @patch(_PATCH_CREATE)
    @patch(_PATCH_LIST)
    def test_polling_detects_new_usb_device(
        self,
        mock_list: MagicMock,
        mock_create: MagicMock,
        _td: MagicMock,
    ) -> None:
        """Verify poll loop picks up a newly-connected iOS 16 USB device."""
        connected_event = threading.Event()

        usb_dev = _make_mock_mux_device("polled_dev")
        mock_list.return_value = [usb_dev]
        mock_create.return_value = _make_mock_lockdown("16.7")

        mock_mounter = MagicMock()
        mock_mounter.is_image_mounted.return_value = True

        def on_connected(conn: object) -> None:
            connected_event.set()

        with patch(_PATCH_MOUNTER, return_value=mock_mounter):
            manager = DeviceManager(poll_interval=0.1)
            manager.on_device_connected = on_connected
            manager.start_polling()

            try:
                assert connected_event.wait(timeout=3.0), (
                    "Device was not detected within timeout"
                )
                assert len(manager.list_connected_devices()) == 1
            finally:
                manager.stop_polling()

    @patch(_PATCH_TUNNELD_DEVICES, return_value=[])
    @patch(_PATCH_CREATE)
    @patch(_PATCH_LIST)
    def test_polling_detects_device_removal(
        self,
        mock_list: MagicMock,
        mock_create: MagicMock,
        _td: MagicMock,
    ) -> None:
        """Verify poll loop detects device removal."""
        removed_event = threading.Event()

        usb_dev = _make_mock_mux_device("removable")
        mock_list.return_value = [usb_dev]
        mock_create.return_value = _make_mock_lockdown("16.7")

        mock_mounter = MagicMock()
        mock_mounter.is_image_mounted.return_value = True

        def on_disconnected(conn: object) -> None:
            removed_event.set()

        with patch(_PATCH_MOUNTER, return_value=mock_mounter):
            manager = DeviceManager(poll_interval=0.1)
            manager.on_device_disconnected = on_disconnected
            manager.start_polling()

            try:
                # Wait for initial detection
                time.sleep(0.5)
                assert len(manager.list_connected_devices()) == 1

                # Simulate removal
                mock_list.return_value = []
                assert removed_event.wait(timeout=3.0), (
                    "Removal was not detected within timeout"
                )
                assert len(manager.list_connected_devices()) == 0
            finally:
                manager.stop_polling()


# =====================================================================
# Windows driver check
# =====================================================================

class TestWindowsDriverCheck:
    """Tests for check_windows_usb_driver."""

    @patch("ios_gps_spoofer.device.device_manager.platform")
    def test_non_windows_reports_no_check_needed(
        self, mock_platform: MagicMock
    ) -> None:
        mock_platform.system.return_value = "Linux"
        result = DeviceManager.check_windows_usb_driver()
        assert result["is_windows"] is False
        assert result["driver_available"] is True

    @patch("ios_gps_spoofer.device.device_manager.platform")
    def test_macos_reports_no_check_needed(
        self, mock_platform: MagicMock
    ) -> None:
        mock_platform.system.return_value = "Darwin"
        result = DeviceManager.check_windows_usb_driver()
        assert result["is_windows"] is False


# =====================================================================
# Resource cleanup
# =====================================================================

class TestResourceCleanup:
    """Tests for resource cleanup on disconnect."""

    @patch(_PATCH_MOUNTER)
    @patch(_PATCH_CREATE)
    @patch(_PATCH_ENUM)
    def test_lockdown_close_called_on_disconnect_ios16(
        self,
        mock_enum: MagicMock,
        mock_create: MagicMock,
        mock_mounter_cls: MagicMock,
    ) -> None:
        """iOS 16 device: lockdown should be closed on disconnect."""
        mock_lockdown = _make_mock_lockdown("16.7")
        mock_enum.return_value = [_make_mock_mux_device("d1")]
        mock_create.return_value = mock_lockdown
        mock_mounter = MagicMock()
        mock_mounter.is_image_mounted.return_value = True
        mock_mounter_cls.return_value = mock_mounter

        manager = DeviceManager()
        manager.connect_device(udid="d1")
        manager.disconnect_device("d1")

        mock_lockdown.close.assert_called_once()

    @patch(_PATCH_CREATE)
    @patch(_PATCH_ENUM)
    def test_rsd_close_called_on_disconnect_ios17(
        self,
        mock_enum: MagicMock,
        mock_create: MagicMock,
    ) -> None:
        """iOS 17+: RSD should be closed on disconnect."""
        mock_enum.return_value = [_make_mock_mux_device("d1")]
        mock_create.return_value = _make_mock_lockdown("17.0")

        with TunneldMockContext(udid="d1") as ctx:
            manager = DeviceManager()
            manager.connect_device(udid="d1")
            manager.disconnect_device("d1")

            ctx.mock_rsd.close.assert_called_once()

    @patch(_PATCH_MOUNTER)
    @patch(_PATCH_CREATE)
    @patch(_PATCH_ENUM)
    def test_lockdown_close_error_does_not_propagate(
        self,
        mock_enum: MagicMock,
        mock_create: MagicMock,
        mock_mounter_cls: MagicMock,
    ) -> None:
        mock_lockdown = _make_mock_lockdown("16.7")
        mock_lockdown.close.side_effect = OSError("already closed")
        mock_enum.return_value = [_make_mock_mux_device("d1")]
        mock_create.return_value = mock_lockdown
        mock_mounter = MagicMock()
        mock_mounter.is_image_mounted.return_value = True
        mock_mounter_cls.return_value = mock_mounter

        manager = DeviceManager()
        manager.connect_device(udid="d1")

        # Should not raise despite close() error
        manager.disconnect_device("d1")
        assert len(manager.list_connected_devices()) == 0


# =====================================================================
# Edge cases
# =====================================================================

class TestEdgeCases:
    """Edge case and boundary tests."""

    @patch(_PATCH_CREATE)
    @patch(_PATCH_ENUM)
    def test_connect_device_with_missing_device_info_fields(
        self,
        mock_enum: MagicMock,
        mock_create: MagicMock,
    ) -> None:
        """Device with minimal lockdown values should use defaults."""
        mock_enum.return_value = [_make_mock_mux_device("minimal")]
        lockdown = MagicMock()
        # Return empty dict -- all fields should use defaults
        lockdown.get_value.return_value = {}
        mock_create.return_value = lockdown

        manager = DeviceManager()
        # Version "0.0" (the default) is below minimum, so this should raise
        with pytest.raises(UnsupportedIOSVersionError):
            manager.connect_device(udid="minimal")

    @patch(_PATCH_CREATE)
    @patch(_PATCH_ENUM)
    def test_connect_same_device_twice_overwrites(
        self,
        mock_enum: MagicMock,
        mock_create: MagicMock,
    ) -> None:
        """Connecting the same UDID twice should overwrite the old connection."""
        mock_enum.return_value = [_make_mock_mux_device("dup")]
        mock_create.return_value = _make_mock_lockdown("17.0")

        with TunneldMockContext(udid="dup"):
            manager = DeviceManager()
            manager.connect_device(udid="dup")
            conn2 = manager.connect_device(udid="dup")

            # Should have exactly one device
            assert len(manager.list_connected_devices()) == 1
            assert conn2.state == ConnectionState.READY


# =====================================================================
# Tunneld-specific tests
# =====================================================================

class TestTunneldIntegration:
    """Tests for tunneld-based device connection."""

    def test_is_tunneld_running_returns_false_when_not_available(self) -> None:
        """is_tunneld_running should return False when tunneld is not running."""
        manager = DeviceManager(tunneld_address=("127.0.0.1", 1))
        assert manager.is_tunneld_running() is False

    @patch(_PATCH_TUNNELD_BY_UDID)
    @patch(_PATCH_ENUM)
    def test_connect_tunneld_device_directly(
        self,
        mock_enum: MagicMock,
        mock_tbu: MagicMock,
    ) -> None:
        """Connect a device directly via tunneld (not found on USB)."""
        mock_enum.return_value = []  # Not on USB

        mock_rsd = _make_mock_rsd("tunnel-dev", "26.2.1")
        mock_tbu.return_value = mock_rsd

        manager = DeviceManager()
        conn = manager.connect_device(udid="tunnel-dev")

        assert conn.udid == "tunnel-dev"
        assert conn.state == ConnectionState.READY
        assert conn.ios_category == IOSVersionCategory.TUNNEL
        assert conn.device_info.product_version == "26.2.1"

    @patch(_PATCH_TUNNELD_BY_UDID)
    @patch(_PATCH_ENUM)
    def test_connect_tunneld_failure_raises_tunnel_error(
        self,
        mock_enum: MagicMock,
        mock_tbu: MagicMock,
    ) -> None:
        """If tunneld query fails, should raise TunnelError."""
        mock_enum.return_value = []
        mock_tbu.side_effect = ConnectionError("tunneld unreachable")

        manager = DeviceManager()
        with pytest.raises(TunnelError, match="tunneld"):
            manager.connect_device(udid="unreachable")

    @patch(_PATCH_ENUM)
    def test_get_ios_category(self, mock_enum: MagicMock) -> None:
        """get_ios_category should return TUNNEL for iOS 17+ devices."""
        mock_enum.return_value = []

        mock_rsd = _make_mock_rsd("cat-test", "17.0")
        with patch(_PATCH_TUNNELD_BY_UDID, return_value=mock_rsd):
            manager = DeviceManager()
            manager.connect_device(udid="cat-test")
            assert manager.get_ios_category("cat-test") == IOSVersionCategory.TUNNEL

    def test_get_ios_category_not_found(self) -> None:
        manager = DeviceManager()
        with pytest.raises(DeviceNotFoundError):
            manager.get_ios_category("nonexistent")
