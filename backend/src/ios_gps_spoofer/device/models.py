"""Data models for device information and connection state.

These models are the canonical representation of device state throughout the
application.  They are intentionally kept as plain dataclasses (no ORM, no
pydantic) so the device layer has zero dependency on the API layer.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from datetime import datetime, timezone


class ConnectionState(enum.Enum):
    """Lifecycle states for a USB-connected iOS device."""

    DISCONNECTED = "disconnected"
    DETECTED = "detected"
    CONNECTING = "connecting"
    PAIRED = "paired"
    DDI_MOUNTED = "ddi_mounted"
    TUNNEL_ESTABLISHED = "tunnel_established"
    READY = "ready"
    ERROR = "error"


class IOSVersionCategory(enum.Enum):
    """Coarse classification of iOS versions for code-path selection.

    - LEGACY: iOS 14-15 (DDI mount, DtSimulateLocation via lockdown)
    - DDI: iOS 16.x (DDI mount, may need personalized image, developer mode)
    - TUNNEL: iOS 17+ (RemoteXPC tunnel, no DDI needed)
    """

    LEGACY = "legacy"
    DDI = "ddi"
    TUNNEL = "tunnel"


@dataclass(frozen=True)
class DeviceInfo:
    """Immutable snapshot of an iOS device's identity and firmware.

    Attributes:
        udid: Unique Device Identifier (40 hex chars for pre-USB-C, longer for USB-C).
        name: User-visible device name (e.g. "John's iPhone").
        product_type: Apple internal model identifier (e.g. "iPhone16,1").
        product_version: Full iOS version string (e.g. "17.2.1").
        build_version: Apple build string (e.g. "21C66").
        chip_id: SoC chip identifier.
        hardware_model: Internal hardware board identifier (e.g. "D83AP").
        device_class: Device class ("iPhone", "iPad", "iPod").
    """

    udid: str
    name: str
    product_type: str
    product_version: str
    build_version: str
    chip_id: int
    hardware_model: str
    device_class: str = "iPhone"


@dataclass
class DeviceConnection:
    """Mutable connection state for an active iOS device session.

    This tracks everything the rest of the application needs to know about
    a connected device: its identity, current lifecycle state, and whether
    the device is ready for location simulation.

    Attributes:
        device_info: Immutable identity/firmware snapshot.
        state: Current lifecycle state.
        ios_category: Coarse iOS version classification.
        error_message: Human-readable error description (set when state == ERROR).
        connected_at: UTC timestamp of initial detection.
        last_seen_at: UTC timestamp of last successful communication.
    """

    device_info: DeviceInfo
    state: ConnectionState = ConnectionState.DETECTED
    ios_category: IOSVersionCategory = IOSVersionCategory.TUNNEL
    error_message: str | None = None
    connected_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_seen_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def udid(self) -> str:
        """Shortcut to the device's UDID."""
        return self.device_info.udid

    @property
    def is_ready(self) -> bool:
        """True when the device is fully prepared for location simulation."""
        return self.state == ConnectionState.READY

    @property
    def is_error(self) -> bool:
        """True when the device is in an error state."""
        return self.state == ConnectionState.ERROR

    def to_dict(self) -> dict[str, str | bool | None]:
        """Serialize to a JSON-friendly dictionary for the API layer.

        Returns:
            Dictionary representation suitable for JSON serialization.
        """
        return {
            "udid": self.device_info.udid,
            "name": self.device_info.name,
            "product_type": self.device_info.product_type,
            "product_version": self.device_info.product_version,
            "build_version": self.device_info.build_version,
            "device_class": self.device_info.device_class,
            "state": self.state.value,
            "ios_category": self.ios_category.value,
            "is_ready": self.is_ready,
            "error_message": self.error_message,
            "connected_at": self.connected_at.isoformat(),
            "last_seen_at": self.last_seen_at.isoformat(),
        }

    def update_last_seen(self) -> None:
        """Refresh the last-seen timestamp to now (UTC)."""
        self.last_seen_at = datetime.now(timezone.utc)

    def set_error(self, message: str) -> None:
        """Transition to ERROR state with a human-readable message.

        Args:
            message: Description of what went wrong.
        """
        self.state = ConnectionState.ERROR
        self.error_message = message
