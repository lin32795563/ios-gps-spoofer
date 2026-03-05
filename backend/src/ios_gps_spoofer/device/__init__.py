"""Device connection and management module for iOS devices.

Public API::

    from ios_gps_spoofer.device import DeviceManager, DeviceConnection, DeviceInfo

    manager = DeviceManager()
    manager.start_polling()
    devices = manager.list_connected_devices()
    provider = manager.get_service_provider(udid)
"""

from ios_gps_spoofer.device.device_manager import DeviceCallback, DeviceManager
from ios_gps_spoofer.device.exceptions import (
    DDIMountError,
    DeveloperModeError,
    DeviceConnectionError,
    DeviceError,
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
    is_ios_17_or_later,
    parse_ios_version,
    version_for_ddi_lookup,
)

__all__ = [
    "ConnectionState",
    "DDIMountError",
    "DeveloperModeError",
    "DeviceCallback",
    "DeviceConnection",
    "DeviceConnectionError",
    "DeviceError",
    "DeviceInfo",
    "DeviceManager",
    "DeviceNotFoundError",
    "DevicePairingError",
    "IOSVersionCategory",
    "TunnelError",
    "UnsupportedIOSVersionError",
    "classify_ios_version",
    "is_developer_mode_required",
    "is_ios_17_or_later",
    "parse_ios_version",
    "version_for_ddi_lookup",
]
