"""Tests for ios_gps_spoofer.device.version_utils module.

Covers:
- Version parsing (valid, invalid, edge cases)
- iOS version classification (LEGACY, DDI, TUNNEL boundaries)
- Helper functions (is_ios_17_or_later, is_developer_mode_required, version_for_ddi_lookup)
"""

import pytest
from packaging.version import Version

from ios_gps_spoofer.device.models import IOSVersionCategory
from ios_gps_spoofer.device.version_utils import (
    classify_ios_version,
    is_developer_mode_required,
    is_ios_17_or_later,
    parse_ios_version,
    version_for_ddi_lookup,
)

# =====================================================================
# parse_ios_version
# =====================================================================

class TestParseIosVersion:
    """Tests for parse_ios_version."""

    def test_parse_major_minor_patch(self) -> None:
        result = parse_ios_version("17.2.1")
        assert result == Version("17.2.1")

    def test_parse_major_minor(self) -> None:
        result = parse_ios_version("16.7")
        assert result == Version("16.7")

    def test_parse_major_only(self) -> None:
        result = parse_ios_version("17")
        assert result == Version("17")

    def test_parse_with_leading_trailing_whitespace(self) -> None:
        result = parse_ios_version("  17.2.1  ")
        assert result == Version("17.2.1")

    def test_parse_empty_string_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="empty or blank"):
            parse_ios_version("")

    def test_parse_whitespace_only_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="empty or blank"):
            parse_ios_version("   ")

    def test_parse_invalid_version_string_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="Cannot parse"):
            parse_ios_version("not.a.version")

    def test_parse_garbage_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="Cannot parse"):
            parse_ios_version("abc")

    def test_parse_version_comparisons_work(self) -> None:
        """Verify parsed versions support comparison operators."""
        v14 = parse_ios_version("14.0")
        v16 = parse_ios_version("16.0")
        v17 = parse_ios_version("17.0")
        assert v14 < v16 < v17
        assert v17 > v16 > v14
        assert v16 == parse_ios_version("16.0")


# =====================================================================
# classify_ios_version
# =====================================================================

class TestClassifyIosVersion:
    """Tests for classify_ios_version."""

    # LEGACY: iOS 14.x - 15.x
    def test_ios_14_0_is_legacy(self) -> None:
        assert classify_ios_version("14.0") == IOSVersionCategory.LEGACY

    def test_ios_14_8_1_is_legacy(self) -> None:
        assert classify_ios_version("14.8.1") == IOSVersionCategory.LEGACY

    def test_ios_15_0_is_legacy(self) -> None:
        assert classify_ios_version("15.0") == IOSVersionCategory.LEGACY

    def test_ios_15_8_is_legacy(self) -> None:
        assert classify_ios_version("15.8") == IOSVersionCategory.LEGACY

    # DDI: iOS 16.x
    def test_ios_16_0_is_ddi(self) -> None:
        assert classify_ios_version("16.0") == IOSVersionCategory.DDI

    def test_ios_16_7_4_is_ddi(self) -> None:
        assert classify_ios_version("16.7.4") == IOSVersionCategory.DDI

    # TUNNEL: iOS 17+
    def test_ios_17_0_is_tunnel(self) -> None:
        assert classify_ios_version("17.0") == IOSVersionCategory.TUNNEL

    def test_ios_17_2_1_is_tunnel(self) -> None:
        assert classify_ios_version("17.2.1") == IOSVersionCategory.TUNNEL

    def test_ios_18_0_is_tunnel(self) -> None:
        assert classify_ios_version("18.0") == IOSVersionCategory.TUNNEL

    # Below minimum
    def test_ios_13_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="below the minimum"):
            classify_ios_version("13.7")

    def test_ios_12_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="below the minimum"):
            classify_ios_version("12.0")

    def test_ios_1_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="below the minimum"):
            classify_ios_version("1.0")

    # Boundary: exactly at 16.0 boundary
    def test_ios_15_9_999_is_legacy(self) -> None:
        """15.9.999 should still be LEGACY (below 16.0)."""
        assert classify_ios_version("15.9") == IOSVersionCategory.LEGACY

    # Boundary: exactly at 17.0 boundary
    def test_ios_16_9_is_ddi(self) -> None:
        assert classify_ios_version("16.9") == IOSVersionCategory.DDI


# =====================================================================
# is_ios_17_or_later
# =====================================================================

class TestIsIos17OrLater:
    """Tests for is_ios_17_or_later."""

    def test_ios_17_0_returns_true(self) -> None:
        assert is_ios_17_or_later("17.0") is True

    def test_ios_17_2_1_returns_true(self) -> None:
        assert is_ios_17_or_later("17.2.1") is True

    def test_ios_18_0_returns_true(self) -> None:
        assert is_ios_17_or_later("18.0") is True

    def test_ios_16_7_returns_false(self) -> None:
        assert is_ios_17_or_later("16.7") is False

    def test_ios_15_0_returns_false(self) -> None:
        assert is_ios_17_or_later("15.0") is False


# =====================================================================
# is_developer_mode_required
# =====================================================================

class TestIsDeveloperModeRequired:
    """Tests for is_developer_mode_required."""

    def test_ios_16_0_requires_dev_mode(self) -> None:
        assert is_developer_mode_required("16.0") is True

    def test_ios_16_7_requires_dev_mode(self) -> None:
        assert is_developer_mode_required("16.7") is True

    def test_ios_17_0_requires_dev_mode(self) -> None:
        assert is_developer_mode_required("17.0") is True

    def test_ios_15_8_does_not_require_dev_mode(self) -> None:
        assert is_developer_mode_required("15.8") is False

    def test_ios_14_0_does_not_require_dev_mode(self) -> None:
        assert is_developer_mode_required("14.0") is False


# =====================================================================
# version_for_ddi_lookup
# =====================================================================

class TestVersionForDdiLookup:
    """Tests for version_for_ddi_lookup."""

    def test_strips_patch_version(self) -> None:
        assert version_for_ddi_lookup("16.7.4") == "16.7"

    def test_major_minor_unchanged(self) -> None:
        assert version_for_ddi_lookup("16.7") == "16.7"

    def test_major_only_gets_zero_minor(self) -> None:
        assert version_for_ddi_lookup("16") == "16.0"

    def test_ios_14_version(self) -> None:
        assert version_for_ddi_lookup("14.8.1") == "14.8"

    def test_ios_15_version(self) -> None:
        assert version_for_ddi_lookup("15.6") == "15.6"
