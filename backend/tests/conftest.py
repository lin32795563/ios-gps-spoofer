"""Shared pytest fixtures for the iOS GPS Spoofer test suite."""

import pytest


@pytest.fixture
def sample_device_info() -> dict:
    """Return a sample device info dictionary for testing."""
    return {
        "udid": "00008030-001A3C440C02002E",
        "name": "iPhone 15 Pro",
        "product_type": "iPhone16,1",
        "product_version": "17.2.1",
        "build_version": "21C66",
        "chip_id": 33056,
        "hardware_model": "D83AP",
    }


@pytest.fixture
def sample_device_info_ios16() -> dict:
    """Return a sample device info dictionary for iOS 16 device."""
    return {
        "udid": "00008020-000A1C340C01001E",
        "name": "iPhone 14",
        "product_type": "iPhone15,2",
        "product_version": "16.7.4",
        "build_version": "20H240",
        "chip_id": 33040,
        "hardware_model": "D73AP",
    }
