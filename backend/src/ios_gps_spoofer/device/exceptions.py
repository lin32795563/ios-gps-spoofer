"""Custom exceptions for the device connection module.

All exceptions inherit from DeviceError, which itself inherits from the
application-wide base exception.  This gives callers a single catch point
while still allowing fine-grained handling when needed.
"""


class DeviceError(Exception):
    """Base exception for all device-related errors."""


class DeviceNotFoundError(DeviceError):
    """Raised when the requested device cannot be found on USB."""

    def __init__(self, udid: str | None = None) -> None:
        if udid:
            super().__init__(f"Device with UDID '{udid}' not found on USB")
        else:
            super().__init__("No iOS device found on USB")
        self.udid = udid


class DeviceConnectionError(DeviceError):
    """Raised when a connection to the device fails or is lost."""

    def __init__(self, udid: str, reason: str) -> None:
        super().__init__(f"Connection error for device '{udid}': {reason}")
        self.udid = udid
        self.reason = reason


class DevicePairingError(DeviceError):
    """Raised when device pairing (trust) has not been established."""

    def __init__(self, udid: str) -> None:
        super().__init__(
            f"Device '{udid}' is not paired. Please unlock the device "
            "and tap 'Trust' when prompted."
        )
        self.udid = udid


class DDIMountError(DeviceError):
    """Raised when Developer Disk Image mounting fails."""

    def __init__(self, udid: str, reason: str) -> None:
        super().__init__(
            f"Failed to mount Developer Disk Image on device '{udid}': {reason}"
        )
        self.udid = udid
        self.reason = reason


class UnsupportedIOSVersionError(DeviceError):
    """Raised when the iOS version is not supported."""

    def __init__(self, udid: str, version: str) -> None:
        super().__init__(
            f"iOS version {version} on device '{udid}' is not supported. "
            "Minimum supported version is 14.0."
        )
        self.udid = udid
        self.version = version


class DeveloperModeError(DeviceError):
    """Raised when Developer Mode is not enabled on iOS 16+ devices."""

    def __init__(self, udid: str) -> None:
        super().__init__(
            f"Developer Mode is not enabled on device '{udid}'. "
            "Please enable it in Settings > Privacy & Security > Developer Mode."
        )
        self.udid = udid


class TunnelError(DeviceError):
    """Raised when iOS 17+ tunnel establishment fails."""

    def __init__(self, udid: str, reason: str) -> None:
        super().__init__(
            f"Failed to establish tunnel for device '{udid}': {reason}"
        )
        self.udid = udid
        self.reason = reason
