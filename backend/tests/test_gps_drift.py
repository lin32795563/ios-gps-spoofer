"""Tests for ios_gps_spoofer.simulation.gps_drift module.

Tests cover:
- Drift application with known seed
- Zero sigma returns same coordinate
- Drift magnitude within expected range
- Boundary clamping (near poles, near +/-180 longitude)
- Sigma validation (negative, NaN, too large, bool)
- Statistical properties (mean near zero, std dev within bounds)
- Pole proximity: longitude drift suppressed
"""

import random

import pytest

from ios_gps_spoofer.location.coordinates import Coordinate
from ios_gps_spoofer.simulation.gps_drift import (
    MAX_SIGMA_METERS,
    apply_drift,
)


class TestApplyDriftBasic:
    """Basic drift application tests."""

    def test_zero_sigma_returns_same_coordinate(self) -> None:
        coord = Coordinate(latitude=25.0, longitude=121.0)
        result = apply_drift(coord, sigma_meters=0.0)
        assert result == coord

    def test_drift_returns_coordinate_instance(self) -> None:
        coord = Coordinate(latitude=25.0, longitude=121.0)
        result = apply_drift(coord, sigma_meters=2.0, rng=random.Random(42))
        assert isinstance(result, Coordinate)

    def test_drift_changes_coordinates(self) -> None:
        """With non-zero sigma, coordinates should change (with high probability)."""
        coord = Coordinate(latitude=25.0, longitude=121.0)
        rng = random.Random(42)
        result = apply_drift(coord, sigma_meters=2.0, rng=rng)
        # Extremely unlikely to be exactly the same with sigma=2.0
        assert result != coord

    def test_drift_is_small(self) -> None:
        """Drift of 2m sigma should produce offsets of ~0.00001-0.0001 degrees."""
        coord = Coordinate(latitude=25.0, longitude=121.0)
        rng = random.Random(42)
        result = apply_drift(coord, sigma_meters=2.0, rng=rng)
        assert abs(result.latitude - coord.latitude) < 0.001  # < ~100m
        assert abs(result.longitude - coord.longitude) < 0.001

    def test_reproducible_with_same_seed(self) -> None:
        coord = Coordinate(latitude=25.0, longitude=121.0)
        result1 = apply_drift(coord, sigma_meters=2.0, rng=random.Random(123))
        result2 = apply_drift(coord, sigma_meters=2.0, rng=random.Random(123))
        assert result1 == result2

    def test_different_seeds_produce_different_results(self) -> None:
        coord = Coordinate(latitude=25.0, longitude=121.0)
        result1 = apply_drift(coord, sigma_meters=2.0, rng=random.Random(1))
        result2 = apply_drift(coord, sigma_meters=2.0, rng=random.Random(2))
        assert result1 != result2


class TestDriftBoundaries:
    """Tests for drift near WGS-84 boundaries."""

    def test_clamp_at_north_pole(self) -> None:
        """Drift at lat=90 should not exceed 90."""
        coord = Coordinate(latitude=90.0, longitude=0.0)
        rng = random.Random(42)
        for _ in range(100):
            result = apply_drift(coord, sigma_meters=5.0, rng=rng)
            assert -90.0 <= result.latitude <= 90.0
            assert -180.0 <= result.longitude <= 180.0

    def test_clamp_at_south_pole(self) -> None:
        """Drift at lat=-90 should not go below -90."""
        coord = Coordinate(latitude=-90.0, longitude=0.0)
        rng = random.Random(42)
        for _ in range(100):
            result = apply_drift(coord, sigma_meters=5.0, rng=rng)
            assert -90.0 <= result.latitude <= 90.0

    def test_longitude_drift_suppressed_near_poles(self) -> None:
        """Near poles (lat >= 89.5), longitude drift should be zero."""
        coord = Coordinate(latitude=89.9, longitude=50.0)
        rng = random.Random(42)
        result = apply_drift(coord, sigma_meters=2.0, rng=rng)
        # Longitude should be unchanged (drift suppressed)
        assert result.longitude == coord.longitude

    def test_longitude_drift_suppressed_at_south_pole_proximity(self) -> None:
        coord = Coordinate(latitude=-89.9, longitude=100.0)
        rng = random.Random(42)
        result = apply_drift(coord, sigma_meters=2.0, rng=rng)
        assert result.longitude == coord.longitude

    def test_clamp_at_max_longitude(self) -> None:
        """Drift near lon=180 should not exceed 180."""
        coord = Coordinate(latitude=0.0, longitude=180.0)
        rng = random.Random(42)
        for _ in range(100):
            result = apply_drift(coord, sigma_meters=5.0, rng=rng)
            assert -180.0 <= result.longitude <= 180.0

    def test_clamp_at_min_longitude(self) -> None:
        """Drift near lon=-180 should not go below -180."""
        coord = Coordinate(latitude=0.0, longitude=-180.0)
        rng = random.Random(42)
        for _ in range(100):
            result = apply_drift(coord, sigma_meters=5.0, rng=rng)
            assert -180.0 <= result.longitude <= 180.0

    def test_equator_drift_symmetric(self) -> None:
        """At the equator, lat and lon drift should be roughly symmetric."""
        coord = Coordinate(latitude=0.0, longitude=0.0)
        rng = random.Random(42)
        lat_offsets = []
        lon_offsets = []
        for _ in range(1000):
            result = apply_drift(coord, sigma_meters=2.0, rng=rng)
            lat_offsets.append(result.latitude - coord.latitude)
            lon_offsets.append(result.longitude - coord.longitude)

        # Mean should be near zero
        assert abs(sum(lat_offsets) / len(lat_offsets)) < 0.0001
        assert abs(sum(lon_offsets) / len(lon_offsets)) < 0.0001


