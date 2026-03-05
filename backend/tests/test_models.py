"""Tests for ios_gps_spoofer.device.models module.

Covers:
- DeviceInfo immutability and construction
- DeviceConnection state management, serialization, and error handling
- ConnectionState and IOSVersionCategory enum values
"""

from datetime import timezone

import pytest

from ios_gps_spoofer.device.models import (
    ConnectionState,
    DeviceConnection,
    DeviceInfo,
    IOSVersionCategory,
)

# =====================================================================
# DeviceInfo
# =====================================================================

class TestDeviceInfo:
    """Tests for DeviceInfo dataclass."""

    def test_construction_with_all_fields(self) -> None:
        info = DeviceInfo(
            udid="abc123",
            name="Test iPhone",
            product_type="iPhone16,1",
            product_version="17.2.1",
            build_version="21C66",
            chip_id=33056,
            hardware_model="D83AP",
            device_class="iPhone",
        )
        assert info.udid == "abc123"
        assert info.name == "Test iPhone"
        assert info.product_version == "17.2.1"
        assert info.device_class == "iPhone"

    def test_default_device_class_is_iphone(self) -> None:
        info = DeviceInfo(
            udid="abc",
            name="Test",
            product_type="iPhone16,1",
            product_version="17.0",
            build_version="21A",
            chip_id=0,
            hardware_model="D83AP",
        )
        assert info.device_class == "iPhone"

    def test_frozen_cannot_modify_fields(self) -> None:
        info = DeviceInfo(
            udid="abc",
            name="Test",
            product_type="iPhone16,1",
            product_version="17.0",
            build_version="21A",
            chip_id=0,
            hardware_model="D83AP",
        )
        with pytest.raises(AttributeError):
            info.udid = "changed"  # type: ignore[misc]

    def test_equality(self) -> None:
        kwargs = dict(
            udid="abc",
            name="Test",
            product_type="iPhone16,1",
            product_version="17.0",
            build_version="21A",
            chip_id=0,
            hardware_model="D83AP",
        )
        info1 = DeviceInfo(**kwargs)
        info2 = DeviceInfo(**kwargs)
        assert info1 == info2

    def test_inequality_different_udid(self) -> None:
        kwargs = dict(
            name="Test",
            product_type="iPhone16,1",
            product_version="17.0",
            build_version="21A",
            chip_id=0,
            hardware_model="D83AP",
        )
        info1 = DeviceInfo(udid="abc", **kwargs)
        info2 = DeviceInfo(udid="xyz", **kwargs)
        assert info1 != info2


# =====================================================================
# DeviceConnection
# =====================================================================

class TestDeviceConnection:
    """Tests for DeviceConnection dataclass."""

    @pytest.fixture
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            udid="test-udid-001",
            name="Test iPhone",
            product_type="iPhone16,1",
            product_version="17.2.1",
            build_version="21C66",
            chip_id=33056,
            hardware_model="D83AP",
        )

    def test_default_state_is_detected(self, device_info: DeviceInfo) -> None:
        conn = DeviceConnection(device_info=device_info)
        assert conn.state == ConnectionState.DETECTED

    def test_default_ios_category_is_tunnel(self, device_info: DeviceInfo) -> None:
        conn = DeviceConnection(device_info=device_info)
        assert conn.ios_category == IOSVersionCategory.TUNNEL

    def test_udid_property(self, device_info: DeviceInfo) -> None:
        conn = DeviceConnection(device_info=device_info)
        assert conn.udid == "test-udid-001"

    def test_is_ready_false_when_not_ready(self, device_info: DeviceInfo) -> None:
        conn = DeviceConnection(device_info=device_info)
        assert conn.is_ready is False

    def test_is_ready_true_when_ready(self, device_info: DeviceInfo) -> None:
        conn = DeviceConnection(device_info=device_info, state=ConnectionState.READY)
        assert conn.is_ready is True

    def test_is_error_false_by_default(self, device_info: DeviceInfo) -> None:
        conn = DeviceConnection(device_info=device_info)
        assert conn.is_error is False

    def test_set_error_transitions_state(self, device_info: DeviceInfo) -> None:
        conn = DeviceConnection(device_info=device_info)
        conn.set_error("something broke")
        assert conn.state == ConnectionState.ERROR
        assert conn.error_message == "something broke"
        assert conn.is_error is True

    def test_update_last_seen(self, device_info: DeviceInfo) -> None:
        conn = DeviceConnection(device_info=device_info)
        old_time = conn.last_seen_at
        # Ensure some time passes (datetime precision)
        conn.update_last_seen()
        assert conn.last_seen_at >= old_time

    def test_connected_at_is_utc(self, device_info: DeviceInfo) -> None:
        conn = DeviceConnection(device_info=device_info)
        assert conn.connected_at.tzinfo is not None
        assert conn.connected_at.tzinfo == timezone.utc

    def test_to_dict_contains_all_keys(self, device_info: DeviceInfo) -> None:
        conn = DeviceConnection(device_info=device_info)
        d = conn.to_dict()
        expected_keys = {
            "udid", "name", "product_type", "product_version",
            "build_version", "device_class", "state", "ios_category",
            "is_ready", "error_message", "connected_at", "last_seen_at",
        }
        assert set(d.keys()) == expected_keys

    def test_to_dict_values_are_serializable(self, device_info: DeviceInfo) -> None:
        conn = DeviceConnection(device_info=device_info)
        d = conn.to_dict()
        # All values should be JSON-serializable primitives
        for key, value in d.items():
            assert isinstance(value, (str, bool, int, float, type(None))), (
                f"Key '{key}' has non-serializable type: {type(value)}"
            )

    def test_to_dict_state_is_string(self, device_info: DeviceInfo) -> None:
        conn = DeviceConnection(device_info=device_info)
        d = conn.to_dict()
        assert d["state"] == "detected"
        assert isinstance(d["state"], str)

    def test_to_dict_error_message_none_by_default(self, device_info: DeviceInfo) -> None:
        conn = DeviceConnection(device_info=device_info)
        d = conn.to_dict()
        assert d["error_message"] is None


# =====================================================================
# Enum values
# =====================================================================

class TestConnectionState:
    """Tests for ConnectionState enum."""

    def test_all_expected_states_exist(self) -> None:
        expected = {
            "disconnected", "detected", "connecting", "paired",
            "ddi_mounted", "tunnel_established", "ready", "error",
        }
        actual = {s.value for s in ConnectionState}
        assert actual == expected

    def test_value_access(self) -> None:
        assert ConnectionState.READY.value == "ready"
        assert ConnectionState.ERROR.value == "error"


class TestIOSVersionCategory:
    """Tests for IOSVersionCategory enum."""

    def test_all_expected_categories_exist(self) -> None:
        expected = {"legacy", "ddi", "tunnel"}
        actual = {c.value for c in IOSVersionCategory}
        assert actual == expected
