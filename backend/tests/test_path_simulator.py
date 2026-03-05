"""Tests for ios_gps_spoofer.simulation.path_simulator module.

Tests cover:
- PathSimulator construction validation
- start/pause/resume/stop lifecycle
- Progress callback invocation
- Completion callback
- Error callback on device failure
- Speed change mid-simulation
- Drift enabled/disabled
- Stop during running and paused states
- Path with duplicate consecutive points (zero-length segments)
- Short path (2 points)
- Long path (many points)
- Loop path mode

The location service is mocked to avoid real device interaction.
Tick interval is set very short (0.01s) so tests complete quickly.
"""

import threading
import time
from unittest.mock import MagicMock

import pytest

from ios_gps_spoofer.location.coordinates import Coordinate
from ios_gps_spoofer.simulation.exceptions import (
    EmptyPathError,
    SimulationStateError,
)
from ios_gps_spoofer.simulation.path_simulator import (
    PathSimulator,
    SimulationConfig,
    SimulationProgress,
)
from ios_gps_spoofer.simulation.state_machine import SimulationState

# Short tick interval for fast tests
_FAST_CONFIG = SimulationConfig(
    drift_enabled=False,
    tick_interval_s=0.01,
)

_FAST_CONFIG_WITH_DRIFT = SimulationConfig(
    drift_enabled=True,
    drift_sigma_meters=1.0,
    tick_interval_s=0.01,
)


def _make_path(n: int = 3, spacing: float = 0.0001) -> list[Coordinate]:
    """Create a simple test path with n points along a line.

    Default spacing of 0.0001 degrees is approximately 15.7 meters,
    which at max speed (278 m/s) with tick_interval=0.01s traverses
    in about 6 ticks -- fast enough for testing.
    """
    return [
        Coordinate(latitude=25.0 + i * spacing, longitude=121.0 + i * spacing)
        for i in range(n)
    ]


def _set_max_speed(sim: PathSimulator) -> None:
    """Set simulation to maximum speed for fast test completion."""
    from ios_gps_spoofer.simulation.speed_profiles import MAX_SPEED_MS
    sim.speed_controller.set_speed_ms(MAX_SPEED_MS)


def _make_mock_location_service() -> MagicMock:
    """Create a mock LocationService."""
    return MagicMock()


# =====================================================================
# Construction
# =====================================================================

class TestPathSimulatorInit:
    """Tests for PathSimulator constructor."""

    def test_valid_construction(self) -> None:
        path = _make_path()
        sim = PathSimulator(
            udid="d1",
            path=path,
            location_service=_make_mock_location_service(),
            config=_FAST_CONFIG,
        )
        assert sim.udid == "d1"
        assert sim.state == SimulationState.IDLE
        assert sim.segment_count == 2
        assert sim.total_distance_m > 0

    def test_empty_udid_raises(self) -> None:
        with pytest.raises(ValueError, match="non-empty"):
            PathSimulator(
                udid="",
                path=_make_path(),
                location_service=_make_mock_location_service(),
            )

    def test_none_location_service_raises(self) -> None:
        with pytest.raises(ValueError, match="location_service"):
            PathSimulator(
                udid="d1",
                path=_make_path(),
                location_service=None,  # type: ignore[arg-type]
            )

    def test_empty_path_raises(self) -> None:
        with pytest.raises(EmptyPathError, match="at least 2"):
            PathSimulator(
                udid="d1",
                path=[],
                location_service=_make_mock_location_service(),
            )

    def test_single_point_path_raises(self) -> None:
        with pytest.raises(EmptyPathError):
            PathSimulator(
                udid="d1",
                path=[Coordinate(latitude=25.0, longitude=121.0)],
                location_service=_make_mock_location_service(),
            )

    def test_path_is_defensively_copied(self) -> None:
        original = _make_path()
        sim = PathSimulator(
            udid="d1",
            path=original,
            location_service=_make_mock_location_service(),
            config=_FAST_CONFIG,
        )
        original.append(Coordinate(latitude=0.0, longitude=0.0))
        assert len(sim.path) == 3  # should not have changed

    def test_default_config_applied(self) -> None:
        sim = PathSimulator(
            udid="d1",
            path=_make_path(),
            location_service=_make_mock_location_service(),
        )
        assert sim.state == SimulationState.IDLE


# =====================================================================
# Start / Stop lifecycle
# =====================================================================

