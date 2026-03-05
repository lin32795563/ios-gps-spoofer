"""Tests for ios_gps_spoofer.simulation.exceptions module."""

import pytest

from ios_gps_spoofer.simulation.exceptions import (
    EmptyPathError,
    GPXParseError,
    SimulationError,
    SimulationStateError,
    SpeedError,
)


class TestExceptionHierarchy:
    """All simulation exceptions inherit from SimulationError."""

    @pytest.mark.parametrize(
        "exc_cls",
        [SimulationStateError, GPXParseError, EmptyPathError, SpeedError],
    )
    def test_inherits_from_simulation_error(self, exc_cls: type) -> None:
        assert issubclass(exc_cls, SimulationError)

    def test_simulation_error_inherits_from_exception(self) -> None:
        assert issubclass(SimulationError, Exception)

    def test_simulation_error_not_inherits_from_base_exception_only(self) -> None:
        # Should be catchable by `except Exception`
        assert not issubclass(SimulationError, KeyboardInterrupt)


class TestSimulationStateError:
    def test_message_includes_state_and_action(self) -> None:
        exc = SimulationStateError("idle", "pause")
        assert "idle" in str(exc)
        assert "pause" in str(exc)

    def test_attributes(self) -> None:
        exc = SimulationStateError("running", "start")
        assert exc.current_state == "running"
        assert exc.attempted_action == "start"


class TestGPXParseError:
    def test_message_includes_detail(self) -> None:
        exc = GPXParseError("Malformed XML")
        assert "Malformed XML" in str(exc)

    def test_message_includes_source(self) -> None:
        exc = GPXParseError("No waypoints", source="/path/to/file.gpx")
        assert "/path/to/file.gpx" in str(exc)

    def test_attributes(self) -> None:
        exc = GPXParseError("detail", source="src")
        assert exc.detail == "detail"
        assert exc.source == "src"

    def test_empty_source(self) -> None:
        exc = GPXParseError("detail")
        assert exc.source == ""


class TestEmptyPathError:
    def test_message_includes_count(self) -> None:
        exc = EmptyPathError(1)
        assert "1" in str(exc)
        assert "at least 2" in str(exc)

    def test_zero_points(self) -> None:
        exc = EmptyPathError(0)
        assert exc.point_count == 0


class TestSpeedError:
    def test_message_includes_speed(self) -> None:
        exc = SpeedError(0.0, reason="too slow")
        assert "0.0" in str(exc)
        assert "too slow" in str(exc)

    def test_attributes(self) -> None:
        exc = SpeedError(-1.5, reason="negative")
        assert exc.speed == -1.5
        assert exc.reason == "negative"

    def test_empty_reason(self) -> None:
        exc = SpeedError(999.0)
        assert exc.reason == ""
