"""iOS version parsing and comparison utilities.

Uses ``packaging.version.Version`` for robust semantic version comparisons
instead of fragile string manipulation.
"""

from __future__ import annotations

import logging

from packaging.version import InvalidVersion, Version

from ios_gps_spoofer.device.models import IOSVersionCategory

logger = logging.getLogger(__name__)

# Version boundaries (inclusive lower bounds)
_IOS_14_0 = Version("14.0")
_IOS_16_0 = Version("16.0")
_IOS_17_0 = Version("17.0")


def parse_ios_version(version_string: str) -> Version:
    """Parse an iOS version string into a comparable ``Version`` object.

    Args:
        version_string: iOS version such as "17.2.1" or "16.7".

    Returns:
        A ``packaging.version.Version`` instance.

    Raises:
        ValueError: If the string cannot be parsed as a valid version.
    """
    if not version_string or not version_string.strip():
        raise ValueError("iOS version string is empty or blank")

    cleaned = version_string.strip()
    try:
        return Version(cleaned)
    except InvalidVersion as exc:
        raise ValueError(
            f"Cannot parse iOS version '{cleaned}': {exc}"
        ) from exc


def classify_ios_version(version_string: str) -> IOSVersionCategory:
    """Determine which code-path category an iOS version falls into.

    Args:
        version_string: iOS version such as "17.2.1" or "16.7".

    Returns:
        The ``IOSVersionCategory`` that governs how we connect to this device.

    Raises:
        ValueError: If the version string is invalid or below iOS 14.
    """
    version = parse_ios_version(version_string)

    if version < _IOS_14_0:
        raise ValueError(
            f"iOS {version_string} is below the minimum supported version (14.0)"
        )

    if version >= _IOS_17_0:
        return IOSVersionCategory.TUNNEL
    if version >= _IOS_16_0:
        return IOSVersionCategory.DDI
    return IOSVersionCategory.LEGACY


def is_ios_17_or_later(version_string: str) -> bool:
    """Check whether the given iOS version uses the tunnel protocol (17+).

    Args:
        version_string: iOS version such as "17.2.1".

    Returns:
        True if the version is 17.0 or later.
    """
    return parse_ios_version(version_string) >= _IOS_17_0


def is_developer_mode_required(version_string: str) -> bool:
    """Check whether Developer Mode must be enabled for this iOS version.

    Developer Mode was introduced in iOS 16.0.

    Args:
        version_string: iOS version such as "16.1".

    Returns:
        True if Developer Mode is required (iOS 16.0+).
    """
    return parse_ios_version(version_string) >= _IOS_16_0


def version_for_ddi_lookup(version_string: str) -> str:
    """Derive the DDI lookup key from a full iOS version string.

    Developer Disk Images are published per major.minor version,
    so "16.7.4" maps to "16.7".

    Args:
        version_string: Full iOS version such as "16.7.4".

    Returns:
        Major.minor string suitable for DDI repository lookup.
    """
    version = parse_ios_version(version_string)
    return f"{version.major}.{version.minor}"