class TestSimulationLifecycle:
    """Tests for start/pause/resume/stop."""

    def test_start_changes_state_to_running(self) -> None:
        sim = PathSimulator(
            udid="d1",
            path=_make_path(),
            location_service=_make_mock_location_service(),
            config=_FAST_CONFIG,
        )
        sim.start()
        assert sim.state == SimulationState.RUNNING
        sim.stop()
        sim.wait(timeout=2.0)

    def test_start_twice_raises(self) -> None:
        sim = PathSimulator(
            udid="d1",
            path=_make_path(),
            location_service=_make_mock_location_service(),
            config=_FAST_CONFIG,
        )
        sim.start()
        with pytest.raises(SimulationStateError):
            sim.start()
        sim.stop()
        sim.wait(timeout=2.0)

    def test_pause_from_running(self) -> None:
        sim = PathSimulator(
            udid="d1",
            path=_make_path(20),
            location_service=_make_mock_location_service(),
            config=_FAST_CONFIG,
        )
        sim.start()
        time.sleep(0.05)  # let it run a bit
        sim.pause()
        assert sim.state == SimulationState.PAUSED
        sim.stop()
        sim.wait(timeout=2.0)

    def test_resume_from_paused(self) -> None:
        sim = PathSimulator(
            udid="d1",
            path=_make_path(20),
            location_service=_make_mock_location_service(),
            config=_FAST_CONFIG,
        )
        sim.start()
        time.sleep(0.05)
        sim.pause()
        sim.resume()
        assert sim.state == SimulationState.RUNNING
        sim.stop()
        sim.wait(timeout=2.0)

    def test_stop_from_running(self) -> None:
        sim = PathSimulator(
            udid="d1",
            path=_make_path(20),
            location_service=_make_mock_location_service(),
            config=_FAST_CONFIG,
        )
        sim.start()
        time.sleep(0.05)
        sim.stop()
        sim.wait(timeout=2.0)
        assert sim.state == SimulationState.STOPPED

    def test_stop_from_paused(self) -> None:
        sim = PathSimulator(
            udid="d1",
            path=_make_path(20),
            location_service=_make_mock_location_service(),
            config=_FAST_CONFIG,
        )
        sim.start()
        time.sleep(0.05)
        sim.pause()
        sim.stop()
        sim.wait(timeout=2.0)
        assert sim.state == SimulationState.STOPPED

    def test_stop_before_start_raises(self) -> None:
        sim = PathSimulator(
            udid="d1",
            path=_make_path(),
            location_service=_make_mock_location_service(),
            config=_FAST_CONFIG,
        )
        with pytest.raises(SimulationStateError):
            sim.stop()


# =====================================================================
# Simulation completion
# =====================================================================

class TestSimulationCompletion:
    """Tests for simulation running to completion."""

    def test_simulation_completes(self) -> None:
        """Short path should complete within a reasonable time."""
        mock_ls = _make_mock_location_service()
        completed = threading.Event()

        sim = PathSimulator(
            udid="d1",
            path=_make_path(2, spacing=0.0001),
            location_service=mock_ls,
            config=_FAST_CONFIG,
            on_complete=completed.set,
        )
        _set_max_speed(sim)
        sim.start()

        assert completed.wait(timeout=5.0), "Simulation did not complete"
        assert sim.state == SimulationState.STOPPED
        # set_location should have been called at least once
        assert mock_ls.set_location.call_count >= 1

    def test_progress_callback_invoked(self) -> None:
        mock_ls = _make_mock_location_service()
        progress_reports: list[SimulationProgress] = []

        sim = PathSimulator(
            udid="d1",
            path=_make_path(2, spacing=0.0001),
            location_service=mock_ls,
            config=_FAST_CONFIG,
            on_progress=progress_reports.append,
        )
        _set_max_speed(sim)
        sim.start()
        sim.wait(timeout=5.0)

        assert len(progress_reports) >= 1
        # Last progress should be complete
        last = progress_reports[-1]
        assert isinstance(last.current_position, Coordinate)
        assert last.total_segments > 0
        assert last.elapsed_time_s >= 0

    def test_progress_to_dict(self) -> None:
        """SimulationProgress.to_dict should be JSON-serializable."""
        mock_ls = _make_mock_location_service()
        progress_reports: list[SimulationProgress] = []

        sim = PathSimulator(
            udid="d1",
            path=_make_path(2, spacing=0.0001),
            location_service=mock_ls,
            config=_FAST_CONFIG,
            on_progress=progress_reports.append,
        )
        _set_max_speed(sim)
        sim.start()
        sim.wait(timeout=5.0)

        assert len(progress_reports) >= 1
        d = progress_reports[0].to_dict()
        assert "current_position" in d
        assert "fraction_complete" in d
        assert "state" in d

    def test_set_location_receives_coordinates(self) -> None:
        """Each set_location call should receive a Coordinate."""
        mock_ls = _make_mock_location_service()
        sim = PathSimulator(
            udid="d1",
            path=_make_path(2, spacing=0.0001),
            location_service=mock_ls,
            config=_FAST_CONFIG,
        )
        _set_max_speed(sim)
        sim.start()
        sim.wait(timeout=5.0)

        for c in mock_ls.set_location.call_args_list:
            assert c[0][0] == "d1"  # udid
            assert isinstance(c[0][1], Coordinate)  # coordinate


