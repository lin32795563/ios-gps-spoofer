"""Coordinate validation and representation for GPS location simulation.

All coordinates in the application pass through this module to ensure they
are valid WGS-84 lat/lon pairs before being sent to the device.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

# WGS-84 boundaries
_MIN_LATITUDE = -90.0
_MAX_LATITUDE = 90.0
_MIN_LONGITUDE = -180.0
_MAX_LONGITUDE = 180.0


@dataclass(frozen=True, slots=True)
class Coordinate:
    """An immutable, validated WGS-84 coordinate pair.

    Attributes:
        latitude: Decimal degrees, range [-90, 90].
        longitude: Decimal degrees, range [-180, 180].
    """

    latitude: float
    longitude: float

    def __post_init__(self) -> None:
        """Validate that lat/lon are finite and within WGS-84 bounds."""
        if isinstance(self.latitude, bool) or not isinstance(
            self.latitude, (int, float)
        ):
            raise TypeError(
                f"latitude must be a number, got {type(self.latitude).__name__}"
            )
        if isinstance(self.longitude, bool) or not isinstance(
            self.longitude, (int, float)
        ):
            raise TypeError(
                f"longitude must be a number, got {type(self.longitude).__name__}"
            )
        if math.isnan(self.latitude) or math.isinf(self.latitude):
            raise ValueError(
                f"latitude must be finite, got {self.latitude}"
            )
        if math.isnan(self.longitude) or math.isinf(self.longitude):
            raise ValueError(
                f"longitude must be finite, got {self.longitude}"
            )
        if not (_MIN_LATITUDE <= self.latitude <= _MAX_LATITUDE):
            raise ValueError(
                f"latitude must be between {_MIN_LATITUDE} and "
                f"{_MAX_LATITUDE}, got {self.latitude}"
            )
        if not (_MIN_LONGITUDE <= self.longitude <= _MAX_LONGITUDE):
            raise ValueError(
                f"longitude must be between {_MIN_LONGITUDE} and "
                f"{_MAX_LONGITUDE}, got {self.longitude}"
            )

    def to_tuple(self) -> tuple[float, float]:
        """Return (latitude, longitude) as a plain tuple.

        Returns:
            A 2-tuple of (latitude, longitude).
        """
        return (self.latitude, self.longitude)

    def to_dict(self) -> dict[str, float]:
        """Serialize to a JSON-friendly dictionary.

        Returns:
            Dictionary with 'latitude' and 'longitude' keys.
        """
        return {"latitude": self.latitude, "longitude": self.longitude}

    def distance_to(self, other: Coordinate) -> float:
        """Calculate the great-circle distance to another coordinate.

        Uses the Haversine formula. This is used by the path simulation
        engine to calculate segment distances.

        Args:
            other: The target coordinate.

        Returns:
            Distance in meters.
        """
        return haversine_distance(
            self.latitude, self.longitude,
            other.latitude, other.longitude,
        )

    def __str__(self) -> str:
        return f"({self.latitude:.6f}, {self.longitude:.6f})"


def haversine_distance(
    lat1: float, lon1: float,
    lat2: float, lon2: float,
) -> float:
    """Calculate great-circle distance between two points using Haversine.

    Args:
        lat1: Latitude of point 1 in decimal degrees.
        lon1: Longitude of point 1 in decimal degrees.
        lat2: Latitude of point 2 in decimal degrees.
        lon2: Longitude of point 2 in decimal degrees.

    Returns:
        Distance in meters.
    """
    earth_radius_m = 6_371_000.0  # Mean Earth radius in meters

    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    delta_lat = math.radians(lat2 - lat1)
    delta_lon = math.radians(lon2 - lon1)

    a = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat1_rad) * math.cos(lat2_rad)
        * math.sin(delta_lon / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return earth_radius_m * c


def interpolate_great_circle(
    start: Coordinate,
    end: Coordinate,
    fraction: float,
) -> Coordinate:
    """Interpolate a point along the great-circle arc between two coordinates.

    Uses spherical linear interpolation (slerp) for geographic accuracy.

    Args:
        start: The starting coordinate.
        end: The ending coordinate.
        fraction: Position along the arc, 0.0 = start, 1.0 = end.
            Values outside [0, 1] are clamped.

    Returns:
        The interpolated ``Coordinate``.
    """
    fraction = max(0.0, min(1.0, fraction))

    if fraction == 0.0:
        return start
    if fraction == 1.0:
        return end

    lat1 = math.radians(start.latitude)
    lon1 = math.radians(start.longitude)
    lat2 = math.radians(end.latitude)
    lon2 = math.radians(end.longitude)

    # Angular distance between points
    delta_sigma = 2 * math.asin(
        math.sqrt(
            math.sin((lat2 - lat1) / 2) ** 2
            + math.cos(lat1) * math.cos(lat2)
            * math.sin((lon2 - lon1) / 2) ** 2
        )
    )

    # For very short distances, use linear interpolation to avoid
    # division by zero in slerp
    if delta_sigma < 1e-10:
        lat = start.latitude + fraction * (end.latitude - start.latitude)
        lon = start.longitude + fraction * (end.longitude - start.longitude)
        return Coordinate(latitude=lat, longitude=lon)

    # Spherical linear interpolation
    a_coeff = math.sin((1 - fraction) * delta_sigma) / math.sin(delta_sigma)
    b_coeff = math.sin(fraction * delta_sigma) / math.sin(delta_sigma)

    x = (
        a_coeff * math.cos(lat1) * math.cos(lon1)
        + b_coeff * math.cos(lat2) * math.cos(lon2)
    )
    y = (
        a_coeff * math.cos(lat1) * math.sin(lon1)
        + b_coeff * math.cos(lat2) * math.sin(lon2)
    )
    z = a_coeff * math.sin(lat1) + b_coeff * math.sin(lat2)

    lat_result = math.degrees(math.atan2(z, math.sqrt(x ** 2 + y ** 2)))
    lon_result = math.degrees(math.atan2(y, x))

    return Coordinate(latitude=lat_result, longitude=lon_result)
