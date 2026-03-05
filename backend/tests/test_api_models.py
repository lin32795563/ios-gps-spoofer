"""Tests for API Pydantic models."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from ios_gps_spoofer.api.models import (
    AddFavoriteRequest,
    ClearLocationRequest,
    CoordinateModel,
    DeviceInfoResponse,
    DeviceListResponse,
    ErrorResponse,
    FavoriteListResponse,
    FavoriteLocation,
    GPXParseResponse,
    LoadGPXRequest,
    LocationStatusResponse,
    SetLocationRequest,
    SetSpeedRequest,
    SimulationProgressResponse,
    SimulationStatusResponse,
    StartSimulationRequest,
    SuccessResponse,
    WSDeviceDisconnected,
    WSDeviceUpdate,
    WSHeartbeat,
    WSSimulationComplete,
    WSSimulationError,
    WSSimulationProgress,
)

# ------------------------------------------------------------------
# CoordinateModel
# ------------------------------------------------------------------

class TestCoordinateModel:
    """Tests for CoordinateModel."""

    def test_valid_coordinate(self):
        c = CoordinateModel(latitude=25.0, longitude=121.5)
        assert c.latitude == 25.0
        assert c.longitude == 121.5

    def test_boundary_values(self):
        c = CoordinateModel(latitude=90.0, longitude=180.0)
        assert c.latitude == 90.0
        assert c.longitude == 180.0

        c = CoordinateModel(latitude=-90.0, longitude=-180.0)
        assert c.latitude == -90.0
        assert c.longitude == -180.0

    def test_latitude_out_of_range(self):
        with pytest.raises(ValidationError):
            CoordinateModel(latitude=91.0, longitude=0.0)

    def test_longitude_out_of_range(self):
        with pytest.raises(ValidationError):
            CoordinateModel(latitude=0.0, longitude=181.0)

    def test_zero_zero(self):
        c = CoordinateModel(latitude=0.0, longitude=0.0)
        assert c.latitude == 0.0
        assert c.longitude == 0.0


# ------------------------------------------------------------------
# SetLocationRequest
# ------------------------------------------------------------------

class TestSetLocationRequest:
    """Tests for SetLocationRequest."""

    def test_valid_request(self):
        req = SetLocationRequest(udid="abc123", latitude=25.0, longitude=121.5)
        assert req.udid == "abc123"
        assert req.latitude == 25.0

    def test_empty_udid_rejected(self):
        with pytest.raises(ValidationError):
            SetLocationRequest(udid="", latitude=25.0, longitude=121.5)

    def test_missing_udid_rejected(self):
        with pytest.raises(ValidationError):
            SetLocationRequest(latitude=25.0, longitude=121.5)

    def test_latitude_out_of_range_rejected(self):
        with pytest.raises(ValidationError):
            SetLocationRequest(udid="abc", latitude=95.0, longitude=0.0)


# ------------------------------------------------------------------
# ClearLocationRequest
# ------------------------------------------------------------------

class TestClearLocationRequest:
    """Tests for ClearLocationRequest."""

    def test_valid(self):
        req = ClearLocationRequest(udid="device-123")
        assert req.udid == "device-123"

    def test_empty_udid(self):
        with pytest.raises(ValidationError):
            ClearLocationRequest(udid="")


# ------------------------------------------------------------------
# StartSimulationRequest
# ------------------------------------------------------------------

class TestStartSimulationRequest:
    """Tests for StartSimulationRequest."""

    def test_valid_request(self):
        req = StartSimulationRequest(
            udid="device-1",
            path=[
                CoordinateModel(latitude=25.0, longitude=121.5),
                CoordinateModel(latitude=25.1, longitude=121.6),
            ],
        )
        assert len(req.path) == 2
        assert req.speed_kmh == 5.0  # default
        assert req.drift_enabled is True
        assert req.loop_path is False

    def test_custom_values(self):
        req = StartSimulationRequest(
            udid="device-1",
            path=[
                CoordinateModel(latitude=25.0, longitude=121.5),
                CoordinateModel(latitude=25.1, longitude=121.6),
            ],
            speed_kmh=60.0,
            drift_enabled=False,
            drift_sigma_meters=3.0,
            loop_path=True,
        )
        assert req.speed_kmh == 60.0
        assert req.drift_enabled is False
        assert req.drift_sigma_meters == 3.0
        assert req.loop_path is True

    def test_single_point_rejected(self):
        with pytest.raises(ValidationError):
            StartSimulationRequest(
                udid="device-1",
                path=[CoordinateModel(latitude=25.0, longitude=121.5)],
            )

    def test_empty_path_rejected(self):
        with pytest.raises(ValidationError):
            StartSimulationRequest(udid="device-1", path=[])

    def test_speed_zero_rejected(self):
        with pytest.raises(ValidationError):
            StartSimulationRequest(
                udid="device-1",
                path=[
                    CoordinateModel(latitude=25.0, longitude=121.5),
                    CoordinateModel(latitude=25.1, longitude=121.6),
                ],
                speed_kmh=0.0,
            )

    def test_speed_negative_rejected(self):
        with pytest.raises(ValidationError):
            StartSimulationRequest(
                udid="device-1",
                path=[
                    CoordinateModel(latitude=25.0, longitude=121.5),
                    CoordinateModel(latitude=25.1, longitude=121.6),
                ],
                speed_kmh=-5.0,
            )

    def test_drift_sigma_too_large_rejected(self):
        with pytest.raises(ValidationError):
            StartSimulationRequest(
                udid="device-1",
                path=[
                    CoordinateModel(latitude=25.0, longitude=121.5),
                    CoordinateModel(latitude=25.1, longitude=121.6),
                ],
                drift_sigma_meters=15.0,
            )


# ------------------------------------------------------------------
# SetSpeedRequest
# ------------------------------------------------------------------

class TestSetSpeedRequest:
    """Tests for SetSpeedRequest."""

    def test_valid(self):
        req = SetSpeedRequest(udid="d1", speed_kmh=30.0)
        assert req.speed_kmh == 30.0

    def test_speed_zero_rejected(self):
        with pytest.raises(ValidationError):
            SetSpeedRequest(udid="d1", speed_kmh=0.0)

    def test_speed_over_max_rejected(self):
        with pytest.raises(ValidationError):
            SetSpeedRequest(udid="d1", speed_kmh=1001.0)


# ------------------------------------------------------------------
# LoadGPXRequest
# ------------------------------------------------------------------

class TestLoadGPXRequest:
    """Tests for LoadGPXRequest."""

    def test_valid(self):
        req = LoadGPXRequest(gpx_content="<gpx>...</gpx>")
        assert req.gpx_content == "<gpx>...</gpx>"
        assert req.source == "<upload>"

    def test_empty_content_rejected(self):
        with pytest.raises(ValidationError):
            LoadGPXRequest(gpx_content="")

    def test_custom_source(self):
        req = LoadGPXRequest(gpx_content="<gpx/>", source="my-file.gpx")
        assert req.source == "my-file.gpx"


# ------------------------------------------------------------------
# FavoriteLocation / AddFavoriteRequest
# ------------------------------------------------------------------

class TestFavoriteModels:
    """Tests for FavoriteLocation and AddFavoriteRequest."""

    def test_valid_favorite(self):
        fav = FavoriteLocation(name="Home", latitude=25.03, longitude=121.56)
        assert fav.name == "Home"

    def test_empty_name_rejected(self):
        with pytest.raises(ValidationError):
            FavoriteLocation(name="", latitude=25.03, longitude=121.56)

    def test_name_too_long_rejected(self):
        with pytest.raises(ValidationError):
            FavoriteLocation(name="x" * 201, latitude=25.03, longitude=121.56)

    def test_add_favorite_request(self):
        req = AddFavoriteRequest(name="Office", latitude=25.05, longitude=121.55)
        assert req.name == "Office"


# ------------------------------------------------------------------
# Response models
# ------------------------------------------------------------------

class TestResponseModels:
    """Tests for response models."""

    def test_success_response_defaults(self):
        resp = SuccessResponse()
        assert resp.success is True
        assert resp.message == ""

    def test_success_response_custom(self):
        resp = SuccessResponse(message="Done!")
        assert resp.message == "Done!"

    def test_error_response(self):
        resp = ErrorResponse(error="Not found", detail="Device not connected")
        assert resp.success is False
        assert resp.error == "Not found"

    def test_device_info_response(self):
        resp = DeviceInfoResponse(
            udid="abc",
            name="iPhone",
            product_type="iPhone16,1",
            product_version="17.2",
            build_version="21C66",
            device_class="iPhone",
            state="ready",
            ios_category="tunnel",
            is_ready=True,
            connected_at="2024-01-01T00:00:00",
            last_seen_at="2024-01-01T00:00:00",
        )
        assert resp.udid == "abc"
        assert resp.is_ready is True

    def test_device_list_response(self):
        resp = DeviceListResponse(devices=[], count=0)
        assert resp.count == 0

    def test_location_status_response(self):
        resp = LocationStatusResponse(
            udid="d1",
            simulation_active=True,
            current_location=CoordinateModel(latitude=25.0, longitude=121.5),
        )
        assert resp.simulation_active is True
        assert resp.current_location is not None

    def test_location_status_no_location(self):
        resp = LocationStatusResponse(
            udid="d1",
            simulation_active=False,
        )
        assert resp.current_location is None

    def test_simulation_progress_response(self):
        resp = SimulationProgressResponse(
            current_position=CoordinateModel(latitude=25.0, longitude=121.5),
            segment_index=0,
            total_segments=3,
            distance_covered_m=100.0,
            total_distance_m=500.0,
            fraction_complete=0.2,
            elapsed_time_s=10.0,
            speed_ms=1.39,
            state="running",
        )
        assert resp.fraction_complete == 0.2

    def test_simulation_status_response(self):
        resp = SimulationStatusResponse(
            udid="d1",
            state="running",
            speed_kmh=15.0,
            progress=None,
        )
        assert resp.state == "running"

    def test_gpx_parse_response(self):
        resp = GPXParseResponse(
            waypoints=[CoordinateModel(latitude=25.0, longitude=121.5)],
            count=1,
        )
        assert resp.count == 1

    def test_favorite_list_response(self):
        resp = FavoriteListResponse(favorites=[], count=0)
        assert resp.count == 0


# ------------------------------------------------------------------
# WebSocket message models
# ------------------------------------------------------------------

class TestWSModels:
    """Tests for WebSocket message models."""

    def test_device_update(self):
        device = DeviceInfoResponse(
            udid="abc",
            name="iPhone",
            product_type="iPhone16,1",
            product_version="17.2",
            build_version="21C66",
            device_class="iPhone",
            state="ready",
            ios_category="tunnel",
            is_ready=True,
            connected_at="2024-01-01T00:00:00",
            last_seen_at="2024-01-01T00:00:00",
        )
        msg = WSDeviceUpdate(device=device)
        assert msg.type == "device_update"
        data = msg.model_dump()
        assert data["type"] == "device_update"
        assert data["device"]["udid"] == "abc"

    def test_device_disconnected(self):
        msg = WSDeviceDisconnected(udid="abc")
        assert msg.type == "device_disconnected"

    def test_simulation_progress(self):
        progress = SimulationProgressResponse(
            current_position=CoordinateModel(latitude=25.0, longitude=121.5),
            segment_index=0,
            total_segments=3,
            distance_covered_m=100.0,
            total_distance_m=500.0,
            fraction_complete=0.2,
            elapsed_time_s=10.0,
            speed_ms=1.39,
            state="running",
        )
        msg = WSSimulationProgress(udid="d1", progress=progress)
        assert msg.type == "simulation_progress"
        json_str = msg.model_dump_json()
        assert '"simulation_progress"' in json_str

    def test_simulation_complete(self):
        msg = WSSimulationComplete(udid="d1")
        assert msg.type == "simulation_complete"

    def test_simulation_error(self):
        msg = WSSimulationError(udid="d1", error="Connection lost")
        assert msg.type == "simulation_error"
        assert msg.error == "Connection lost"

    def test_heartbeat(self):
        msg = WSHeartbeat(timestamp=1000.0)
        assert msg.type == "heartbeat"
        assert msg.timestamp == 1000.0

    def test_ws_messages_serialize_to_json(self):
        """All WS messages should serialize cleanly to JSON."""
        msg = WSHeartbeat(timestamp=42.0)
        json_str = msg.model_dump_json()
        assert '"heartbeat"' in json_str
        assert '"42.0"' in json_str or "42.0" in json_str