# =====================================================================
# Error handling
# =====================================================================

class TestErrorHandling:
    """Tests for device error during simulation."""

    def test_error_callback_on_device_failure(self) -> None:
        mock_ls = _make_mock_location_service()
        mock_ls.set_location.side_effect = OSError("USB disconnected")
        errors: list[Exception] = []

        sim = PathSimulator(
            udid="d1",
            path=_make_path(3),
            location_service=mock_ls,
            config=_FAST_CONFIG,
            on_error=errors.append,
        )
        _set_max_speed(sim)
        sim.start()
        sim.wait(timeout=5.0)

        assert len(errors) == 1
        assert "USB disconnected" in str(errors[0])
        assert sim.state == SimulationState.STOPPED

    def test_simulation_stops_on_device_error(self) -> None:
        mock_ls = _make_mock_location_service()
        mock_ls.set_location.side_effect = ConnectionError("lost")

        sim = PathSimulator(
            udid="d1",
            path=_make_path(3),
            location_service=mock_ls,
            config=_FAST_CONFIG,
        )
        _set_max_speed(sim)
        sim.start()
        sim.wait(timeout=5.0)

        assert sim.state == SimulationState.STOPPED
        # Should have attempted set_location only once before stopping
        assert mock_ls.set_location.call_count == 1

    def test_progress_callback_exception_does_not_crash(self) -> None:
        mock_ls = _make_mock_location_service()

        def bad_callback(progress: SimulationProgress) -> None:
            raise RuntimeError("callback error")

        completed = threading.Event()
        sim = PathSimulator(
            udid="d1",
            path=_make_path(2, spacing=0.0001),
            location_service=mock_ls,
            config=_FAST_CONFIG,
            on_progress=bad_callback,
            on_complete=completed.set,
        )
        _set_max_speed(sim)
        sim.start()

        # Should still complete despite callback errors
        assert completed.wait(timeout=5.0)


# =====================================================================
# Speed changes mid-simulation
# =====================================================================

class TestSpeedChanges:
    """Tests for changing speed during simulation."""

    def test_speed_change_during_simulation(self) -> None:
        mock_ls = _make_mock_location_service()
        completed = threading.Event()

        # Use a path long enough that slow speed won't finish instantly
        path = _make_path(5, spacing=0.001)
        sim = PathSimulator(
            udid="d1",
            path=path,
            location_service=mock_ls,
            config=_FAST_CONFIG,
            on_complete=completed.set,
        )
        sim.speed_controller.set_speed_kmh(1.0)  # very slow
        sim.start()

        time.sleep(0.1)
        # Speed up to maximum
        from ios_gps_spoofer.simulation.speed_profiles import MAX_SPEED_MS
        sim.speed_controller.set_speed_ms(MAX_SPEED_MS)

        assert completed.wait(timeout=10.0), "Simulation did not complete after speed change"


# =====================================================================
# GPS drift
# =====================================================================

