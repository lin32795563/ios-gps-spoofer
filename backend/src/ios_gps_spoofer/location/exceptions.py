"""Custom exceptions for the location simulation module.

All exceptions inherit from ``LocationError``, which itself inherits from
the standard ``Exception``.  The device module's ``DeviceError`` is NOT
a parent -- location errors are conceptually distinct from device errors,
even though they may be caused by underlying device issues.
"""

from __future__ import annotations


class LocationError(Exception):
    """Base exception for all location-related errors."""


class LocationServiceNotReadyError(LocationError):
    """Raised when a location operation is attempted before the service is ready.

    This typically means the device has not been connected, or the
    DtSimulateLocation service has not been started.
    """

    def __init__(self, udid: str, reason: str = "Service not initialized") -> None:
        super().__init__(
            f"Location service not ready for device '{udid}': {reason}"
        )
        self.udid = udid
        self.reason = reason


class LocationSetError(LocationError):
    """Raised when setting a simulated location fails.

    This can happen if the device disconnects mid-operation, the DDI
    is not mounted, or the service connection drops.
    """

    def __init__(self, udid: str, reason: str) -> None:
        super().__init__(
            f"Failed to set location on device '{udid}': {reason}"
        )
        self.udid = udid
        self.reason = reason


class LocationClearError(LocationError):
    """Raised when clearing the simulated location fails."""

    def __init__(self, udid: str, reason: str) -> None:
        super().__init__(
            f"Failed to clear simulated location on device '{udid}': {reason}"
        )
        self.udid = udid
        self.reason = reason


class InvalidCoordinateError(LocationError):
    """Raised when coordinate validation fails.

    This is a more specific wrapper than the generic ``ValueError``
    that ``Coordinate.__post_init__`` raises, intended for the API layer.
    """

    def __init__(self, detail: str) -> None:
        super().__init__(f"Invalid coordinate: {detail}")
        self.detail = detail
