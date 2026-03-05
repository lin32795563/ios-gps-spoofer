"""Speed profile management for path simulation.

Provides named speed presets (walking, cycling, driving) and support for
custom speed values.  All speeds are stored and returned in meters per
second (m/s) internally, with convenience conversion utilities.

Thread Safety
-------------
``SpeedController`` is thread-safe.  The current speed can be changed
at any time during a running simulation -- the simulation loop picks up
the new speed on its next iteration.
"""

from __future__ import annotations

import enum
import logging
import threading

logger = logging.getLogger(__name__)

# Conversion factor: 1 km/h = 1000m / 3600s
_KMH_TO_MS = 1000.0 / 3600.0

# Minimum and maximum allowed speeds in m/s.
# Minimum is a small positive value to prevent division by zero.
# Maximum is approximately 1000 km/h (supersonic; generous upper bound).
MIN_SPEED_MS = 0.01  # ~0.036 km/h
MAX_SPEED_MS = 277.78  # ~1000 km/h


class SpeedPreset(enum.Enum):
    """Named speed presets for common movement types.

    Values are in km/h for human readability; use ``preset_to_ms()``
    or ``SpeedController.set_preset()`` to convert to m/s.
    """

    WALKING = 5.0      # 5 km/h
    CYCLING = 15.0     # 15 km/h
    DRIVING = 60.0     # 60 km/h


def kmh_to_ms(speed_kmh: float) -> float:
    """Convert speed from km/h to m/s.

    Args:
        speed_kmh: Speed in kilometers per hour.

    Returns:
        Speed in meters per second.
    """
    return speed_kmh * _KMH_TO_MS


def ms_to_kmh(speed_ms: float) -> float:
    """Convert speed from m/s to km/h.

    Args:
        speed_ms: Speed in meters per second.

    Returns:
        Speed in kilometers per hour.
    """
    return speed_ms / _KMH_TO_MS


def preset_to_ms(preset: SpeedPreset) -> float:
    """Convert a speed preset to m/s.

    Args:
        preset: A ``SpeedPreset`` enum member.

    Returns:
        Speed in meters per second.
    """
    return kmh_to_ms(preset.value)


class SpeedController:
    """Thread-safe speed controller that can be updated during simulation.

    The simulation loop reads the current speed via ``speed_ms`` on each
    iteration.  External code can change the speed via ``set_speed_ms()``,
    ``set_speed_kmh()``, or ``set_preset()`` at any time.

    Usage::

        controller = SpeedController()
        controller.set_preset(SpeedPreset.WALKING)

        # In the simulation loop:
        current_speed = controller.speed_ms

        # User changes speed mid-simulation:
        controller.set_speed_kmh(30.0)
    """

    def __init__(self, initial_preset: SpeedPreset = SpeedPreset.WALKING) -> None:
        """Initialize with a default speed preset.

        Args:
            initial_preset: The starting speed preset.
        """
        self._speed_ms: float = preset_to_ms(initial_preset)
        self._lock = threading.Lock()

    @property
    def speed_ms(self) -> float:
        """Current speed in meters per second (thread-safe read)."""
        with self._lock:
            return self._speed_ms

    @property
    def speed_kmh(self) -> float:
        """Current speed in kilometers per hour (thread-safe read)."""
        with self._lock:
            return ms_to_kmh(self._speed_ms)

    def set_speed_ms(self, speed_ms: float) -> None:
        """Set the speed in meters per second.

        Args:
            speed_ms: Speed in m/s.  Must be between ``MIN_SPEED_MS``
                and ``MAX_SPEED_MS``.

        Raises:
            ValueError: If speed is out of the allowed range.
        """
        self._validate_speed_ms(speed_ms)
        with self._lock:
            self._speed_ms = speed_ms
        logger.debug("Speed set to %.2f m/s (%.1f km/h)", speed_ms, ms_to_kmh(speed_ms))

    def set_speed_kmh(self, speed_kmh: float) -> None:
        """Set the speed in kilometers per hour.

        Args:
            speed_kmh: Speed in km/h.

        Raises:
            ValueError: If the converted speed is out of the allowed range.
        """
        speed_ms = kmh_to_ms(speed_kmh)
        self.set_speed_ms(speed_ms)

    def set_preset(self, preset: SpeedPreset) -> None:
        """Set the speed to a named preset.

        Args:
            preset: A ``SpeedPreset`` enum member.
        """
        speed_ms = preset_to_ms(preset)
        with self._lock:
            self._speed_ms = speed_ms
        logger.info("Speed preset set to %s (%.1f km/h)", preset.name, preset.value)

    @staticmethod
    def _validate_speed_ms(speed_ms: float) -> None:
        """Validate that a speed value is within the allowed range.

        Args:
            speed_ms: Speed in m/s.

        Raises:
            ValueError: If speed is out of range, NaN, or infinite.
        """
        import math

        if not isinstance(speed_ms, (int, float)) or isinstance(speed_ms, bool):
            raise ValueError(
                f"Speed must be a number, got {type(speed_ms).__name__}"
            )
        if math.isnan(speed_ms) or math.isinf(speed_ms):
            raise ValueError(f"Speed must be finite, got {speed_ms}")
        if speed_ms < MIN_SPEED_MS:
            raise ValueError(
                f"Speed must be at least {MIN_SPEED_MS} m/s "
                f"({ms_to_kmh(MIN_SPEED_MS):.3f} km/h), got {speed_ms} m/s"
            )
        if speed_ms > MAX_SPEED_MS:
            raise ValueError(
                f"Speed must be at most {MAX_SPEED_MS} m/s "
                f"({ms_to_kmh(MAX_SPEED_MS):.1f} km/h), got {speed_ms} m/s"
            )
