"""Tests for ios_gps_spoofer.location.coordinates module.

Covers:
- Coordinate construction and validation (valid, boundary, invalid inputs)
- Type checking (reject strings, None, booleans)
- Serialization (to_tuple, to_dict, __str__)
- Haversine distance calculation (known distances, same point, antipodal)
- Great-circle interpolation (endpoints, midpoint, very short, clamping)
"""


import pytest

from ios_gps_spoofer.location.coordinates import (
    Coordinate,
    haversine_distance,
    interpolate_great_circle,
)

# =====================================================================
# Coordinate construction and validation
# =====================================================================

class TestCoordinateConstruction:
    """Tests for valid Coordinate construction."""

    def test_basic_construction(self) -> None:
        coord = Coordinate(latitude=25.0330, longitude=121.5654)
        assert coord.latitude == 25.0330
        assert coord.longitude == 121.5654

    def test_zero_zero(self) -> None:
        coord = Coordinate(latitude=0.0, longitude=0.0)
        assert coord.latitude == 0.0
        assert coord.longitude == 0.0

    def test_integer_values(self) -> None:
        coord = Coordinate(latitude=25, longitude=121)
        assert coord.latitude == 25
        assert coord.longitude == 121

    def test_negative_values(self) -> None:
        coord = Coordinate(latitude=-33.8688, longitude=-151.2093)
        assert coord.latitude == -33.8688

    def test_boundary_max_latitude(self) -> None:
        coord = Coordinate(latitude=90.0, longitude=0.0)
        assert coord.latitude == 90.0

    def test_boundary_min_latitude(self) -> None:
        coord = Coordinate(latitude=-90.0, longitude=0.0)
        assert coord.latitude == -90.0

    def test_boundary_max_longitude(self) -> None:
        coord = Coordinate(latitude=0.0, longitude=180.0)
        assert coord.longitude == 180.0

    def test_boundary_min_longitude(self) -> None:
        coord = Coordinate(latitude=0.0, longitude=-180.0)
        assert coord.longitude == -180.0

    def test_all_corners(self) -> None:
        """All four extreme corner coordinates."""
        corners = [
            (90.0, 180.0), (90.0, -180.0),
            (-90.0, 180.0), (-90.0, -180.0),
        ]
        for lat, lon in corners:
            coord = Coordinate(latitude=lat, longitude=lon)
            assert coord.latitude == lat
            assert coord.longitude == lon

    def test_frozen_cannot_modify(self) -> None:
        coord = Coordinate(latitude=0.0, longitude=0.0)
        with pytest.raises(AttributeError):
            coord.latitude = 1.0  # type: ignore[misc]


class TestCoordinateValidation:
    """Tests for invalid Coordinate inputs."""

    def test_latitude_above_90_raises(self) -> None:
        with pytest.raises(ValueError, match="latitude must be between"):
            Coordinate(latitude=90.1, longitude=0.0)

    def test_latitude_below_minus_90_raises(self) -> None:
        with pytest.raises(ValueError, match="latitude must be between"):
            Coordinate(latitude=-90.1, longitude=0.0)

    def test_longitude_above_180_raises(self) -> None:
        with pytest.raises(ValueError, match="longitude must be between"):
            Coordinate(latitude=0.0, longitude=180.1)

    def test_longitude_below_minus_180_raises(self) -> None:
        with pytest.raises(ValueError, match="longitude must be between"):
            Coordinate(latitude=0.0, longitude=-180.1)

    def test_nan_latitude_raises(self) -> None:
        with pytest.raises(ValueError, match="latitude must be finite"):
            Coordinate(latitude=float("nan"), longitude=0.0)

    def test_nan_longitude_raises(self) -> None:
        with pytest.raises(ValueError, match="longitude must be finite"):
            Coordinate(latitude=0.0, longitude=float("nan"))

    def test_inf_latitude_raises(self) -> None:
        with pytest.raises(ValueError, match="latitude must be finite"):
            Coordinate(latitude=float("inf"), longitude=0.0)

    def test_neg_inf_longitude_raises(self) -> None:
        with pytest.raises(ValueError, match="longitude must be finite"):
            Coordinate(latitude=0.0, longitude=float("-inf"))

    def test_string_latitude_raises_type_error(self) -> None:
        with pytest.raises(TypeError, match="latitude must be a number"):
            Coordinate(latitude="25.0", longitude=0.0)  # type: ignore[arg-type]

    def test_none_latitude_raises_type_error(self) -> None:
        with pytest.raises(TypeError, match="latitude must be a number"):
            Coordinate(latitude=None, longitude=0.0)  # type: ignore[arg-type]

    def test_none_longitude_raises_type_error(self) -> None:
        with pytest.raises(TypeError, match="longitude must be a number"):
            Coordinate(latitude=0.0, longitude=None)  # type: ignore[arg-type]

    def test_bool_latitude_raises_type_error(self) -> None:
        with pytest.raises(TypeError, match="latitude must be a number"):
            Coordinate(latitude=True, longitude=0.0)  # type: ignore[arg-type]

    def test_bool_longitude_raises_type_error(self) -> None:
        with pytest.raises(TypeError, match="longitude must be a number"):
            Coordinate(latitude=0.0, longitude=False)  # type: ignore[arg-type]

    def test_extremely_large_latitude_raises(self) -> None:
        with pytest.raises(ValueError):
            Coordinate(latitude=1000.0, longitude=0.0)

    def test_extremely_large_longitude_raises(self) -> None:
        with pytest.raises(ValueError):
            Coordinate(latitude=0.0, longitude=1000.0)


