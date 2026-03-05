"""Pydantic request/response models for the REST API.

All API models use Pydantic v2 ``BaseModel`` for automatic validation,
serialization, and OpenAPI schema generation.  Internal domain objects
(``Coordinate``, ``DeviceConnection``, etc.) are converted to/from these
models at the API boundary -- the domain layer never depends on Pydantic.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

# ------------------------------------------------------------------
# Shared models (used by both requests and responses)
# ------------------------------------------------------------------


class CoordinateModel(BaseModel):
    """A geographic coordinate (used in both requests and responses)."""

    latitude: float = Field(..., ge=-90.0, le=90.0)
    longitude: float = Field(..., ge=-180.0, le=180.0)


class FavoriteLocation(BaseModel):
    """A saved favorite location."""

    model_config = ConfigDict(strict=True)

    name: str = Field(..., min_length=1, max_length=200, description="Display name")
    latitude: float = Field(..., ge=-90.0, le=90.0)
    longitude: float = Field(..., ge=-180.0, le=180.0)


# ------------------------------------------------------------------
# Request models
# ------------------------------------------------------------------


class SetLocationRequest(BaseModel):
    """Request body for setting a single GPS location."""

    model_config = ConfigDict(strict=True)

    udid: str = Field(..., min_length=1, description="Device UDID")
    latitude: float = Field(..., ge=-90.0, le=90.0, description="Latitude in degrees")
    longitude: float = Field(
        ..., ge=-180.0, le=180.0, description="Longitude in degrees"
    )


class ClearLocationRequest(BaseModel):
    """Request body for clearing simulated location."""

    model_config = ConfigDict(strict=True)

    udid: str = Field(..., min_length=1, description="Device UDID")


class StartSimulationRequest(BaseModel):
    """Request body for starting a path simulation."""

    model_config = ConfigDict(strict=True)

    udid: str = Field(..., min_length=1, description="Device UDID")
    path: list[CoordinateModel] = Field(
        ..., min_length=2, description="Waypoints (at least 2)"
    )
    speed_kmh: float = Field(
        default=5.0, gt=0.0, le=1000.0, description="Speed in km/h"
    )
    drift_enabled: bool = Field(default=True, description="Enable GPS drift")
    drift_sigma_meters: float = Field(
        default=2.0, ge=0.0, le=10.0, description="Drift sigma in meters"
    )
    loop_path: bool = Field(default=False, description="Loop the path")


class SetSpeedRequest(BaseModel):
    """Request body for changing simulation speed."""

    model_config = ConfigDict(strict=True)

    udid: str = Field(..., min_length=1, description="Device UDID")
    speed_kmh: float = Field(..., gt=0.0, le=1000.0, description="Speed in km/h")


class SimulationControlRequest(BaseModel):
    """Request body for pause/resume/stop operations."""

    model_config = ConfigDict(strict=True)

    udid: str = Field(..., min_length=1, description="Device UDID")


class LoadGPXRequest(BaseModel):
    """Request body for loading a GPX file (content as string)."""

    model_config = ConfigDict(strict=True)

    gpx_content: str = Field(..., min_length=1, description="GPX XML content")
    source: str = Field(default="<upload>", description="Source name for logging")


class AddFavoriteRequest(BaseModel):
    """Request body for adding a favorite location."""

    model_config = ConfigDict(strict=True)

    name: str = Field(..., min_length=1, max_length=200, description="Display name")
    latitude: float = Field(..., ge=-90.0, le=90.0)
    longitude: float = Field(..., ge=-180.0, le=180.0)


# ------------------------------------------------------------------
# Response models
# ------------------------------------------------------------------


class DeviceInfoResponse(BaseModel):
    """Response model for a single device."""

    udid: str
    name: str
    product_type: str
    product_version: str
    build_version: str
    device_class: str
    state: str
    ios_category: str
    is_ready: bool
    error_message: str | None = None
    connected_at: str
    last_seen_at: str


class DeviceListResponse(BaseModel):
    """Response model for the device list endpoint."""

    devices: list[DeviceInfoResponse]
    count: int


class LocationStatusResponse(BaseModel):
    """Response model for location status."""

    udid: str
    simulation_active: bool
    current_location: CoordinateModel | None = None


class SimulationProgressResponse(BaseModel):
    """Response model for simulation progress."""

    current_position: CoordinateModel
    segment_index: int
    total_segments: int
    distance_covered_m: float
    total_distance_m: float
    fraction_complete: float
    elapsed_time_s: float
    speed_ms: float
    state: str


class SimulationStatusResponse(BaseModel):
    """Response model for simulation status."""

    udid: str
    state: str
    speed_kmh: float
    progress: SimulationProgressResponse | None = None


class GPXParseResponse(BaseModel):
    """Response model for GPX parsing."""

    waypoints: list[CoordinateModel]
    count: int


class FavoriteListResponse(BaseModel):
    """Response model for favorites list."""

    favorites: list[FavoriteLocation]
    count: int


class SuccessResponse(BaseModel):
    """Generic success response."""

    success: bool = True
    message: str = ""


class ErrorResponse(BaseModel):
    """Generic error response."""

    success: bool = False
    error: str
    detail: str = ""


# ------------------------------------------------------------------
# WebSocket message models
# ------------------------------------------------------------------


class WSMessage(BaseModel):
    """Base WebSocket message with type discriminator."""

    type: str


class WSDeviceUpdate(WSMessage):
    """WebSocket message: device status changed."""

    type: str = "device_update"
    device: DeviceInfoResponse


class WSDeviceDisconnected(WSMessage):
    """WebSocket message: device disconnected."""

    type: str = "device_disconnected"
    udid: str


class WSSimulationProgress(WSMessage):
    """WebSocket message: simulation progress tick."""

    type: str = "simulation_progress"
    udid: str
    progress: SimulationProgressResponse


class WSSimulationComplete(WSMessage):
    """WebSocket message: simulation finished."""

    type: str = "simulation_complete"
    udid: str


class WSSimulationError(WSMessage):
    """WebSocket message: simulation error."""

    type: str = "simulation_error"
    udid: str
    error: str


class WSHeartbeat(WSMessage):
    """WebSocket heartbeat (ping/pong)."""

    type: str = "heartbeat"
    timestamp: float
