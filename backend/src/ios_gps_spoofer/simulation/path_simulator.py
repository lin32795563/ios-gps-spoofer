"""Core path simulation engine.

Moves a virtual GPS position along a sequence of coordinates at a
configurable speed, sending each intermediate position to the device
via ``LocationService``.  Runs on a dedicated daemon thread so the
main thread / API layer is never blocked.

Architecture
------------
``PathSimulator`` owns:
- A ``SimulationStateMachine`` for lifecycle management.
- A ``SpeedController`` for thread-safe speed adjustment.
- A worker thread that runs the ``_simulation_loop()``.
- A progress callback for real-time UI updates.

The simulation loop:
1. Iterates over path segments (pairs of consecutive waypoints).
2. For each segment, calculates intermediate positions using great-circle
   interpolation at intervals determined by current speed.
3. At each tick, optionally applies GPS drift, then sends the position
   to the device via ``LocationService.set_location()``.
4. Respects pause/resume via ``SimulationStateMachine.wait_for_resume()``.
5. Exits cleanly when stopped or when the path is complete.

Thread Safety
-------------
``PathSimulator`` is designed for one simulation per device.  Multiple
simulators can run concurrently for different devices.  All mutable state
is protected by locks or thread-safe components.
"""

from __future__ import annotations

import contextlib
import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from ios_gps_spoofer.location.coordinates import Coordinate, interpolate_great_circle
from ios_gps_spoofer.simulation.exceptions import (
    EmptyPathError,
    SimulationStateError,
)
from ios_gps_spoofer.simulation.gps_drift import apply_drift
from ios_gps_spoofer.simulation.speed_profiles import SpeedController
from ios_gps_spoofer.simulation.state_machine import (
    SimulationState,
    SimulationStateMachine,
)

if TYPE_CHECKING:
    from ios_gps_spoofer.location.location_service import LocationService

logger = logging.getLogger(__name__)

# Minimum interval between location updates in seconds.
# Prevents overwhelming the device with too-frequent updates.
MIN_TICK_INTERVAL_S = 0.5

# Maximum interval between location updates in seconds.
# Ensures the UI stays responsive even at very low speeds.
MAX_TICK_INTERVAL_S = 2.0

# Default tick interval target
DEFAULT_TICK_INTERVAL_S = 1.0


@dataclass
class SimulationProgress:
    """Snapshot of current simulation progress.

    Sent to the progress callback on each tick.
    """

    current_position: Coordinate
    segment_index: int
    total_segments: int
    distance_covered_m: float
    total_distance_m: float
    elapsed_time_s: float
    speed_ms: float
    state: SimulationState

    @property
    def fraction_complete(self) -> float:
        """Progress as a fraction in [0.0, 1.0]."""
        if self.total_distance_m <= 0:
            return 1.0
        return min(1.0, self.distance_covered_m / self.total_distance_m)

    @property
    def is_complete(self) -> bool:
        """True if the simulation has reached the end of the path."""
        return self.distance_covered_m >= self.total_distance_m

    def to_dict(self) -> dict[str, object]:
        """Serialize to a JSON-friendly dictionary."""
        return {
            "current_position": self.current_position.to_dict(),
            "segment_index": self.segment_index,
            "total_segments": self.total_segments,
            "distance_covered_m": round(self.distance_covered_m, 2),
            "total_distance_m": round(self.total_distance_m, 2),
            "fraction_complete": round(self.fraction_complete, 4),
            "elapsed_time_s": round(self.elapsed_time_s, 2),
            "speed_ms": round(self.speed_ms, 2),
            "state": self.state.value,
        }


# Type alias for the progress callback
ProgressCallback = Callable[[SimulationProgress], None]


@dataclass
class SimulationConfig:
    """Configuration for a path simulation run.

    Attributes:
        drift_enabled: Whether to apply Gaussian GPS drift.
        drift_sigma_meters: Standard deviation of drift in meters.
        loop_path: Whether to restart from the beginning when the
            end of the path is reached.
        tick_interval_s: Target interval between location updates.
    """

    drift_enabled: bool = True
    drift_sigma_meters: float = 2.0
    loop_path: bool = False
    tick_interval_s: float = DEFAULT_TICK_INTERVAL_S