# =====================================================================
# Serialization
# =====================================================================

class TestCoordinateSerialization:
    """Tests for to_tuple, to_dict, __str__."""

    def test_to_tuple(self) -> None:
        coord = Coordinate(latitude=25.0330, longitude=121.5654)
        assert coord.to_tuple() == (25.0330, 121.5654)

    def test_to_dict(self) -> None:
        coord = Coordinate(latitude=25.0330, longitude=121.5654)
        d = coord.to_dict()
        assert d == {"latitude": 25.0330, "longitude": 121.5654}

    def test_to_dict_keys(self) -> None:
        coord = Coordinate(latitude=0.0, longitude=0.0)
        d = coord.to_dict()
        assert set(d.keys()) == {"latitude", "longitude"}

    def test_str_format(self) -> None:
        coord = Coordinate(latitude=25.033000, longitude=121.565400)
        s = str(coord)
        assert "25.033000" in s
        assert "121.565400" in s

    def test_str_negative(self) -> None:
        coord = Coordinate(latitude=-33.868800, longitude=-151.209300)
        s = str(coord)
        assert "-33.868800" in s


# =====================================================================
# Distance calculation
# =====================================================================

class TestCoordinateDistance:
    """Tests for distance_to and haversine_distance."""

    def test_distance_to_self_is_zero(self) -> None:
        coord = Coordinate(latitude=25.0, longitude=121.0)
        assert coord.distance_to(coord) == pytest.approx(0.0, abs=0.01)

    def test_same_point_distance_is_zero(self) -> None:
        assert haversine_distance(0.0, 0.0, 0.0, 0.0) == pytest.approx(0.0)

    def test_known_distance_new_york_to_london(self) -> None:
        """NYC to London is approximately 5,570 km."""
        nyc = Coordinate(latitude=40.7128, longitude=-74.0060)
        london = Coordinate(latitude=51.5074, longitude=-0.1278)
        distance_km = nyc.distance_to(london) / 1000.0
        assert distance_km == pytest.approx(5570, rel=0.02)  # 2% tolerance

    def test_known_distance_equator_one_degree(self) -> None:
        """One degree of longitude at the equator is ~111.32 km."""
        d = haversine_distance(0.0, 0.0, 0.0, 1.0) / 1000.0
        assert d == pytest.approx(111.32, rel=0.01)

    def test_antipodal_points(self) -> None:
        """Distance between antipodal points ~20,015 km (half circumference)."""
        d = haversine_distance(0.0, 0.0, 0.0, 180.0) / 1000.0
        assert d == pytest.approx(20015, rel=0.01)

    def test_north_pole_to_south_pole(self) -> None:
        """North pole to south pole ~20,015 km."""
        d = haversine_distance(90.0, 0.0, -90.0, 0.0) / 1000.0
        assert d == pytest.approx(20015, rel=0.01)

    def test_short_distance_meters(self) -> None:
        """Two points very close together (tens of meters)."""
        d = haversine_distance(25.0330, 121.5654, 25.0331, 121.5654)
        assert 5 < d < 20  # should be about 11 meters

    def test_distance_is_symmetric(self) -> None:
        d1 = haversine_distance(25.0, 121.0, 35.0, 139.0)
        d2 = haversine_distance(35.0, 139.0, 25.0, 121.0)
        assert d1 == pytest.approx(d2, rel=1e-10)