class TestDrift:
    """Tests for GPS drift during simulation."""

    def test_drift_disabled_produces_exact_positions(self) -> None:
        """With drift disabled, positions should lie exactly on the path."""
        mock_ls = _make_mock_location_service()
        path = [
            Coordinate(latitude=0.0, longitude=0.0),
            Coordinate(latitude=0.0, longitude=1.0),
        ]
        sim = PathSimulator(
            udid="d1",
            path=path,
            location_service=mock_ls,
            config=SimulationConfig(drift_enabled=False, tick_interval_s=0.01),
        )
        sim.speed_controller.set_speed_kmh(600.0)
        sim.start()
        sim.wait(timeout=5.0)

        # All positions should have latitude exactly 0.0
        for c in mock_ls.set_location.call_args_list:
            coord = c[0][1]
            assert coord.latitude == pytest.approx(0.0, abs=1e-10)

    def test_drift_enabled_offsets_positions(self) -> None:
        """With drift enabled, positions should be slightly offset."""
        mock_ls = _make_mock_location_service()
        path = [
            Coordinate(latitude=0.0, longitude=0.0),
            Coordinate(latitude=0.0, longitude=1.0),
        ]
        sim = PathSimulator(
            udid="d1",
            path=path,
            location_service=mock_ls,
            config=_FAST_CONFIG_WITH_DRIFT,
        )
        sim.speed_controller.set_speed_kmh(600.0)
        sim.start()
        sim.wait(timeout=5.0)

        # At least one position should have non-zero latitude (drift)
        has_drift = any(
            c[0][1].latitude != 0.0
            for c in mock_ls.set_location.call_args_list
        )
        assert has_drift, "Expected drift to offset at least one position"


# =====================================================================
# Edge cases
# =====================================================================

class TestEdgeCases:
    """Edge case tests."""

    def test_path_with_duplicate_consecutive_points(self) -> None:
        """Duplicate consecutive points (zero-length segment) should be skipped."""
        mock_ls = _make_mock_location_service()
        completed = threading.Event()
        path = [
            Coordinate(latitude=25.0, longitude=121.0),
            Coordinate(latitude=25.0, longitude=121.0),  # duplicate
            Coordinate(latitude=25.0001, longitude=121.0001),
        ]
        sim = PathSimulator(
            udid="d1",
            path=path,
            location_service=mock_ls,
            config=_FAST_CONFIG,
            on_complete=completed.set,
        )
        _set_max_speed(sim)
        sim.start()
        assert completed.wait(timeout=5.0)

    def test_two_point_path(self) -> None:
        """Minimum valid path (2 points) should work."""
        mock_ls = _make_mock_location_service()
        completed = threading.Event()
        path = [
            Coordinate(latitude=25.0, longitude=121.0),
            Coordinate(latitude=25.0001, longitude=121.0001),
        ]
        sim = PathSimulator(
            udid="d1",
            path=path,
            location_service=mock_ls,
            config=_FAST_CONFIG,
            on_complete=completed.set,
        )
        _set_max_speed(sim)
        sim.start()
        assert completed.wait(timeout=5.0)
        assert mock_ls.set_location.call_count >= 1

    def test_wait_without_start(self) -> None:
        """wait() should return immediately if never started."""
        sim = PathSimulator(
            udid="d1",
            path=_make_path(),
            location_service=_make_mock_location_service(),
            config=_FAST_CONFIG,
        )
        sim.wait(timeout=0.1)  # should not hang

    def test_properties(self) -> None:
        """Test various read-only properties."""
        path = _make_path(5)
        sim = PathSimulator(
            udid="test-device",
            path=path,
            location_service=_make_mock_location_service(),
            config=_FAST_CONFIG,
        )
        assert sim.udid == "test-device"
        assert len(sim.path) == 5
        assert sim.segment_count == 4
        assert sim.total_distance_m > 0


# =====================================================================
# Loop path
# =====================================================================

class TestLoopPath:
    """Tests for loop_path mode."""

    def test_loop_continues_after_completion(self) -> None:
        """With loop_path=True, simulation should continue past the end."""
        mock_ls = _make_mock_location_service()
        progress_reports: list[SimulationProgress] = []

        path = [
            Coordinate(latitude=25.0, longitude=121.0),
            Coordinate(latitude=25.0001, longitude=121.0001),
        ]
        config = SimulationConfig(
            drift_enabled=False,
            tick_interval_s=0.01,
            loop_path=True,
        )
        sim = PathSimulator(
            udid="d1",
            path=path,
            location_service=mock_ls,
            config=config,
            on_progress=progress_reports.append,
        )
        _set_max_speed(sim)
        sim.start()

        # Let it run for a bit (should loop multiple times)
        time.sleep(0.5)
        sim.stop()
        sim.wait(timeout=2.0)

        assert sim.state == SimulationState.STOPPED
        # Should have many more calls than a single traversal
        assert mock_ls.set_location.call_count > 2