class PathSimulator:
    """Core path simulation engine.

    Usage::

        from ios_gps_spoofer.simulation import PathSimulator, SpeedPreset

        simulator = PathSimulator(
            udid="device-udid",
            path=[coord1, coord2, coord3],
            location_service=location_service,
        )
        simulator.speed_controller.set_preset(SpeedPreset.CYCLING)
        simulator.start()
        # ... later ...
        simulator.pause()
        simulator.resume()
        simulator.stop()
    """

    def __init__(
        self,
        udid: str,
        path: list[Coordinate],
        location_service: LocationService,
        config: SimulationConfig | None = None,
        on_progress: ProgressCallback | None = None,
        on_complete: Callable[[], None] | None = None,
        on_error: Callable[[Exception], None] | None = None,
    ) -> None:
        """Initialize the path simulator.

        Args:
            udid: Device UDID to send locations to.
            path: Ordered list of waypoints (at least 2 points).
            location_service: The location service for sending positions.
            config: Simulation configuration.  Defaults are used if None.
            on_progress: Callback invoked on each tick with progress info.
            on_complete: Callback invoked when the path is fully traversed.
            on_error: Callback invoked if an error occurs during simulation.

        Raises:
            EmptyPathError: If path has fewer than 2 points.
            ValueError: If udid or location_service is invalid.
        """
        if not udid:
            raise ValueError("udid must be a non-empty string")
        if location_service is None:
            raise ValueError("location_service must not be None")
        if len(path) < 2:
            raise EmptyPathError(len(path))

        self._udid = udid
        self._path = list(path)  # defensive copy
        self._location_service = location_service
        self._config = config or SimulationConfig()
        self._on_progress = on_progress
        self._on_complete = on_complete
        self._on_error = on_error

        # Public-facing components
        self._state_machine = SimulationStateMachine()
        self._speed_controller = SpeedController()

        # Internal state
        self._thread: threading.Thread | None = None
        self._segment_distances: list[float] = []
        self._total_distance_m: float = 0.0

        # Pre-calculate segment distances
        self._precompute_distances()

    @property
    def state(self) -> SimulationState:
        """Current simulation state."""
        return self._state_machine.state

    @property
    def speed_controller(self) -> SpeedController:
        """The speed controller for adjusting speed during simulation."""
        return self._speed_controller

    @property
    def udid(self) -> str:
        """The device UDID this simulator targets."""
        return self._udid

    @property
    def path(self) -> list[Coordinate]:
        """The waypoint path (read-only copy)."""
        return list(self._path)

    @property
    def total_distance_m(self) -> float:
        """Total path distance in meters."""
        return self._total_distance_m

    @property
    def segment_count(self) -> int:
        """Number of segments in the path (waypoints - 1)."""
        return len(self._segment_distances)

    def start(self) -> None:
        """Start the simulation.

        Creates a daemon thread that runs the simulation loop.

        Raises:
            SimulationStateError: If simulation is not in IDLE state.
        """
        self._state_machine.transition("start")

        self._thread = threading.Thread(
            target=self._simulation_loop,
            name=f"PathSimulator-{self._udid}",
            daemon=True,
        )
        self._thread.start()
        logger.info(
            "Simulation started for %s (%d waypoints, %.1f m total)",
            self._udid,
            len(self._path),
            self._total_distance_m,
        )

    def pause(self) -> None:
        """Pause the simulation.

        The simulation thread blocks at the next tick boundary until
        ``resume()`` or ``stop()`` is called.

        Raises:
            SimulationStateError: If simulation is not RUNNING.
        """
        self._state_machine.transition("pause")
        logger.info("Simulation paused for %s", self._udid)

    def resume(self) -> None:
        """Resume a paused simulation.

        Raises:
            SimulationStateError: If simulation is not PAUSED.
        """
        self._state_machine.transition("resume")
        logger.info("Simulation resumed for %s", self._udid)

    def stop(self) -> None:
        """Stop the simulation.

        Can be called from RUNNING or PAUSED state.  The simulation
        thread exits on its next iteration.

        Raises:
            SimulationStateError: If simulation cannot be stopped
                from current state.
        """
        self._state_machine.transition("stop")
        logger.info("Simulation stop requested for %s", self._udid)

    def wait(self, timeout: float | None = None) -> None:
        """Wait for the simulation thread to finish.

        Args:
            timeout: Maximum seconds to wait.  None means wait forever.
        """
        if self._thread is not None:
            self._thread.join(timeout=timeout)

    # ------------------------------------------------------------------
    # Internal: distance pre-computation
    # ------------------------------------------------------------------

    def _precompute_distances(self) -> None:
        """Calculate the distance of each path segment and total distance."""
        self._segment_distances = []
        total = 0.0
        for i in range(len(self._path) - 1):
            dist = self._path[i].distance_to(self._path[i + 1])
            self._segment_distances.append(dist)
            total += dist
        self._total_distance_m = total

    # ------------------------------------------------------------------
    # Internal: simulation loop
    # ------------------------------------------------------------------

    def _simulation_loop(self) -> None:
        """Main simulation loop running on a dedicated thread.

        Uses an outer loop for path looping (when ``loop_path=True``).
        Each iteration of the outer loop traverses the entire path once.
        """
        start_time = time.monotonic()

        try:
            # Outer loop handles path looping without recursion
            while True:
                completed = self._traverse_path(start_time)

                if not completed:
                    # Stopped during traversal
                    return

                # Path fully traversed
                if self._config.loop_path and not self._state_machine.is_stopped:
                    logger.info(
                        "Path complete for %s, looping...", self._udid
                    )
                    continue  # start another traversal

                # Not looping -- simulation is done
                break

            logger.info(
                "Simulation complete for %s (%.1f m in %.1f s)",
                self._udid,
                self._total_distance_m,
                time.monotonic() - start_time,
            )

            # Transition to stopped
            with contextlib.suppress(SimulationStateError):
                self._state_machine.transition("stop")

            if self._on_complete:
                try:
                    self._on_complete()
                except Exception:
                    logger.exception("Error in on_complete callback")

        except Exception as exc:
            logger.exception(
                "Unexpected error in simulation loop for %s", self._udid
            )
            with contextlib.suppress(SimulationStateError):
                self._state_machine.transition("stop")
            if self._on_error:
                try:
                    self._on_error(exc)
                except Exception:
                    logger.exception("Error in on_error callback")

    def _traverse_path(self, start_time: float) -> bool:
        """Traverse the entire path once, sending positions to the device.

        Args:
            start_time: The monotonic time when the overall simulation
                started (used for elapsed time in progress reports).

        Returns:
            True if the path was fully traversed, False if stopped
            or an error occurred.
        """
        distance_covered = 0.0

        for segment_index in range(len(self._segment_distances)):
            # Check if stopped
            if self._state_machine.is_stopped:
                return False

            # Handle pause -- block until resumed or stopped
            if not self._wait_for_running():
                return False

            segment_distance = self._segment_distances[segment_index]

            # Skip zero-length segments (duplicate consecutive points)
            if segment_distance < 0.01:
                logger.debug(
                    "Skipping zero-length segment %d", segment_index
                )
                continue

            # Traverse this segment
            result = self._traverse_segment(
                segment_index=segment_index,
                distance_covered_so_far=distance_covered,
                start_time=start_time,
            )

            if result is None:
                # Stopped or error during segment traversal
                return False

            distance_covered += result

        return True

    def _traverse_segment(
        self,
        segment_index: int,
        distance_covered_so_far: float,
        start_time: float,
    ) -> float | None:
        """Traverse a single path segment, returning distance covered.

        Args:
            segment_index: Index of the current segment.
            distance_covered_so_far: Total distance covered before this segment.
            start_time: Overall simulation start time for progress reports.

        Returns:
            Distance covered in this segment (meters), or None if the
            simulation was stopped or an error occurred.
        """
        segment_start = self._path[segment_index]
        segment_end = self._path[segment_index + 1]
        segment_distance = self._segment_distances[segment_index]
        distance_into_segment = 0.0
        distance_accounted = 0.0

        while distance_into_segment < segment_distance:
            if self._state_machine.is_stopped:
                return None

            # Handle pause
            if not self._wait_for_running():
                return None

            tick_start = time.monotonic()

            # Read current speed (may change mid-segment)
            speed = self._speed_controller.speed_ms

            # Calculate distance to travel in this tick
            tick_interval = self._config.tick_interval_s
            distance_this_tick = speed * tick_interval

            # Advance along the segment
            distance_into_segment += distance_this_tick

            # Clamp to segment end
            if distance_into_segment >= segment_distance:
                # We've reached or passed the end of this segment
                actual_advance = segment_distance - (
                    distance_into_segment - distance_this_tick
                )
                distance_accounted += actual_advance
                fraction = 1.0
            else:
                distance_accounted += distance_this_tick
                fraction = distance_into_segment / segment_distance

            # Interpolate position
            position = interpolate_great_circle(
                segment_start, segment_end, fraction
            )

            # Apply GPS drift if enabled
            if self._config.drift_enabled:
                position = apply_drift(
                    position,
                    sigma_meters=self._config.drift_sigma_meters,
                )

            # Send to device
            try:
                self._location_service.set_location(
                    self._udid, position
                )
            except Exception as exc:
                logger.error(
                    "Failed to set location on %s: %s",
                    self._udid,
                    exc,
                )
                if self._on_error:
                    self._on_error(exc)
                with contextlib.suppress(SimulationStateError):
                    self._state_machine.transition("stop")
                return None

            # Notify progress
            total_distance_covered = distance_covered_so_far + distance_accounted
            elapsed = time.monotonic() - start_time
            progress = SimulationProgress(
                current_position=position,
                segment_index=segment_index,
                total_segments=len(self._segment_distances),
                distance_covered_m=min(
                    total_distance_covered, self._total_distance_m
                ),
                total_distance_m=self._total_distance_m,
                elapsed_time_s=elapsed,
                speed_ms=speed,
                state=self._state_machine.state,
            )
            self._fire_progress(progress)

            # If we've completed this segment, break to next
            if fraction >= 1.0:
                break

            # Sleep for the remainder of the tick interval
            tick_elapsed = time.monotonic() - tick_start
            sleep_time = max(0.0, tick_interval - tick_elapsed)
            if sleep_time > 0:
                self._interruptible_sleep(sleep_time)

        return distance_accounted

    def _wait_for_running(self) -> bool:
        """Block until the simulation is running (not paused), or detect stop.

        Returns:
            True if the simulation is now running.
            False if the simulation has been stopped.
        """
        while not self._state_machine.is_stopped:
            if (
                self._state_machine.wait_for_resume(timeout=0.1)
                and not self._state_machine.is_stopped
            ):
                return True
        return False

    def _interruptible_sleep(self, duration: float) -> None:
        """Sleep for the given duration, but wake up early if stopped.

        Breaks sleep into small chunks to respond to stop quickly.

        Args:
            duration: Total sleep duration in seconds.
        """
        chunk = 0.1
        remaining = duration
        while remaining > 0 and not self._state_machine.is_stopped:
            time.sleep(min(chunk, remaining))
            remaining -= chunk

    def _fire_progress(self, progress: SimulationProgress) -> None:
        """Invoke the progress callback, catching any exceptions.

        Args:
            progress: The current progress snapshot.
        """
        if self._on_progress is not None:
            try:
                self._on_progress(progress)
            except Exception:
                logger.exception("Error in on_progress callback")
