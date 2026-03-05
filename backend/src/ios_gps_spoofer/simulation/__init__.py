"""Path simulation engine for GPS route playback.

Public API::

    from ios_gps_spoofer.simulation import (
        PathSimulator,
        SimulationConfig,
        SimulationProgress,
        SimulationState,
        SpeedPreset,
        parse_gpx_file,
        parse_gpx_string,
    )

    # Parse a GPX file
    waypoints = parse_gpx_file("route.gpx")

    # Create and run a simulator
    simulator = PathSimulator(
        udid="device-udid",
        path=waypoints,
        location_service=location_service,
    )
    simulator.speed_controller.set_preset(SpeedPreset.CYCLING)
    simulator.start()
"""

from ios_gps_spoofer.simulation.exceptions import (
    EmptyPathError,
    GPXParseError,
    SimulationError,
    SimulationStateError,
    SpeedError,
)
from ios_gps_spoofer.simulation.gps_drift import apply_drift
from ios_gps_spoofer.simulation.gpx_parser import parse_gpx_file, parse_gpx_string
from ios_gps_spoofer.simulation.path_simulator import (
    PathSimulator,
    ProgressCallback,
    SimulationConfig,
    SimulationProgress,
)
from ios_gps_spoofer.simulation.speed_profiles import (
    SpeedController,
    SpeedPreset,
    kmh_to_ms,
    ms_to_kmh,
)
from ios_gps_spoofer.simulation.state_machine import (
    SimulationState,
    SimulationStateMachine,
)

__all__ = [
    "EmptyPathError",
    "GPXParseError",
    "PathSimulator",
    "ProgressCallback",
    "SimulationConfig",
    "SimulationError",
    "SimulationProgress",
    "SimulationState",
    "SimulationStateError",
    "SimulationStateMachine",
    "SpeedController",
    "SpeedError",
    "SpeedPreset",
    "apply_drift",
    "kmh_to_ms",
    "ms_to_kmh",
    "parse_gpx_file",
    "parse_gpx_string",
]
