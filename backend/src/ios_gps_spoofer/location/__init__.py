"""Location setting and GPS simulation module.

Public API::

    from ios_gps_spoofer.location import LocationService, Coordinate

    location_service = LocationService(device_manager)
    coord = Coordinate(latitude=25.0330, longitude=121.5654)
    location_service.set_location(udid, coord)
"""

from ios_gps_spoofer.location.coordinates import (
    Coordinate,
    haversine_distance,
    interpolate_great_circle,
)
from ios_gps_spoofer.location.exceptions import (
    InvalidCoordinateError,
    LocationClearError,
    LocationError,
    LocationServiceNotReadyError,
    LocationSetError,
)
from ios_gps_spoofer.location.location_service import LocationService

__all__ = [
    "Coordinate",
    "InvalidCoordinateError",
    "LocationClearError",
    "LocationError",
    "LocationService",
    "LocationServiceNotReadyError",
    "LocationSetError",
    "haversine_distance",
    "interpolate_great_circle",
]
