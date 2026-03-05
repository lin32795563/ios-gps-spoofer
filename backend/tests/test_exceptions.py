"""Tests for ios_gps_spoofer.device.exceptions module.

Covers:
- Exception hierarchy (all inherit from DeviceError)
- Message formatting
- Attribute preservation
"""

import pytest

from ios_gps_spoofer.device.exceptions import (
    DDIMountError,
    DeveloperModeError,
    DeviceConnectionError,
    DeviceError,
    DeviceNotFoundError,
    DevicePairingError,
    TunnelError,
    UnsupportedIOSVersionError,
)


class TestExceptionHierarchy:
    """All custom exceptions must inherit from DeviceError."""

    @pytest.mark.parametrize(
        "exc_class",
        [
            DeviceNotFoundError,
            DeviceConnectionError,
            DevicePairingError,
            DDIMountError,
            UnsupportedIOSVersionError,
            DeveloperModeError,
            TunnelError,
        ],
    )
    def test_inherits_from_device_error(self, exc_class: type) -> None:
        assert issubclass(exc_class, DeviceError)

    def test_device_error_inherits_from_exception(self) -> None:
        assert issubclass(DeviceError, Exception)


class TestDeviceNotFoundError:
    """Tests for DeviceNotFoundError."""

    def test_with_udid(self) -> None:
        exc = DeviceNotFoundError(udid="abc123")
        assert "abc123" in str(exc)
        assert exc.udid == "abc123"

    def test_without_udid(self) -> None:
        exc = DeviceNotFoundError()
        assert "No iOS device found" in str(exc)
        assert exc.udid is None

    def test_catchable_as_device_error(self) -> None:
        with pytest.raises(DeviceError):
            raise DeviceNotFoundError("test")


class TestDeviceConnectionError:
    """Tests for DeviceConnectionError."""

    def test_message_includes_udid_and_reason(self) -> None:
        exc = DeviceConnectionError("abc", "timeout")
        assert "abc" in str(exc)
        assert "timeout" in str(exc)
        assert exc.udid == "abc"
        assert exc.reason == "timeout"


class TestDevicePairingError:
    """Tests for DevicePairingError."""

    def test_message_includes_trust_instruction(self) -> None:
        exc = DevicePairingError("abc")
        assert "Trust" in str(exc)
        assert exc.udid == "abc"


class TestDDIMountError:
    """Tests for DDIMountError."""

    def test_message_includes_reason(self) -> None:
        exc = DDIMountError("abc", "image not found")
        assert "image not found" in str(exc)
        assert exc.udid == "abc"
        assert exc.reason == "image not found"


class TestUnsupportedIOSVersionError:
    """Tests for UnsupportedIOSVersionError."""

    def test_message_includes_version(self) -> None:
        exc = UnsupportedIOSVersionError("abc", "12.0")
        assert "12.0" in str(exc)
        assert "14.0" in str(exc)  # minimum version mentioned
        assert exc.udid == "abc"
        assert exc.version == "12.0"


class TestDeveloperModeError:
    """Tests for DeveloperModeError."""

    def test_message_includes_settings_path(self) -> None:
        exc = DeveloperModeError("abc")
        assert "Developer Mode" in str(exc)
        assert exc.udid == "abc"


class TestTunnelError:
    """Tests for TunnelError."""

    def test_message_includes_reason(self) -> None:
        exc = TunnelError("abc", "connection refused")
        assert "connection refused" in str(exc)
        assert exc.udid == "abc"
        assert exc.reason == "connection refused"
