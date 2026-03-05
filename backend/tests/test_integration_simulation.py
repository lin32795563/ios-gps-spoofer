"""Integration tests: GPX parsing -> PathSimulator -> LocationService.

These tests verify the complete simulation workflow:
1. Parse a GPX file/string into coordinates
2. Create a PathSimulator with those coordinates
3. Run the simulation with a mocked LocationService
4. Verify positions are sent, progress is reported, completion fires

The LocationService is mocked to avoid needing a real device.
"""

import threading
import time
from unittest.mock import MagicMock

from ios_gps_spoofer.location.coordinates import Coordinate
from ios_gps_spoofer.simulation.gpx_parser import parse_gpx_string
from ios_gps_spoofer.simulation.path_simulator import (
    PathSimulator,
    SimulationConfig,
    SimulationProgress,
)
from ios_gps_spoofer.simulation.speed_profiles import MAX_SPEED_MS
from ios_gps_spoofer.simulation.state_machine import SimulationState

_GPX_SAMPLE = """\
<?xml version="1.0" encoding="UTF-8"?>
<gpx xmlns="http://www.topografix.com/GPX/1/1" version="1.1">
  <trk>
    <name>Test Route</name>
    <trkseg>
      <trkpt lat="25.0330" lon="121.5654"/>
      <trkpt lat="25.0331" lon="121.5655"/>
      <trkpt lat="25.0332" lon="121.5656"/>
      <trkpt lat="25.0333" lon="121.5657"/>
    </trkseg>
  </trk>
</gpx>
"""

_FAST_CONFIG = SimulationConfig(
    drift_enabled=False,
    tick_interval_s=0.01,
)


class TestGPXToSimulation:
    """End-to-end: GPX parsing -> path simulation."""

    def test_parse_gpx_and_simulate(self) -> None:
        """Parse GPX, create simulator, run to completion."""
        waypoints = parse_gpx_string(_GPX_SAMPLE)
        assert len(waypoints) == 4

        mock_ls = MagicMock()
        completed = threading.Event()
        progress_reports: list[SimulationProgress] = []

        sim = PathSimulator(
            udid="integration-device",
            path=waypoints,
            location_service=mock_ls,
            config=_FAST_CONFIG,
            on_progress=progress_reports.append,
            on_complete=completed.set,
        )
        sim.speed_controller.set_speed_ms(MAX_SPEED_MS)
        sim.start()

        assert completed.wait(timeout=10.0), "Simulation did not complete"
        assert sim.state == SimulationState.STOPPED

        # Verify set_location was called multiple times
        assert mock_ls.set_location.call_count >= 3

        # Verify all calls used the correct UDID
        for call_args in mock_ls.set_location.call_args_list:
            assert call_args[0][0] == "integration-device"
            assert isinstance(call_args[0][1], Coordinate)

        # Verify progress was reported
        assert len(progress_reports) >= 3
        last_progress = progress_reports[-1]
        assert last_progress.fraction_complete >= 0.9

    def test_pause_resume_stop_during_gpx_simulation(self) -> None:
        """Pause, resume, then stop a GPX-based simulation."""
        waypoints = parse_gpx_string(_GPX_SAMPLE)
        mock_ls = MagicMock()

        # Use slower speed so there's time to pause
        sim = PathSimulator(
            udid="pause-test",
            path=waypoints,
            location_service=mock_ls,
            config=_FAST_CONFIG,
        )
        sim.speed_controller.set_speed_ms(1.0)  # slow
        sim.start()

        time.sleep(0.1)
        sim.pause()
        assert sim.state == SimulationState.PAUSED

        # Record call count while paused
        calls_while_paused = mock_ls.set_location.call_count
        time.sleep(0.2)
        # Should not have progressed while paused
        assert mock_ls.set_location.call_count == calls_while_paused

        sim.resume()
        time.sleep(0.1)
        sim.stop()
        sim.wait(timeout=2.0)

        assert sim.state == SimulationState.STOPPED
        # Should have progressed after resume
        assert mock_ls.set_location.call_count > calls_while_paused


class TestSimulationWithDrift:
    """Tests for drift in the integrated pipeline."""

    def test_drift_applied_during_simulation(self) -> None:
        """Verify drift is applied when enabled."""
        waypoints = [
            Coordinate(latitude=0.0, longitude=0.0),
            Coordinate(latitude=0.0, longitude=0.001),
        ]
        mock_ls = MagicMock()
        completed = threading.Event()

        config = SimulationConfig(
            drift_enabled=True,
            drift_sigma_meters=3.0,
            tick_interval_s=0.01,
        )
        sim = PathSimulator(
            udid="drift-test",
            path=waypoints,
            location_service=mock_ls,
            config=config,
            on_complete=completed.set,
        )
        sim.speed_controller.set_speed_ms(MAX_SPEED_MS)
        sim.start()
        assert completed.wait(timeout=10.0)

        # With drift sigma=3m, latitude should deviate from 0.0
        has_lat_drift = any(
            call_args[0][1].latitude != 0.0
            for call_args in mock_ls.set_location.call_args_list
        )
        assert has_lat_drift, "Expected drift to change latitude"


class TestMultipleSimulators:
    """Tests for running multiple simulators concurrently."""

    def test_two_simulators_different_devices(self) -> None:
        """Two simulators for different devices can run concurrently."""
        waypoints = parse_gpx_string(_GPX_SAMPLE)
        mock_ls = MagicMock()

        completed_a = threading.Event()
        completed_b = threading.Event()

        sim_a = PathSimulator(
            udid="device-a",
            path=waypoints,
            location_service=mock_ls,
            config=_FAST_CONFIG,
            on_complete=completed_a.set,
        )
        sim_b = PathSimulator(
            udid="device-b",
            path=waypoints,
            location_service=mock_ls,
            config=_FAST_CONFIG,
            on_complete=completed_b.set,
        )

        sim_a.speed_controller.set_speed_ms(MAX_SPEED_MS)
        sim_b.speed_controller.set_speed_ms(MAX_SPEED_MS)

        sim_a.start()
        sim_b.start()

        assert completed_a.wait(timeout=10.0), "Simulator A did not complete"
        assert completed_b.wait(timeout=10.0), "Simulator B did not complete"

        # Both should have sent locations
        device_a_calls = [
            c for c in mock_ls.set_location.call_args_list
            if c[0][0] == "device-a"
        ]
        device_b_calls = [
            c for c in mock_ls.set_location.call_args_list
            if c[0][0] == "device-b"
        ]
        assert len(device_a_calls) >= 1
        assert len(device_b_calls) >= 1


class TestDeviceErrorDuringSimulation:
    """Integration test for device error mid-simulation."""

    def test_device_disconnect_stops_simulation(self) -> None:
        """If set_location raises, simulation should stop and report error."""
        waypoints = parse_gpx_string(_GPX_SAMPLE)
        mock_ls = MagicMock()

        call_count = 0

        def fail_after_3_calls(udid: str, coord: Coordinate) -> None:
            nonlocal call_count
            call_count += 1
            if call_count > 3:
                raise OSError("USB disconnected during simulation")

        mock_ls.set_location.side_effect = fail_after_3_calls

        errors: list[Exception] = []
        sim = PathSimulator(
            udid="disconnect-test",
            path=waypoints,
            location_service=mock_ls,
            config=_FAST_CONFIG,
            on_error=errors.append,
        )
        sim.speed_controller.set_speed_ms(MAX_SPEED_MS)
        sim.start()
        sim.wait(timeout=10.0)

        assert sim.state == SimulationState.STOPPED
        assert len(errors) == 1
        assert "USB disconnected" in str(errors[0])