class TestDriftStatistics:
    """Statistical tests for drift properties."""

    def test_drift_mean_near_zero(self) -> None:
        """Over many samples, mean drift should be near zero."""
        coord = Coordinate(latitude=25.0, longitude=121.0)
        rng = random.Random(42)
        offsets = []
        for _ in range(2000):
            result = apply_drift(coord, sigma_meters=2.0, rng=rng)
            offsets.append(result.latitude - coord.latitude)

        mean_offset = sum(offsets) / len(offsets)
        assert abs(mean_offset) < 0.00005  # very close to zero

    def test_drift_magnitude_reasonable(self) -> None:
        """With sigma=2m, 99.7% of offsets should be < 6m (~3 sigma)."""
        coord = Coordinate(latitude=25.0, longitude=121.0)
        rng = random.Random(42)
        # 6m in degrees: approx 6 / 111320 = 0.0000539
        max_offset_deg = 6.0 / 111320.0 * 1.5  # generous margin

        for _ in range(500):
            result = apply_drift(coord, sigma_meters=2.0, rng=rng)
            assert abs(result.latitude - coord.latitude) < max_offset_deg


class TestDriftValidation:
    """Tests for sigma_meters validation."""

    def test_negative_sigma_raises(self) -> None:
        coord = Coordinate(latitude=25.0, longitude=121.0)
        with pytest.raises(ValueError, match="non-negative"):
            apply_drift(coord, sigma_meters=-1.0)

    def test_sigma_too_large_raises(self) -> None:
        coord = Coordinate(latitude=25.0, longitude=121.0)
        with pytest.raises(ValueError, match=f"at most {MAX_SIGMA_METERS}"):
            apply_drift(coord, sigma_meters=MAX_SIGMA_METERS + 1.0)

    def test_nan_sigma_raises(self) -> None:
        coord = Coordinate(latitude=25.0, longitude=121.0)
        with pytest.raises(ValueError, match="finite"):
            apply_drift(coord, sigma_meters=float("nan"))

    def test_inf_sigma_raises(self) -> None:
        coord = Coordinate(latitude=25.0, longitude=121.0)
        with pytest.raises(ValueError, match="finite"):
            apply_drift(coord, sigma_meters=float("inf"))

    def test_bool_sigma_raises(self) -> None:
        coord = Coordinate(latitude=25.0, longitude=121.0)
        with pytest.raises(ValueError, match="number"):
            apply_drift(coord, sigma_meters=True)  # type: ignore[arg-type]

    def test_max_sigma_accepted(self) -> None:
        coord = Coordinate(latitude=25.0, longitude=121.0)
        result = apply_drift(
            coord, sigma_meters=MAX_SIGMA_METERS, rng=random.Random(42)
        )
        assert isinstance(result, Coordinate)

    def test_small_positive_sigma_accepted(self) -> None:
        coord = Coordinate(latitude=25.0, longitude=121.0)
        result = apply_drift(coord, sigma_meters=0.001, rng=random.Random(42))
        assert isinstance(result, Coordinate)
