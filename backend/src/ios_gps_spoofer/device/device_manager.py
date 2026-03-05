"""Device connection manager for iOS devices.

This module is the single entry-point for the rest of the application to
discover, connect to, and manage iOS device sessions.  It handles:

- USB device enumeration via usbmux (iOS 14-16)
- Tunneld-based device discovery via ``pymobiledevice3.tunneld`` API (iOS 17+)
- Lockdown client creation and pairing (iOS 14-16)
- iOS version detection and code-path routing
- Developer Disk Image mounting (iOS 14-16)
- Service provider abstraction for location simulation
- Clean resource teardown

iOS 17+ Tunnel Architecture
---------------------------
Instead of managing tunnels directly (which requires administrator privileges
and WinTun drivers), this module relies on the ``pymobiledevice3 remote
tunneld`` daemon running externally (typically started with admin rights).
The tunneld exposes an HTTP API at ``127.0.0.1:49151`` that lists active
tunnel connections.  We call ``get_tunneld_devices()`` or
``get_tunneld_device_by_udid()`` to obtain ``RemoteServiceDiscoveryService``
instances that are already connected through the tunnel.

Design decisions
----------------
* **Thread safety** -- All mutable state lives in ``DeviceManager`` and is
  protected by a ``threading.Lock``.  The polling loop runs on a dedicated
  daemon thread so the main / asyncio thread is never blocked.
* **Resource cleanup** -- Every lockdown client and RSD reference is tracked
  and cleaned up on disconnect, even on crash paths.
* **Callback-based notifications** -- Callers register callbacks for
  ``on_device_connected`` / ``on_device_disconnected`` / ``on_state_changed``
  instead of polling, keeping the API layer decoupled.
* **Service provider abstraction** -- ``get_service_provider(udid)`` returns
  the appropriate ``LockdownServiceProvider`` for any iOS version, hiding
  the DDI vs tunneld distinction from the location module.
"""

from __future__ import annotations

import logging
import platform
import threading
from collections.abc import Callable
from typing import Any

from pymobiledevice3.exceptions import (
    ConnectionFailedError,
    MuxException,
    PairingError,
)
from pymobiledevice3.lockdown import LockdownClient, create_using_usbmux
from pymobiledevice3.lockdown_service_provider import LockdownServiceProvider
from pymobiledevice3.usbmux import MuxDevice
from pymobiledevice3.usbmux import list_devices as usbmux_list_devices

from ios_gps_spoofer.device.exceptions import (
    DDIMountError,
    DeveloperModeError,
    DeviceConnectionError,
    DeviceNotFoundError,
    DevicePairingError,
    TunnelError,
    UnsupportedIOSVersionError,
)
from ios_gps_spoofer.device.models import (
    ConnectionState,
    DeviceConnection,
    DeviceInfo,
    IOSVersionCategory,
)
from ios_gps_spoofer.device.version_utils import (
    classify_ios_version,
    is_developer_mode_required,
)

logger = logging.getLogger(__name__)

# Type alias for event callbacks
DeviceCallback = Callable[[DeviceConnection], None]

# Default address for the tunneld HTTP API
TUNNELD_DEFAULT_ADDRESS = ("127.0.0.1", 49151)


