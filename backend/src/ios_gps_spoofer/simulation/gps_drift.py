"""GPS drift simulation using Gaussian noise.

Adds small random offsets to coordinates to simulate the natural jitter
of a real GPS receiver.  The noise magnitude is configurable via
``sigma_meters`` (default 2.0m, range 0-10m).

Boundary Safety
---------------
When a coordinate is near the WGS-84 boundaries (lat +/-90 or lon +/-180),
the drift is clamped to stay within valid bounds.  Near the poles, longitude
drift is suppressed because longitude converges and becomes meaningless.
"""

from __future__ import annotations

import logging
import math
import random

from ios_gps_spoofer.location.coordinates import Coordinate

logger = logging.getLogger(__name__)

# Earth radius in meters for converting meter offsets to degree offsets
_EARTH_RADIUS_M = 6_371_000.0

# Maximum allowed sigma in meters
MAX_SIGMA_METERS = 10.0

# Latitude threshold (degrees) near the poles where longitude drift
# is suppressed to avoid extreme scaling artifacts
_POLE_LATITUDE_THRESHOLD = 89.5


def apply_drift(
    coordinate: Coordinate,
    sigma_meters: float = 2.0,
    rng: random.Random | None = None,
) -> Coordinate:
    """Apply Gaussian GPS drift to a coordinate.

    Adds random offsets in both latitude and longitude, drawn from a
    Gaussian distribution with the specified standard deviation.

    The drift is applied in a locally-flat approximation (valid for
    offsets under ~100m).  Near the poles, longitude drift is suppressed
    because the convergence of meridians makes small longitude changes
    represent very large physical distances.

    Args:
        coordinate: The base coordinate to add drift to.
        sigma_meters: Standard deviation of the drift in meters.
            Must be in range [0, MAX_SIGMA_METERS].
            A value of 0 disables drift.
        rng: Optional ``random.Random`` instance for reproducible results.
            If None, the module-level random is used.

    Returns:
        A new ``Coordinate`` with drift applied.  If drift would push
        the coordinate out of WGS-84 bounds, it is clamped.
    """
    if sigma_meters == 0.0:
        return coordinate

    _validate_sigma(sigma_meters)

    gen = rng if rng is not None else random

    # Generate random offsets in meters
    offset_north_m = gen.gauss(0.0, sigma_meters)
    offset_east_m = gen.gauss(0.0, sigma_meters)

    # Convert meter offsets to degree offsets
    delta_lat = _meters_to_lat_degrees(offset_north_m)
    delta_lon = _meters_to_lon_degrees(offset_east_m, coordinate.latitude)

    # Apply offsets
    new_lat = coordinate.latitude + delta_lat
    new_lon = coordinate.longitude + delta_lon

    # Clamp to WGS-84 bounds
    new_lat = max(-90.0, min(90.0, new_lat))
    new_lon = max(-180.0, min(180.0, new_lon))

    return Coordinate(latitude=new_lat, longitude=new_lon)


def _meters_to_lat_degrees(meters: float) -> float:
    """Convert a north/south offset in meters to latitude degrees.

    This is a simple linear approximation valid for small offsets.

    Args:
        meters: Offset in meters (positive = north, negative = south).

    Returns:
        Offset in latitude degrees.
    """
    return math.degrees(meters / _EARTH_RADIUS_M)


def _meters_to_lon_degrees(meters: float, latitude: float) -> float:
    """Convert an east/west offset in meters to longitude degrees.

    Takes into account the convergence of meridians at higher latitudes.
    Near the poles, returns 0 to avoid extreme values.

    Args:
        meters: Offset in meters (positive = east, negative = west).
        latitude: The current latitude in degrees.

    Returns:
        Offset in longitude degrees.
    """
    # Near the poles, suppress longitude drift entirely
    if abs(latitude) >= _POLE_LATITUDE_THRESHOLD:
        return 0.0

    cos_lat = math.cos(math.radians(latitude))

    # Guard against division by extremely small cos values
    # (should not happen given the pole threshold, but defensive)
    if cos_lat < 1e-10:
        return 0.0

    return math.degrees(meters / (_EARTH_RADIUS_M * cos_lat))


def _validate_sigma(sigma_meters: float) -> None:
    """Validate the sigma_meters parameter.

    Args:
        sigma_meters: The sigma value to validate.

    Raises:
        ValueError: If sigma is negative, NaN, infinite, or too large.
    """
    if not isinstance(sigma_meters, (int, float)) or isinstance(sigma_meters, bool):
        raise ValueError(
            f"sigma_meters must be a number, got {type(sigma_meters).__name__}"
        )
    if math.isnan(sigma_meters) or math.isinf(sigma_meters):
        raise ValueError(f"sigma_meters must be finite, got {sigma_meters}")
    if sigma_meters < 0.0:
        raise ValueError(
            f"sigma_meters must be non-negative, got {sigma_meters}"
        )
    if sigma_meters > MAX_SIGMA_METERS:
        raise ValueError(
            f"sigma_meters must be at most {MAX_SIGMA_METERS}m, "
            f"got {sigma_meters}"
        )
