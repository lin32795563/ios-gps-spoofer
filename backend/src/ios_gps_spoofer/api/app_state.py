"""Application state container for the FastAPI server.

Holds references to the shared ``DeviceManager``, ``LocationService``,
and active ``PathSimulator`` instances.  This is a singleton-like object
created at server startup and torn down at shutdown.

The ``AppState`` class is NOT a global variable -- it is created by the
server factory and injected into routes via FastAPI dependency injection.

Thread Safety
-------------
``AppState`` coordinates access to active simulators via a
``threading.Lock``.  The underlying ``DeviceManager`` and
``LocationService`` have their own internal thread safety.
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path

from ios_gps_spoofer.api.models import FavoriteLocation
from ios_gps_spoofer.device.device_manager import DeviceManager
from ios_gps_spoofer.location.location_service import LocationService
from ios_gps_spoofer.simulation.path_simulator import PathSimulator
from ios_gps_spoofer.simulation.speed_profiles import ms_to_kmh

logger = logging.getLogger(__name__)

# File for persisting favorites (JSON)
_FAVORITES_FILE = Path(__file__).resolve().parent.parent.parent.parent.parent / "favorites.json"


class AppState:
    """Shared application state for the FastAPI server.

    Holds references to core services and manages active simulators.

    Usage::

        state = AppState()
        state.startup()
        # ... API routes use state ...
        state.shutdown()
    """

    def __init__(self) -> None:
        """Initialize application state with core services."""
        self._device_manager = DeviceManager()
        self._location_service = LocationService(self._device_manager)
        self._active_simulators: dict[str, PathSimulator] = {}
        self._lock = threading.Lock()
        self._favorites: list[FavoriteLocation] = []
        self._favorites_file = _FAVORITES_FILE

    @property
    def device_manager(self) -> DeviceManager:
        """The shared device manager."""
        return self._device_manager

    @property
    def location_service(self) -> LocationService:
        """The shared location service."""
        return self._location_service

    def startup(self) -> None:
        """Initialize services on server startup.

        Starts device polling and loads saved favorites.
        """
        self._device_manager.start_polling()
        self._load_favorites()
        logger.info("AppState started: device polling active")

    def shutdown(self) -> None:
        """Clean up all resources on server shutdown.

        Stops all active simulators, clears simulated locations,
        stops device polling, and saves favorites.
        """
        logger.info("AppState shutting down...")

        # Stop all active simulators
        self.stop_all_simulators()

        # Stop device polling and clean up connections
        self._device_manager.stop_polling()

        # Save favorites
        self._save_favorites()

        logger.info("AppState shutdown complete")

    # ------------------------------------------------------------------
    # Simulator management
    # ------------------------------------------------------------------

    def get_simulator(self, udid: str) -> PathSimulator | None:
        """Get the active simulator for a device, if any.

        Args:
            udid: Device UDID.

        Returns:
            The active ``PathSimulator``, or None if no simulation
            is running for this device.
        """
        with self._lock:
            return self._active_simulators.get(udid)

    def register_simulator(self, udid: str, simulator: PathSimulator) -> None:
        """Register an active simulator for a device.

        If a simulator is already registered for this device, it is
        stopped first.

        Args:
            udid: Device UDID.
            simulator: The new ``PathSimulator`` to register.
        """
        with self._lock:
            existing = self._active_simulators.get(udid)
            if existing is not None:
                logger.info(
                    "Stopping existing simulator for %s before registering new one",
                    udid,
                )
                self._stop_simulator_unsafe(existing)
            self._active_simulators[udid] = simulator

    def unregister_simulator(self, udid: str) -> None:
        """Remove the simulator registration for a device.

        Does not stop the simulator -- call ``stop_simulator()`` for that.

        Args:
            udid: Device UDID.
        """
        with self._lock:
            self._active_simulators.pop(udid, None)

    def stop_simulator(self, udid: str) -> bool:
        """Stop the active simulator for a device.

        Args:
            udid: Device UDID.

        Returns:
            True if a simulator was found and stopped, False if none was active.
        """
        with self._lock:
            simulator = self._active_simulators.pop(udid, None)
            if simulator is None:
                return False
            self._stop_simulator_unsafe(simulator)
            return True

    def stop_all_simulators(self) -> int:
        """Stop all active simulators.

        Returns:
            Number of simulators that were stopped.
        """
        with self._lock:
            count = len(self._active_simulators)
            for udid, simulator in list(self._active_simulators.items()):
                logger.info("Stopping simulator for %s", udid)
                self._stop_simulator_unsafe(simulator)
            self._active_simulators.clear()
        logger.info("Stopped %d simulators", count)
        return count

    def get_simulator_status(self, udid: str) -> dict[str, object] | None:
        """Get a status summary for a device's active simulator.

        Args:
            udid: Device UDID.

        Returns:
            Dictionary with state, speed, and progress information,
            or None if no simulator is active.
        """
        with self._lock:
            simulator = self._active_simulators.get(udid)
            if simulator is None:
                return None

        return {
            "udid": udid,
            "state": simulator.state.value,
            "speed_kmh": round(ms_to_kmh(simulator.speed_controller.speed_ms), 1),
        }

    @staticmethod
    def _stop_simulator_unsafe(simulator: PathSimulator) -> None:
        """Stop a simulator without holding the lock.

        Catches errors to avoid disrupting bulk-stop operations.

        Args:
            simulator: The simulator to stop.
        """
        try:
            from ios_gps_spoofer.simulation.state_machine import SimulationState

            if simulator.state not in (
                SimulationState.STOPPED,
                SimulationState.IDLE,
            ):
                simulator.stop()
                simulator.wait(timeout=2.0)
        except Exception:
            logger.exception(
                "Error stopping simulator for %s", simulator.udid
            )

    # ------------------------------------------------------------------
    # Favorites management
    # ------------------------------------------------------------------

    def get_favorites(self) -> list[FavoriteLocation]:
        """Return all saved favorite locations.

        Returns:
            List of ``FavoriteLocation`` objects.
        """
        return list(self._favorites)

    def add_favorite(self, favorite: FavoriteLocation) -> None:
        """Add a new favorite location.

        Args:
            favorite: The favorite to add.
        """
        self._favorites.append(favorite)
        self._save_favorites()
        logger.info("Added favorite: %s", favorite.name)

    def remove_favorite(self, index: int) -> FavoriteLocation | None:
        """Remove a favorite by index.

        Args:
            index: Zero-based index into the favorites list.

        Returns:
            The removed ``FavoriteLocation``, or None if index is invalid.
        """
        if 0 <= index < len(self._favorites):
            removed = self._favorites.pop(index)
            self._save_favorites()
            logger.info("Removed favorite: %s", removed.name)
            return removed
        return None

    def _load_favorites(self) -> None:
        """Load favorites from the JSON file."""
        import json

        if not self._favorites_file.exists():
            self._favorites = []
            return

        try:
            raw = self._favorites_file.read_text(encoding="utf-8")
            data = json.loads(raw)
            self._favorites = [FavoriteLocation(**item) for item in data]
            logger.info("Loaded %d favorites from %s", len(self._favorites), self._favorites_file)
        except Exception:
            logger.exception("Failed to load favorites from %s", self._favorites_file)
            self._favorites = []

    def _save_favorites(self) -> None:
        """Save favorites to the JSON file."""
        import json

        try:
            data = [fav.model_dump() for fav in self._favorites]
            self._favorites_file.parent.mkdir(parents=True, exist_ok=True)
            self._favorites_file.write_text(
                json.dumps(data, indent=2), encoding="utf-8"
            )
        except Exception:
            logger.exception("Failed to save favorites to %s", self._favorites_file)