class DeviceManager:
    """Manages discovery and lifecycle of connected iOS devices.

    For iOS 14-16 devices, discovery is via USB/usbmux.
    For iOS 17+ devices, discovery is via the tunneld daemon API.

    Usage::

        manager = DeviceManager()
        manager.on_device_connected = my_connect_handler
        manager.start_polling()
        # ... later ...
        manager.stop_polling()

    The manager maintains an internal dictionary of active connections keyed
    by UDID.  It is safe to call any public method from any thread.
    """

    def __init__(
        self,
        poll_interval: float = 2.0,
        connection_timeout: float = 10.0,
        tunneld_address: tuple[str, int] = TUNNELD_DEFAULT_ADDRESS,
    ) -> None:
        """Initialize the device manager.

        Args:
            poll_interval: Seconds between device enumeration polls.
            connection_timeout: Seconds to wait for pairing before timeout.
            tunneld_address: Address of the tunneld HTTP API
                (default: ``('127.0.0.1', 49151)``).
        """
        if poll_interval <= 0:
            raise ValueError(f"poll_interval must be positive, got {poll_interval}")
        if connection_timeout <= 0:
            raise ValueError(
                f"connection_timeout must be positive, got {connection_timeout}"
            )

        self._poll_interval = poll_interval
        self._connection_timeout = connection_timeout
        self._tunneld_address = tunneld_address

        # Active connections keyed by UDID
        self._connections: dict[str, DeviceConnection] = {}
        # Lockdown clients keyed by UDID (kept alive for DDI-based devices)
        self._lockdown_clients: dict[str, LockdownClient] = {}
        # RemoteServiceDiscoveryService instances for iOS 17+ (keyed by UDID)
        # These are obtained from tunneld, NOT self-managed.
        self._rsd_services: dict[str, Any] = {}

        self._lock = threading.Lock()
        self._poll_thread: threading.Thread | None = None
        self._stop_event = threading.Event()

        # Callbacks
        self._on_device_connected: DeviceCallback | None = None
        self._on_device_disconnected: DeviceCallback | None = None
        self._on_state_changed: DeviceCallback | None = None

    # ------------------------------------------------------------------
    # Callback properties
    # ------------------------------------------------------------------

    @property
    def on_device_connected(self) -> DeviceCallback | None:
        """Callback invoked when a new device is detected and identified."""
        return self._on_device_connected

    @on_device_connected.setter
    def on_device_connected(self, callback: DeviceCallback | None) -> None:
        self._on_device_connected = callback

    @property
    def on_device_disconnected(self) -> DeviceCallback | None:
        """Callback invoked when a previously-connected device disappears."""
        return self._on_device_disconnected

    @on_device_disconnected.setter
    def on_device_disconnected(self, callback: DeviceCallback | None) -> None:
        self._on_device_disconnected = callback

    @property
    def on_state_changed(self) -> DeviceCallback | None:
        """Callback invoked when a device's connection state changes."""
        return self._on_state_changed

    @on_state_changed.setter
    def on_state_changed(self, callback: DeviceCallback | None) -> None:
        self._on_state_changed = callback

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start_polling(self) -> None:
        """Start the background device-polling thread.

        Does nothing if polling is already running.
        """
        with self._lock:
            if self._poll_thread is not None and self._poll_thread.is_alive():
                logger.warning("Polling is already running")
                return
            self._stop_event.clear()
            self._poll_thread = threading.Thread(
                target=self._poll_loop,
                name="DeviceManager-poll",
                daemon=True,
            )
            self._poll_thread.start()
            logger.info(
                "Device polling started (interval=%.1fs)", self._poll_interval
            )

    def stop_polling(self) -> None:
        """Stop the background polling thread and clean up all connections.

        Blocks until the poll thread has exited (up to one poll interval).
        """
        self._stop_event.set()
        thread = self._poll_thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=self._poll_interval + 1.0)
            if thread.is_alive():
                logger.warning("Poll thread did not exit cleanly within timeout")
        self._poll_thread = None
        self.disconnect_all()
        logger.info("Device polling stopped")

    @property
    def is_polling(self) -> bool:
        """True if the background poll thread is running."""
        return (
            self._poll_thread is not None
            and self._poll_thread.is_alive()
            and not self._stop_event.is_set()
        )

    def list_connected_devices(self) -> list[DeviceConnection]:
        """Return a snapshot of all currently-connected devices.

        Returns:
            List of ``DeviceConnection`` objects (defensive copies of state).
        """
        with self._lock:
            return list(self._connections.values())

    def get_device(self, udid: str) -> DeviceConnection:
        """Look up a connected device by UDID.

        Args:
            udid: The device's Unique Device Identifier.

        Returns:
            The ``DeviceConnection`` for that device.

        Raises:
            DeviceNotFoundError: If no device with that UDID is connected.
        """
        with self._lock:
            connection = self._connections.get(udid)
        if connection is None:
            raise DeviceNotFoundError(udid)
        return connection

    def get_lockdown_client(self, udid: str) -> LockdownClient:
        """Return the lockdown client for an already-connected device.

        Args:
            udid: The device's Unique Device Identifier.

        Returns:
            The active ``LockdownClient`` instance.

        Raises:
            DeviceNotFoundError: If no device with that UDID is connected.
            DeviceConnectionError: If the lockdown client is not available.
        """
        with self._lock:
            client = self._lockdown_clients.get(udid)
            has_connection = udid in self._connections
        if client is None:
            if not has_connection:
                raise DeviceNotFoundError(udid)
            raise DeviceConnectionError(udid, "Lockdown client is not available")
        return client

    def get_service_provider(self, udid: str) -> LockdownServiceProvider:
        """Return the appropriate service provider for location simulation.

        For iOS <= 16, this returns the ``LockdownClient``.
        For iOS 17+, this returns the ``RemoteServiceDiscoveryService``
        obtained via tunneld.

        Args:
            udid: The device's Unique Device Identifier.

        Returns:
            A ``LockdownServiceProvider`` suitable for passing to
            pymobiledevice3 services.

        Raises:
            DeviceNotFoundError: If no device with that UDID is connected.
            DeviceConnectionError: If the service provider is not available
                (device not ready, tunnel not established, etc.).
        """
        with self._lock:
            connection = self._connections.get(udid)
            rsd = self._rsd_services.get(udid)
            lockdown = self._lockdown_clients.get(udid)

        if connection is None:
            raise DeviceNotFoundError(udid)

        if not connection.is_ready:
            raise DeviceConnectionError(
                udid,
                f"Device is not ready (state={connection.state.value}). "
                "Cannot provide service provider.",
            )

        # iOS 17+ uses RemoteServiceDiscoveryService via tunneld
        if connection.ios_category == IOSVersionCategory.TUNNEL:
            if rsd is None:
                raise DeviceConnectionError(
                    udid,
                    "RemoteServiceDiscoveryService is not available. "
                    "Is tunneld running? (pymobiledevice3 remote tunneld)",
                )
            return rsd

        # iOS <= 16 uses the lockdown client directly
        if lockdown is None:
            raise DeviceConnectionError(
                udid, "Lockdown client is not available"
            )
        return lockdown

    def get_ios_category(self, udid: str) -> IOSVersionCategory:
        """Return the iOS version category for a connected device.

        Args:
            udid: The device's Unique Device Identifier.

        Returns:
            The ``IOSVersionCategory`` (LEGACY, DDI, or TUNNEL).

        Raises:
            DeviceNotFoundError: If no device with that UDID is connected.
        """
        with self._lock:
            connection = self._connections.get(udid)
        if connection is None:
            raise DeviceNotFoundError(udid)
        return connection.ios_category

    def connect_device(self, udid: str | None = None) -> DeviceConnection:
        """Manually trigger connection to a specific (or first available) device.

        For iOS 14-16: discovers via USB, creates lockdown, mounts DDI.
        For iOS 17+: queries tunneld for the device's RSD.

        Args:
            udid: Optional UDID. If None, connects to the first device found.

        Returns:
            The ``DeviceConnection`` for the newly-connected device.

        Raises:
            DeviceNotFoundError: If no matching device is found.
            DeviceConnectionError: On lockdown / communication failure.
            DevicePairingError: If the device is not trusted.
            UnsupportedIOSVersionError: If the iOS version is below 14.0.
        """
        # First try USB devices (iOS 14-16)
        mux_devices = self._enumerate_usb_devices()

        # If a UDID is specified, check USB first
        if udid is not None:
            for device in mux_devices:
                if device.serial == udid:
                    return self._connect_usb_device(device.serial)

            # Not found on USB -- try tunneld (iOS 17+)
            return self._connect_tunneld_device(udid)

        # No UDID specified -- try first USB device
        if mux_devices:
            return self._connect_usb_device(mux_devices[0].serial)

        # No USB devices -- try first tunneld device
        tunneld_rsds = self._query_tunneld_devices()
        if tunneld_rsds:
            first_rsd = tunneld_rsds[0]
            rsd_udid = self._get_rsd_udid(first_rsd)
            if rsd_udid:
                return self._connect_with_rsd(rsd_udid, first_rsd)

        raise DeviceNotFoundError(udid)

    def disconnect_device(self, udid: str) -> None:
        """Cleanly disconnect a single device.

        Args:
            udid: The UDID of the device to disconnect.
        """
        self._cleanup_device(udid)
        logger.info("Device %s disconnected", udid)

    def disconnect_all(self) -> None:
        """Disconnect all devices and release all resources."""
        with self._lock:
            udids = list(self._connections.keys())
        for udid in udids:
            self._cleanup_device(udid)
        logger.info("All devices disconnected")

    def is_tunneld_running(self) -> bool:
        """Check whether the tunneld daemon is reachable.

        Returns:
            True if tunneld responds at its HTTP endpoint.
        """
        try:
            import requests

            resp = requests.get(
                f"http://{self._tunneld_address[0]}:{self._tunneld_address[1]}",
                timeout=2.0,
            )
            return resp.status_code == 200
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Internal: polling loop
    # ------------------------------------------------------------------

    def _poll_loop(self) -> None:
        """Background loop that periodically enumerates devices."""
        logger.debug("Poll loop started")
        while not self._stop_event.is_set():
            try:
                self._poll_once()
            except Exception:
                logger.exception("Unexpected error in device poll loop")
            self._stop_event.wait(timeout=self._poll_interval)
        logger.debug("Poll loop exited")

    def _poll_once(self) -> None:
        """Single iteration of the poll loop.

        Checks both USB (iOS 14-16) and tunneld (iOS 17+) for devices.
        Detects newly-attached and newly-removed devices.
        """
        current_udids: set[str] = set()

        # Phase 1: USB devices (iOS 14-16)
        try:
            mux_devices = self._enumerate_usb_devices()
            for d in mux_devices:
                current_udids.add(d.serial)
        except Exception:
            logger.exception("Failed to enumerate USB devices")

        # Phase 2: Tunneld devices (iOS 17+)
        try:
            tunneld_rsds = self._query_tunneld_devices()
            for rsd in tunneld_rsds:
                rsd_udid = self._get_rsd_udid(rsd)
                if rsd_udid:
                    current_udids.add(rsd_udid)
        except Exception:
            logger.debug("Tunneld not available or query failed", exc_info=True)

        with self._lock:
            known_udids = set(self._connections.keys())

        # Detect new devices
        new_udids = current_udids - known_udids
        for udid in new_udids:
            with self._lock:
                if udid in self._connections:
                    continue
            logger.info("New device detected: %s", udid)
            try:
                self._auto_connect_device(udid)
            except (DeviceConnectionError, DevicePairingError) as exc:
                logger.error("Failed to connect new device %s: %s", udid, exc)
            except UnsupportedIOSVersionError as exc:
                logger.warning("Unsupported device %s: %s", udid, exc)
            except Exception:
                logger.exception("Unexpected error connecting device %s", udid)

        # Detect removed devices
        removed_udids = known_udids - current_udids
        for udid in removed_udids:
            logger.info("Device removed: %s", udid)
            with self._lock:
                connection = self._connections.get(udid)
            self._cleanup_device(udid)
            if connection and self._on_device_disconnected:
                try:
                    self._on_device_disconnected(connection)
                except Exception:
                    logger.exception("Error in on_device_disconnected callback")

        # Update last-seen for devices still present
        with self._lock:
            for udid in current_udids & known_udids:
                conn = self._connections.get(udid)
                if conn:
                    conn.update_last_seen()

    def _auto_connect_device(self, udid: str) -> DeviceConnection:
        """Auto-connect a device found during polling.

        Tries USB first, then tunneld.

        Args:
            udid: The device UDID.

        Returns:
            The ``DeviceConnection``.
        """
        # Check USB
        try:
            mux_devices = self._enumerate_usb_devices()
            for d in mux_devices:
                if d.serial == udid:
                    return self._connect_usb_device(udid)
        except Exception:
            pass

        # Try tunneld
        return self._connect_tunneld_device(udid)

    # ------------------------------------------------------------------
    # Internal: USB connection sequence (iOS 14-16)
    # ------------------------------------------------------------------

    def _connect_usb_device(self, udid: str) -> DeviceConnection:
        """Run the full USB connection sequence for a device.

        Steps:
        1. Create lockdown client
        2. Read device info
        3. Classify iOS version
        4. If TUNNEL category (17+), skip DDI and use tunneld instead
        5. If DDI category (14-16), mount DDI
        6. Mark as READY

        Args:
            udid: The device's UDID.

        Returns:
            The resulting ``DeviceConnection`` (also stored internally).
        """
        # Step 1: Create lockdown client
        lockdown = self._create_lockdown_client(udid)

        # Step 2: Read device info
        device_info = self._read_device_info(lockdown, udid)

        # Step 3: Classify iOS version
        try:
            ios_category = classify_ios_version(device_info.product_version)
        except ValueError as exc:
            self._close_lockdown_client(lockdown)
            raise UnsupportedIOSVersionError(
                udid, device_info.product_version
            ) from exc

        # If this is iOS 17+, we should use tunneld instead of USB lockdown
        if ios_category == IOSVersionCategory.TUNNEL:
            self._close_lockdown_client(lockdown)
            return self._connect_tunneld_device(udid, device_info=device_info)

        # Step 4: Create connection record for DDI-based device
        connection = DeviceConnection(
            device_info=device_info,
            state=ConnectionState.PAIRED,
            ios_category=ios_category,
        )

        with self._lock:
            self._connections[udid] = connection
            self._lockdown_clients[udid] = lockdown

        self._notify_state_change(connection)

        # Step 5: Mount DDI
        try:
            self._prepare_ddi_device(connection, lockdown)
        except (DDIMountError, DeveloperModeError) as exc:
            connection.set_error(str(exc))
            self._notify_state_change(connection)
            raise
        except Exception as exc:
            connection.set_error(f"Unexpected preparation error: {exc}")
            self._notify_state_change(connection)
            raise DeviceConnectionError(udid, str(exc)) from exc

        # Step 6: Mark as ready
        connection.state = ConnectionState.READY
        self._notify_state_change(connection)

        if self._on_device_connected:
            try:
                self._on_device_connected(connection)
            except Exception:
                logger.exception("Error in on_device_connected callback")

        logger.info(
            "Device %s (%s, iOS %s) is ready [%s]",
            udid,
            device_info.name,
            device_info.product_version,
            ios_category.value,
        )
        return connection

    # ------------------------------------------------------------------
    # Internal: tunneld connection (iOS 17+)
    # ------------------------------------------------------------------

    def _connect_tunneld_device(
        self,
        udid: str,
        device_info: DeviceInfo | None = None,
    ) -> DeviceConnection:
        """Connect an iOS 17+ device via the tunneld daemon.

        Queries tunneld for the device's RSD, reads device info from
        the RSD if not already known, and marks the device as READY.

        Args:
            udid: The device UDID.
            device_info: Optional pre-fetched device info (from USB lockdown).

        Returns:
            The ``DeviceConnection``.

        Raises:
            DeviceNotFoundError: If tunneld doesn't know about this device.
            TunnelError: If tunneld connection fails.
        """
        try:
            rsd = self._get_tunneld_device(udid)
        except Exception as exc:
            raise TunnelError(
                udid,
                f"Failed to get device from tunneld: {exc}. "
                "Is 'pymobiledevice3 remote tunneld' running as admin?",
            ) from exc

        if rsd is None:
            raise DeviceNotFoundError(udid)

        return self._connect_with_rsd(udid, rsd, device_info=device_info)

    def _connect_with_rsd(
        self,
        udid: str,
        rsd: Any,
        device_info: DeviceInfo | None = None,
    ) -> DeviceConnection:
        """Finalize connection using an RSD from tunneld.

        Args:
            udid: The device UDID.
            rsd: The ``RemoteServiceDiscoveryService`` instance.
            device_info: Optional pre-fetched device info.

        Returns:
            The ``DeviceConnection``.
        """
        # Read device info from RSD if not provided
        if device_info is None:
            device_info = self._read_device_info_from_rsd(rsd, udid)

        connection = DeviceConnection(
            device_info=device_info,
            state=ConnectionState.TUNNEL_ESTABLISHED,
            ios_category=IOSVersionCategory.TUNNEL,
        )

        with self._lock:
            self._connections[udid] = connection
            self._rsd_services[udid] = rsd

        self._notify_state_change(connection)

        # Mark as READY immediately (tunneld handles the tunnel lifecycle)
        connection.state = ConnectionState.READY
        self._notify_state_change(connection)

        if self._on_device_connected:
            try:
                self._on_device_connected(connection)
            except Exception:
                logger.exception("Error in on_device_connected callback")

        logger.info(
            "Device %s (%s, iOS %s) is ready via tunneld [tunnel]",
            udid,
            device_info.name,
            device_info.product_version,
        )
        return connection

    def _read_device_info_from_rsd(self, rsd: Any, udid: str) -> DeviceInfo:
        """Read device info from a RemoteServiceDiscoveryService.

        Args:
            rsd: The connected RSD instance.
            udid: The device UDID (for error messages).

        Returns:
            A ``DeviceInfo`` snapshot.
        """
        try:
            # RSD exposes device info through its peer_info or
            # through a lockdown-like get_value interface
            all_values = rsd.peer_info
            return DeviceInfo(
                udid=udid,
                name=all_values.get("DeviceName", all_values.get("name", "Unknown")),
                product_type=all_values.get("ProductType", all_values.get("productType", "Unknown")),
                product_version=all_values.get(
                    "ProductVersion",
                    all_values.get("OSVersion", "17.0"),
                ),
                build_version=all_values.get("BuildVersion", "Unknown"),
                chip_id=all_values.get("ChipID", 0),
                hardware_model=all_values.get("HardwareModel", "Unknown"),
                device_class=all_values.get("DeviceClass", "iPhone"),
            )
        except Exception as exc:
            logger.warning(
                "Could not read device info from RSD for %s: %s", udid, exc
            )
            # Return minimal info
            return DeviceInfo(
                udid=udid,
                name="Unknown",
                product_type="Unknown",
                product_version="17.0",
                build_version="Unknown",
                chip_id=0,
                hardware_model="Unknown",
            )

    # ------------------------------------------------------------------
    # Internal: tunneld API wrappers
    # ------------------------------------------------------------------

    def _query_tunneld_devices(self) -> list[Any]:
        """Query tunneld for all connected devices.

        Returns:
            List of ``RemoteServiceDiscoveryService`` instances,
            or empty list if tunneld is unreachable.
        """
        try:
            from pymobiledevice3.tunneld.api import get_tunneld_devices

            return get_tunneld_devices(self._tunneld_address)
        except Exception:
            # tunneld not running or unreachable -- this is not an error
            # during polling, only when explicitly connecting
            return []

    def _get_tunneld_device(self, udid: str) -> Any | None:
        """Get a specific device from tunneld by UDID.

        Args:
            udid: The device UDID.

        Returns:
            A ``RemoteServiceDiscoveryService`` if found, else None.
        """
        from pymobiledevice3.tunneld.api import get_tunneld_device_by_udid

        return get_tunneld_device_by_udid(udid, self._tunneld_address)

    @staticmethod
    def _get_rsd_udid(rsd: Any) -> str | None:
        """Extract the UDID from a RemoteServiceDiscoveryService.

        Args:
            rsd: The RSD instance.

        Returns:
            The device UDID, or None if it cannot be determined.
        """
        try:
            # RSD instances have a .udid property
            if hasattr(rsd, "udid") and rsd.udid:
                return str(rsd.udid)
            # Fallback: peer_info -> Properties -> UniqueDeviceID
            peer_info = rsd.peer_info
            props = peer_info.get("Properties", {})
            udid = props.get("UniqueDeviceID") or peer_info.get("UniqueDeviceID")
            if udid:
                return str(udid)
            return None
        except Exception:
            return None

    # ------------------------------------------------------------------
    # Internal: DDI device preparation (iOS 14-16)
    # ------------------------------------------------------------------

    def _prepare_ddi_device(
        self, connection: DeviceConnection, lockdown: LockdownClient
    ) -> None:
        """Prepare a DDI-based device (iOS 14-16).

        Steps:
        1. Check Developer Mode (iOS 16+ only)
        2. Check if DDI is already mounted
        3. Mount DDI if needed

        Args:
            connection: The device's connection record.
            lockdown: The active lockdown client.
        """
        udid = connection.udid

        # Check Developer Mode for iOS 16+
        if is_developer_mode_required(connection.device_info.product_version):
            try:
                dev_mode_status = lockdown.developer_mode_status
                if not dev_mode_status:
                    raise DeveloperModeError(udid)
            except (ConnectionFailedError, MuxException, OSError) as exc:
                logger.warning(
                    "Could not check Developer Mode status for %s: %s",
                    udid,
                    exc,
                )

        # Check if DDI is already mounted
        try:
            from pymobiledevice3.services.mobile_image_mounter import (
                MobileImageMounterService,
            )

            mounter = MobileImageMounterService(lockdown=lockdown)
            if mounter.is_image_mounted():
                logger.info("DDI already mounted on %s", udid)
                connection.state = ConnectionState.DDI_MOUNTED
                self._notify_state_change(connection)
                return
        except Exception as exc:
            logger.warning(
                "Could not check DDI mount status for %s: %s", udid, exc
            )

        # Mount DDI
        connection.state = ConnectionState.CONNECTING
        self._notify_state_change(connection)
        self._mount_ddi(connection, lockdown)
        connection.state = ConnectionState.DDI_MOUNTED
        self._notify_state_change(connection)

    def _mount_ddi(
        self, connection: DeviceConnection, lockdown: LockdownClient
    ) -> None:
        """Download and mount the Developer Disk Image.

        Args:
            connection: The device's connection record.
            lockdown: The active lockdown client.

        Raises:
            DDIMountError: If DDI download or mounting fails.
        """
        from ios_gps_spoofer.device.version_utils import version_for_ddi_lookup

        udid = connection.udid
        version_key = version_for_ddi_lookup(
            connection.device_info.product_version
        )

        logger.info(
            "Mounting DDI for %s (iOS %s, lookup key: %s)",
            udid,
            connection.device_info.product_version,
            version_key,
        )

        try:
            from developer_disk_image.repo import DeveloperDiskImageRepository
            from pymobiledevice3.services.mobile_image_mounter import (
                MobileImageMounterService,
            )

            repo = DeveloperDiskImageRepository.create()
            ddi = repo.get_developer_disk_image(version_key)

            if ddi is None:
                raise DDIMountError(
                    udid,
                    f"No Developer Disk Image found for iOS {version_key}",
                )

            mounter = MobileImageMounterService(lockdown=lockdown)
            mounter.upload_image(
                "Developer", ddi.image, ddi.signature
            )
            mounter.mount_image(
                "Developer", ddi.signature
            )
            logger.info("DDI mounted successfully on %s", udid)

        except DDIMountError:
            raise
        except Exception as exc:
            raise DDIMountError(udid, str(exc)) from exc

    # ------------------------------------------------------------------
    # Internal: lockdown client management
    # ------------------------------------------------------------------

    def _create_lockdown_client(self, udid: str) -> LockdownClient:
        """Create and return a lockdown client for the given UDID.

        Args:
            udid: The device's UDID.

        Returns:
            An authenticated ``LockdownClient``.

        Raises:
            DeviceConnectionError: On communication failure.
            DevicePairingError: If the device is not trusted.
        """
        try:
            lockdown = create_using_usbmux(
                serial=udid,
                autopair=True,
                pair_timeout=self._connection_timeout,
            )
            return lockdown
        except PairingError as exc:
            raise DevicePairingError(udid) from exc
        except (ConnectionFailedError, MuxException, OSError) as exc:
            raise DeviceConnectionError(udid, str(exc)) from exc

    def _read_device_info(
        self, lockdown: LockdownClient, udid: str
    ) -> DeviceInfo:
        """Read device identity and firmware info from lockdown.

        Args:
            lockdown: An active lockdown client.
            udid: The device's UDID (used in error messages).

        Returns:
            A ``DeviceInfo`` snapshot.

        Raises:
            DeviceConnectionError: If reading device values fails.
        """
        try:
            all_values = lockdown.get_value()
            return DeviceInfo(
                udid=udid,
                name=all_values.get("DeviceName", "Unknown"),
                product_type=all_values.get("ProductType", "Unknown"),
                product_version=all_values.get("ProductVersion", "0.0"),
                build_version=all_values.get("BuildVersion", "Unknown"),
                chip_id=all_values.get("ChipID", 0),
                hardware_model=all_values.get("HardwareModel", "Unknown"),
                device_class=all_values.get("DeviceClass", "iPhone"),
            )
        except (ConnectionFailedError, MuxException, OSError) as exc:
            raise DeviceConnectionError(
                udid, f"Failed to read device info: {exc}"
            ) from exc

    # ------------------------------------------------------------------
    # Internal: USB enumeration
    # ------------------------------------------------------------------

    @staticmethod
    def _enumerate_usb_devices() -> list[MuxDevice]:
        """Return the list of USB-connected iOS devices via usbmux.

        Returns:
            List of ``MuxDevice`` objects from pymobiledevice3.

        Raises:
            DeviceConnectionError: If usbmux communication fails entirely.
        """
        try:
            devices = usbmux_list_devices()
            # Filter to USB-only (exclude network/WiFi devices)
            usb_devices = [d for d in devices if d.is_usb]
            return usb_devices
        except (MuxException, ConnectionRefusedError, OSError) as exc:
            logger.error("Failed to enumerate USB devices: %s", exc)
            raise DeviceConnectionError(
                "usbmux",
                f"Cannot communicate with usbmux daemon: {exc}. "
                f"Ensure {'iTunes or Apple Mobile Device Support' if platform.system() == 'Windows' else 'usbmuxd'} is installed.",
            ) from exc

    # ------------------------------------------------------------------
    # Internal: cleanup
    # ------------------------------------------------------------------

    def _cleanup_device(self, udid: str) -> None:
        """Release all resources for a single device.

        Safe to call even if the device is partially connected or already
        cleaned up.

        Args:
            udid: The UDID of the device to clean up.
        """
        with self._lock:
            connection = self._connections.pop(udid, None)
            lockdown = self._lockdown_clients.pop(udid, None)
            rsd = self._rsd_services.pop(udid, None)

        self._close_lockdown_client(lockdown)
        self._close_rsd(rsd)

        if connection:
            connection.state = ConnectionState.DISCONNECTED
            logger.debug("Cleaned up resources for device %s", udid)

    @staticmethod
    def _close_lockdown_client(lockdown: LockdownClient | None) -> None:
        """Safely close a lockdown client, ignoring errors."""
        if lockdown is None:
            return
        try:
            lockdown.close()
        except Exception:
            logger.debug("Error closing lockdown client", exc_info=True)

    @staticmethod
    def _close_rsd(rsd: Any | None) -> None:
        """Safely close an RSD instance, ignoring errors.

        Note: RSD instances from tunneld are shared references; closing
        them here just releases our local reference.  The tunneld daemon
        manages the actual tunnel lifecycle.
        """
        if rsd is None:
            return
        try:
            rsd.close()
        except Exception:
            logger.debug("Error closing RSD", exc_info=True)

    # ------------------------------------------------------------------
    # Internal: notifications
    # ------------------------------------------------------------------

    def _notify_state_change(self, connection: DeviceConnection) -> None:
        """Fire the on_state_changed callback if registered.

        Args:
            connection: The device whose state just changed.
        """
        if self._on_state_changed:
            try:
                self._on_state_changed(connection)
            except Exception:
                logger.exception("Error in on_state_changed callback")

    # ------------------------------------------------------------------
    # Windows driver check
    # ------------------------------------------------------------------

    @staticmethod
    def check_windows_usb_driver() -> dict[str, bool | str]:
        """Check whether Apple USB drivers are available on Windows.

        Returns:
            A dict with keys:
            - ``is_windows``: True if running on Windows.
            - ``driver_available``: True if Apple Mobile Device Support is detected.
            - ``message``: Human-readable status message.
        """
        if platform.system() != "Windows":
            return {
                "is_windows": False,
                "driver_available": True,
                "message": "Not running on Windows; no driver check needed.",
            }

        try:
            import winreg

            # Check for Apple Mobile Device Service in the registry
            try:
                key = winreg.OpenKey(
                    winreg.HKEY_LOCAL_MACHINE,
                    r"SYSTEM\CurrentControlSet\Services\Apple Mobile Device Service",
                )
                winreg.CloseKey(key)
                return {
                    "is_windows": True,
                    "driver_available": True,
                    "message": "Apple Mobile Device Support is installed.",
                }
            except FileNotFoundError:
                pass

            # Fallback: check for usbmuxd in Apple's application support path
            import os

            apple_paths = [
                os.path.join(
                    os.environ.get("COMMONPROGRAMFILES", ""),
                    "Apple",
                    "Mobile Device Support",
                ),
                os.path.join(
                    os.environ.get("COMMONPROGRAMFILES(X86)", ""),
                    "Apple",
                    "Mobile Device Support",
                ),
            ]
            for path in apple_paths:
                if os.path.isdir(path):
                    return {
                        "is_windows": True,
                        "driver_available": True,
                        "message": f"Apple Mobile Device Support found at: {path}",
                    }

            return {
                "is_windows": True,
                "driver_available": False,
                "message": (
                    "Apple Mobile Device Support not found. "
                    "Please install iTunes or Apple Devices from the Microsoft Store."
                ),
            }
        except Exception as exc:
            return {
                "is_windows": True,
                "driver_available": False,
                "message": f"Could not check for Apple USB drivers: {exc}",
            }
