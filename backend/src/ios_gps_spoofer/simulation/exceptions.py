"""Custom exceptions for the path simulation engine.

All exceptions inherit from ``SimulationError``, which itself inherits from
the standard ``Exception``.  The device and location exception hierarchies
are kept separate -- simulation errors represent problems with the route
playback logic, not with device connectivity or coordinate validation.
"""

from __future__ import annotations


class SimulationError(Exception):
    """Base exception for all simulation-related errors."""


class SimulationStateError(SimulationError):
    """Raised when an operation is invalid for the current simulation state.

    For example, attempting to pause a simulation that is not running,
    or starting a simulation that is already running.
    """

    def __init__(self, current_state: str, attempted_action: str) -> None:
        super().__init__(
            f"Cannot {attempted_action} simulation: "
            f"current state is '{current_state}'"
        )
        self.current_state = current_state
        self.attempted_action = attempted_action


class GPXParseError(SimulationError):
    """Raised when a GPX file cannot be parsed.

    Covers malformed XML, missing required elements, invalid coordinate
    values, and empty waypoint lists.
    """

    def __init__(self, detail: str, source: str = "") -> None:
        msg = f"GPX parse error: {detail}"
        if source:
            msg += f" (source: {source})"
        super().__init__(msg)
        self.detail = detail
        self.source = source


class EmptyPathError(SimulationError):
    """Raised when a simulation is started with an empty or single-point path.

    A path must have at least two distinct points for movement simulation.
    """

    def __init__(self, point_count: int) -> None:
        super().__init__(
            f"Path must have at least 2 points for simulation, "
            f"got {point_count}"
        )
        self.point_count = point_count


class SpeedError(SimulationError):
    """Raised when an invalid speed value is provided."""

    def __init__(self, speed: float, reason: str = "") -> None:
        msg = f"Invalid speed: {speed} m/s"
        if reason:
            msg += f" ({reason})"
        super().__init__(msg)
        self.speed = speed
        self.reason = reason