# =====================================================================
# Great-circle interpolation
# =====================================================================

class TestInterpolateGreatCircle:
    """Tests for interpolate_great_circle function."""

    def test_fraction_zero_returns_start(self) -> None:
        start = Coordinate(latitude=0.0, longitude=0.0)
        end = Coordinate(latitude=10.0, longitude=10.0)
        result = interpolate_great_circle(start, end, 0.0)
        assert result.latitude == start.latitude
        assert result.longitude == start.longitude

    def test_fraction_one_returns_end(self) -> None:
        start = Coordinate(latitude=0.0, longitude=0.0)
        end = Coordinate(latitude=10.0, longitude=10.0)
        result = interpolate_great_circle(start, end, 1.0)
        assert result.latitude == end.latitude
        assert result.longitude == end.longitude

    def test_midpoint_on_equator(self) -> None:
        """Midpoint between (0,0) and (0,10) should be near (0,5)."""
        start = Coordinate(latitude=0.0, longitude=0.0)
        end = Coordinate(latitude=0.0, longitude=10.0)
        mid = interpolate_great_circle(start, end, 0.5)
        assert mid.latitude == pytest.approx(0.0, abs=0.01)
        assert mid.longitude == pytest.approx(5.0, abs=0.1)

    def test_quarter_point(self) -> None:
        """Quarter point along equator."""
        start = Coordinate(latitude=0.0, longitude=0.0)
        end = Coordinate(latitude=0.0, longitude=20.0)
        quarter = interpolate_great_circle(start, end, 0.25)
        assert quarter.longitude == pytest.approx(5.0, abs=0.1)

    def test_negative_fraction_clamped_to_zero(self) -> None:
        start = Coordinate(latitude=0.0, longitude=0.0)
        end = Coordinate(latitude=10.0, longitude=10.0)
        result = interpolate_great_circle(start, end, -1.0)
        assert result.latitude == start.latitude
        assert result.longitude == start.longitude

    def test_fraction_above_one_clamped(self) -> None:
        start = Coordinate(latitude=0.0, longitude=0.0)
        end = Coordinate(latitude=10.0, longitude=10.0)
        result = interpolate_great_circle(start, end, 2.0)
        assert result.latitude == end.latitude
        assert result.longitude == end.longitude

    def test_same_point_returns_same(self) -> None:
        """Interpolating between identical points returns that point."""
        point = Coordinate(latitude=25.033, longitude=121.565)
        result = interpolate_great_circle(point, point, 0.5)
        assert result.latitude == pytest.approx(point.latitude, abs=1e-6)
        assert result.longitude == pytest.approx(point.longitude, abs=1e-6)

    def test_very_short_distance(self) -> None:
        """Points micrometers apart should use linear interpolation."""
        start = Coordinate(latitude=25.0, longitude=121.0)
        end = Coordinate(latitude=25.0000001, longitude=121.0000001)
        mid = interpolate_great_circle(start, end, 0.5)
        assert mid.latitude == pytest.approx(25.00000005, abs=1e-8)

    def test_interpolation_stays_on_globe(self) -> None:
        """Result must be a valid coordinate."""
        start = Coordinate(latitude=40.7128, longitude=-74.0060)
        end = Coordinate(latitude=51.5074, longitude=-0.1278)
        for frac in [0.0, 0.1, 0.25, 0.5, 0.75, 0.9, 1.0]:
            result = interpolate_great_circle(start, end, frac)
            assert -90 <= result.latitude <= 90
            assert -180 <= result.longitude <= 180

    def test_monotonic_distance_along_path(self) -> None:
        """Distance from start should increase monotonically with fraction."""
        start = Coordinate(latitude=0.0, longitude=0.0)
        end = Coordinate(latitude=45.0, longitude=90.0)
        prev_dist = 0.0
        for frac in [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]:
            point = interpolate_great_circle(start, end, frac)
            dist = start.distance_to(point)
            assert dist >= prev_dist
            prev_dist = dist
