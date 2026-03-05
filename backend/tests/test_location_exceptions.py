"""Tests for ios_gps_spoofer.location.exceptions module.

Covers:
- Exception hierarchy (all derive from LocationError)
- Exception messages include relevant context (UDID, reason, detail)
- Exception attributes are stored correctly
"""

import pytest

from ios_gps_spoofer.location.exceptions import (
    InvalidCoordinateError,
    LocationClearError,
    LocationError,
    LocationServiceNotReadyError,
    LocationSetError,
)

# =====================================================================
# Hierarchy
# =====================================================================

class TestLocationExceptionHierarchy:
    """All location exceptions must inherit from LocationError."""

    @pytest.mark.parametrize(
        "exc_cls",
        [
            LocationServiceNotReadyError,
            LocationSetError,
            LocationClearError,
            InvalidCoordinateError,
        ],
    )
    def test_inherits_from_location_error(self, exc_cls: type) -> None:
        assert issubclass(exc_cls, LocationError)

    def test_location_error_inherits_from_exception(self) -> None:
        assert issubclass(LocationError, Exception)

    def test_location_error_not_inherits_from_base_exception_only(self) -> None:
        """LocationError should not be a bare BaseException subclass."""
        assert issubclass(LocationError, Exception)


# =====================================================================
# LocationServiceNotReadyError
# =====================================================================

class TestLocationServiceNotReadyError:
    """Tests for LocationServiceNotReadyError."""

    def test_message_includes_udid(self) -> None:
        exc = LocationServiceNotReadyError("abc123")
        assert "abc123" in str(exc)

    def test_message_includes_reason(self) -> None:
        exc = LocationServiceNotReadyError("abc123", "tunnel not ready")
        assert "tunnel not ready" in str(exc)

    def test_default_reason(self) -> None:
        exc = LocationServiceNotReadyError("abc123")
        assert "Service not initialized" in str(exc)

    def test_attributes(self) -> None:
        exc = LocationServiceNotReadyError("abc123", "custom reason")
        assert exc.udid == "abc123"
        assert exc.reason == "custom reason"

    def test_catchable_as_location_error(self) -> None:
        with pytest.raises(LocationError):
            raise LocationServiceNotReadyError("x")


# =====================================================================
# LocationSetError
# =====================================================================

class TestLocationSetError:
    """Tests for LocationSetError."""

    def test_message_includes_udid_and_reason(self) -> None:
        exc = LocationSetError("device1", "connection lost")
        assert "device1" in str(exc)
        assert "connection lost" in str(exc)

    def test_attributes(self) -> None:
        exc = LocationSetError("device1", "reason")
        assert exc.udid == "device1"
        assert exc.reason == "reason"


# =====================================================================
# LocationClearError
# =====================================================================

class TestLocationClearError:
    """Tests for LocationClearError."""

    def test_message_includes_udid_and_reason(self) -> None:
        exc = LocationClearError("device1", "service unavailable")
        assert "device1" in str(exc)
        assert "service unavailable" in str(exc)

    def test_attributes(self) -> None:
        exc = LocationClearError("device1", "reason")
        assert exc.udid == "device1"
        assert exc.reason == "reason"


# =====================================================================
# InvalidCoordinateError
# =====================================================================

class TestInvalidCoordinateError:
    """Tests for InvalidCoordinateError."""

    def test_message_includes_detail(self) -> None:
        exc = InvalidCoordinateError("latitude out of range")
        assert "latitude out of range" in str(exc)

    def test_attributes(self) -> None:
        exc = InvalidCoordinateError("detail text")
        assert exc.detail == "detail text"

    def test_catchable_as_location_error(self) -> None:
        with pytest.raises(LocationError):
            raise InvalidCoordinateError("bad coords")
