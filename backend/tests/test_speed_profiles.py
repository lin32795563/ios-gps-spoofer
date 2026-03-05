"""Tests for ios_gps_spoofer.simulation.speed_profiles module.

Tests cover:
- SpeedPreset values
- Conversion utilities (kmh_to_ms, ms_to_kmh)
- SpeedController: preset, custom speed, thread-safe access
- Validation: NaN, Inf, negative, zero, too large, bool, non-numeric
"""

import threading

import pytest

from ios_gps_spoofer.simulation.speed_profiles import (
    MAX_SPEED_MS,
    MIN_SPEED_MS,
    SpeedController,
    SpeedPreset,
    kmh_to_ms,
    ms_to_kmh,
    preset_to_ms,
)


class TestSpeedPreset:
    """Tests for SpeedPreset enum."""

    def test_walking_is_5_kmh(self) -> None:
        assert SpeedPreset.WALKING.value == 5.0

    def test_cycling_is_15_kmh(self) -> None:
        assert SpeedPreset.CYCLING.value == 15.0

    def test_driving_is_60_kmh(self) -> None:
        assert SpeedPreset.DRIVING.value == 60.0

    def test_all_presets_exist(self) -> None:
        assert len(SpeedPreset) == 3


class TestConversions:
    """Tests for speed conversion utilities."""

    def test_kmh_to_ms_zero(self) -> None:
        assert kmh_to_ms(0.0) == 0.0

    def test_kmh_to_ms_known_value(self) -> None:
        # 3.6 km/h = 1.0 m/s
        assert kmh_to_ms(3.6) == pytest.approx(1.0)

    def test_ms_to_kmh_known_value(self) -> None:
        assert ms_to_kmh(1.0) == pytest.approx(3.6)

    def test_round_trip(self) -> None:
        original = 42.5
        assert ms_to_kmh(kmh_to_ms(original)) == pytest.approx(original)

    def test_preset_to_ms_walking(self) -> None:
        speed_ms = preset_to_ms(SpeedPreset.WALKING)
        assert speed_ms == pytest.approx(5.0 * 1000 / 3600)

    def test_preset_to_ms_driving(self) -> None:
        speed_ms = preset_to_ms(SpeedPreset.DRIVING)
        assert speed_ms == pytest.approx(60.0 * 1000 / 3600)


class TestSpeedController:
    """Tests for SpeedController."""

    def test_default_preset_is_walking(self) -> None:
        ctrl = SpeedController()
        assert ctrl.speed_ms == pytest.approx(preset_to_ms(SpeedPreset.WALKING))

    def test_custom_initial_preset(self) -> None:
        ctrl = SpeedController(initial_preset=SpeedPreset.DRIVING)
        assert ctrl.speed_kmh == pytest.approx(60.0)

    def test_set_speed_ms(self) -> None:
        ctrl = SpeedController()
        ctrl.set_speed_ms(10.0)
        assert ctrl.speed_ms == pytest.approx(10.0)

    def test_set_speed_kmh(self) -> None:
        ctrl = SpeedController()
        ctrl.set_speed_kmh(36.0)
        assert ctrl.speed_ms == pytest.approx(10.0)

    def test_set_preset(self) -> None:
        ctrl = SpeedController()
        ctrl.set_preset(SpeedPreset.CYCLING)
        assert ctrl.speed_kmh == pytest.approx(15.0)

    def test_speed_kmh_property(self) -> None:
        ctrl = SpeedController()
        ctrl.set_speed_ms(10.0)
        assert ctrl.speed_kmh == pytest.approx(36.0)


class TestSpeedControllerValidation:
    """Tests for SpeedController input validation."""

    def test_zero_speed_raises(self) -> None:
        ctrl = SpeedController()
        with pytest.raises(ValueError, match="at least"):
            ctrl.set_speed_ms(0.0)

    def test_negative_speed_raises(self) -> None:
        ctrl = SpeedController()
        with pytest.raises(ValueError, match="at least"):
            ctrl.set_speed_ms(-5.0)

    def test_speed_below_minimum_raises(self) -> None:
        ctrl = SpeedController()
        with pytest.raises(ValueError, match="at least"):
            ctrl.set_speed_ms(MIN_SPEED_MS / 2)

    def test_speed_above_maximum_raises(self) -> None:
        ctrl = SpeedController()
        with pytest.raises(ValueError, match="at most"):
            ctrl.set_speed_ms(MAX_SPEED_MS + 1.0)

    def test_nan_speed_raises(self) -> None:
        ctrl = SpeedController()
        with pytest.raises(ValueError, match="finite"):
            ctrl.set_speed_ms(float("nan"))

    def test_inf_speed_raises(self) -> None:
        ctrl = SpeedController()
        with pytest.raises(ValueError, match="finite"):
            ctrl.set_speed_ms(float("inf"))

    def test_neg_inf_speed_raises(self) -> None:
        ctrl = SpeedController()
        with pytest.raises(ValueError, match="finite"):
            ctrl.set_speed_ms(float("-inf"))

    def test_bool_speed_raises(self) -> None:
        ctrl = SpeedController()
        with pytest.raises(ValueError, match="number"):
            ctrl.set_speed_ms(True)  # type: ignore[arg-type]

    def test_string_speed_raises(self) -> None:
        ctrl = SpeedController()
        with pytest.raises(ValueError, match="number"):
            ctrl.set_speed_ms("fast")  # type: ignore[arg-type]

    def test_minimum_speed_accepted(self) -> None:
        ctrl = SpeedController()
        ctrl.set_speed_ms(MIN_SPEED_MS)
        assert ctrl.speed_ms == pytest.approx(MIN_SPEED_MS)

    def test_maximum_speed_accepted(self) -> None:
        ctrl = SpeedController()
        ctrl.set_speed_ms(MAX_SPEED_MS)
        assert ctrl.speed_ms == pytest.approx(MAX_SPEED_MS)


class TestSpeedControllerThreadSafety:
    """Tests for concurrent speed changes."""

    def test_concurrent_set_speed_no_crash(self) -> None:
        ctrl = SpeedController()
        errors: list[Exception] = []

        def worker(speed_ms: float) -> None:
            try:
                for _ in range(100):
                    ctrl.set_speed_ms(speed_ms)
                    _ = ctrl.speed_ms
                    _ = ctrl.speed_kmh
            except Exception as exc:
                errors.append(exc)

        threads = [
            threading.Thread(target=worker, args=(1.0,)),
            threading.Thread(target=worker, args=(5.0,)),
            threading.Thread(target=worker, args=(10.0,)),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10.0)

        assert len(errors) == 0, f"Errors: {errors}"
