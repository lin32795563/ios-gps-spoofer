"""Location simulation service for iOS devices.

This module provides the ``LocationService`` class, which is the single
entry-point for the rest of the application to set, get, and clear
simulated GPS locations on connected iOS devices.

Architecture
------------
``LocationService`` uses two different approaches depending on iOS version:

- **iOS 14-16 (DDI)**: Uses ``DtSimulateLocation`` via the lockdown client.
- **iOS 17+ (Tunnel)**: Uses ``DvtSecureSocketProxyService`` + ``LocationSimulation``
  via the RSD obtained from tunneld.  This is necessary because iOS 17+
  (and especially iOS 26+) does not expose ``com.apple.dt.simulatelocation``
  directly through the RSD -- location simulation must go through the DVT
  (Developer Tools) channel.

DVT connections for iOS 17+ are **cached per device** to avoid the overhead
and instability of creating a new connection for every location update.
If a cached connection fails, it is automatically discarded and a fresh
connection is established (retry-once strategy).

``LocationService`` does NOT manage device connections or tunnels -- those
responsibilities belong to ``DeviceManager``.  It obtains the appropriate
``LockdownServiceProvider`` and iOS version category from ``DeviceManager``.

Thread Safety
-------------
``LocationService`` is thread-safe.  A ``threading.Lock`` protects
all mutable state including the DVT session cache.

Lifecycle
---------
1. Create ``LocationService`` with a reference to ``DeviceManager``.
2. Call ``set_location(udid, coordinate)`` to spoof GPS.
3. Call ``get_current_location(udid)`` to query what was last set.
4. Call ``clear_location(udid)`` to restore real GPS.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import TYPE_CHECKING

from ios_gps_spoofer.device.models import IOSVersionCategory
from ios_gps_spoofer.location.coordinates import Coordinate
from ios_gps_spoofer.location.exceptions import (
    LocationClearError,
    LocationServiceNotReadyError,
    LocationSetError,
)

if TYPE_CHECKING:
    from ios_gps_spoofer.device.device_manager import DeviceManager

logger = logging.getLogger(__name__)


class _DvtSession:
    """Wraps a cached DVT proxy connection for a single device."""

    def __init__(self, service_provider: object) -> None:
        from pymobiledevice3.services.dvt.dvt_secure_socket_proxy import (
            DvtSecureSocketProxyService,
        )

        self._dvt = DvtSecureSocketProxyService(lockdown=service_provider)
        self._dvt.__enter__()
        self._closed = False

    def set_location(self, latitude: float, longitude: float) -> None:
        from pymobiledevice3.services.dvt.instruments.location_simulation import (
            LocationSimulation,
        )

        LocationSimulation(self._dvt).set(latitude, longitude)

    def clear_location(self) -> None:
        from pymobiledevice3.services.dvt.instruments.location_simulation import (
            LocationSimulation,
        )

        LocationSimulation(self._dvt).clear()

    def close(self) -> None:
        if not self._closed:
            self._closed = True
            try:
                self._dvt.__exit__(None, None, None)
            except Exception:
                pass


class LocationService:
    """Manages GPS location simulation for connected iOS devices.

    Usage::

        from ios_gps_spoofer.device import DeviceManager
        from ios_gps_spoofer.location import LocationService, Coordinate

        device_manager = DeviceManager()
        location_service = LocationService(device_manager)

        # After device is connected and ready...
        coord = Coordinate(latitude=25.0330, longitude=121.5654)
        location_service.set_location(udid, coord)

        # Check what was set
        current = location_service.get_current_location(udid)

        # Restore real GPS
        location_service.clear_location(udid)
    """

    def __init__(self, device_manager: DeviceManager) -> None:
        if device_manager is None:
            raise ValueError("device_manager must not be None")

        self._device_manager = device_manager

        # Track the last-set location per device (keyed by UDID)
        self._current_locations: dict[str, Coordinate] = {}

        # Track whether location simulation is active per device
        self._simulation_active: dict[str, bool] = {}

        # Cached DVT sessions for iOS 17+ devices (keyed by UDID)
        self._dvt_sessions: dict[str, _DvtSession] = {}

        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_location(self, udid: str, coordinate: Coordinate) -> None:
        """Set a simulated GPS location on the specified device.

        For iOS 17+, uses a cached DVT connection with automatic retry
        on failure (creates a fresh connection and retries once).
        """
        if not isinstance(coordinate, Coordinate):
            raise TypeError(
                f"coordinate must be a Coordinate instance, "
                f"got {type(coordinate).__name__}"
            )

        logger.info("Setting location on %s to %s", udid, coordinate)

        try:
            service_provider = self._device_manager.get_service_provider(udid)
        except Exception as exc:
            raise LocationServiceNotReadyError(udid, str(exc)) from exc

        try:
            ios_category = self._device_manager.get_ios_category(udid)
        except Exception:
            ios_category = IOSVersionCategory.DDI

        try:
            if ios_category == IOSVersionCategory.TUNNEL:
                self._set_location_dvt_cached(udid, service_provider, coordinate)
            else:
                self._set_location_dt_sim(service_provider, coordinate)
        except Exception as exc:
            raise LocationSetError(udid, str(exc)) from exc

        with self._lock:
            self._current_locations[udid] = coordinate
            self._simulation_active[udid] = True

        logger.info(
            "Location set on %s: lat=%.6f lon=%.6f",
            udid, coordinate.latitude, coordinate.longitude,
        )

    def clear_location(self, udid: str) -> None:
        """Clear the simulated location and restore real GPS."""
        logger.info("Clearing simulated location on %s", udid)

        try:
            service_provider = self._device_manager.get_service_provider(udid)
        except Exception as exc:
            raise LocationServiceNotReadyError(udid, str(exc)) from exc

        try:
            ios_category = self._device_manager.get_ios_category(udid)
        except Exception:
            ios_category = IOSVersionCategory.DDI

        try:
            if ios_category == IOSVersionCategory.TUNNEL:
                self._clear_location_dvt_cached(udid, service_provider)
            else:
                self._clear_location_dt_sim(service_provider)
        except Exception as exc:
            raise LocationClearError(udid, str(exc)) from exc

        with self._lock:
            self._current_locations.pop(udid, None)
            self._simulation_active[udid] = False

        logger.info("Simulated location cleared on %s", udid)

    # ------------------------------------------------------------------
    # Implementation: DtSimulateLocation (iOS 14-16)
    # ------------------------------------------------------------------

    @staticmethod
    def _set_location_dt_sim(
        service_provider: object,
        coordinate: Coordinate,
    ) -> None:
        from pymobiledevice3.services.simulate_location import (
            DtSimulateLocation,
        )

        location_sim = DtSimulateLocation(service_provider)
        location_sim.set(coordinate.latitude, coordinate.longitude)

    @staticmethod
    def _clear_location_dt_sim(service_provider: object) -> None:
        from pymobiledevice3.services.simulate_location import (
            DtSimulateLocation,
        )

        location_sim = DtSimulateLocation(service_provider)
        location_sim.clear()

    # ------------------------------------------------------------------
    # Implementation: Cached DVT LocationSimulation (iOS 17+)
    # ------------------------------------------------------------------

    def _get_dvt_session(self, udid: str, service_provider: object) -> _DvtSession:
        """Get or create a cached DVT session for the device."""
        with self._lock:
            session = self._dvt_sessions.get(udid)
            if session is not None:
                return session

        # Create outside lock (connection may take time)
        logger.debug("Creating new DVT session for %s", udid)
        session = _DvtSession(service_provider)

        with self._lock:
            # Another thread may have created one while we were connecting
            existing = self._dvt_sessions.get(udid)
            if existing is not None:
                session.close()
                return existing
            self._dvt_sessions[udid] = session
            return session

    def _discard_dvt_session(self, udid: str) -> None:
        """Close and remove the cached DVT session for a device."""
        with self._lock:
            session = self._dvt_sessions.pop(udid, None)
        if session is not None:
            logger.debug("Discarding DVT session for %s", udid)
            session.close()

    def _set_location_dvt_cached(
        self,
        udid: str,
        service_provider: object,
        coordinate: Coordinate,
    ) -> None:
        """Set location via cached DVT session. Retries once on failure."""
        for attempt in range(2):
            session = self._get_dvt_session(udid, service_provider)
            try:
                session.set_location(coordinate.latitude, coordinate.longitude)
                return
            except Exception as exc:
                logger.warning(
                    "DVT set_location failed for %s (attempt %d): %s",
                    udid, attempt + 1, exc,
                )
                self._discard_dvt_session(udid)
                if attempt == 1:
                    raise
                # Brief pause before retry
                time.sleep(0.5)

    def _clear_location_dvt_cached(
        self,
        udid: str,
        service_provider: object,
    ) -> None:
        """Clear location via cached DVT session. Retries once on failure."""
        for attempt in range(2):
            session = self._get_dvt_session(udid, service_provider)
            try:
                session.clear_location()
                return
            except Exception as exc:
                logger.warning(
                    "DVT clear_location failed for %s (attempt %d): %s",
                    udid, attempt + 1, exc,
                )
                self._discard_dvt_session(udid)
                if attempt == 1:
                    raise
                time.sleep(0.5)

    # ------------------------------------------------------------------
    # Read-only state queries
    # ------------------------------------------------------------------

    def get_current_location(self, udid: str) -> Coordinate | None:
        """Return the most recently set simulated location for a device.

        This does NOT read from the device -- it returns the last
        coordinate that was successfully sent via ``set_location()``.
        """
        with self._lock:
            return self._current_locations.get(udid)

    def is_simulation_active(self, udid: str) -> bool:
        """Check whether location simulation is currently active on a device."""
        with self._lock:
            return self._simulation_active.get(udid, False)

    def cleanup_device(self, udid: str) -> None:
        """Remove all location state and close DVT session for a disconnected device."""
        self._discard_dvt_session(udid)
        with self._lock:
            self._current_locations.pop(udid, None)
            self._simulation_active.pop(udid, None)
        logger.debug("Cleaned up location state for device %s", udid)

    def get_status(self, udid: str) -> dict[str, object]:
        """Return a JSON-serializable status summary for a device."""
        with self._lock:
            active = self._simulation_active.get(udid, False)
            coord = self._current_locations.get(udid)

        return {
            "udid": udid,
            "simulation_active": active,
            "current_location": coord.to_dict() if coord else None,
        }
