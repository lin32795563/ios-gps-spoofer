"""FastAPI REST API routes for iOS GPS Spoofer.

All routes operate on the shared ``AppState`` obtained via dependency
injection.  Routes are organized by domain:

- ``/api/devices`` -- Device discovery and connection
- ``/api/location`` -- Single-point location setting and clearing
- ``/api/simulation`` -- Path simulation lifecycle and speed control
- ``/api/gpx`` -- GPX file parsing
- ``/api/favorites`` -- Saved favorite locations
- ``/ws`` -- WebSocket endpoint for real-time updates

Error Handling
--------------
All routes use a consistent error response format via ``ErrorResponse``.
Domain exceptions are caught and translated to appropriate HTTP status
codes (400 for client errors, 404 for not found, 500 for internal errors).
"""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse

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
    SimulationControlRequest,
    SimulationStatusResponse,
    StartSimulationRequest,
    SuccessResponse,
    WSSimulationComplete,
    WSSimulationError,
    WSSimulationProgress,
)
from ios_gps_spoofer.api.models import (
    SimulationProgressResponse as ProgressResp,
)

logger = logging.getLogger(__name__)

# Router will be mounted on the app by the server factory
router = APIRouter()


def _error_response(
    error: str,
    detail: str = "",
    status_code: int = 400,
) -> JSONResponse:
    """Create a JSON error response with the given HTTP status code.

    Args:
        error: Short error description.
        detail: Detailed error information.
        status_code: HTTP status code (default 400).

    Returns:
        A ``JSONResponse`` with the error body.
    """
    return JSONResponse(
        status_code=status_code,
        content={"success": False, "error": error, "detail": detail},
    )


# ------------------------------------------------------------------
# Dependency: get app state from the app's state attribute
# ------------------------------------------------------------------

def _get_state():
    """Import and return the app state.

    This is a module-level helper, not a FastAPI dependency, because
    the actual app state is set on the router's app at startup.
    Routes call this at the top of each handler.
    """
    # Late import to avoid circular dependency
    from ios_gps_spoofer.api.server import get_app_state

    return get_app_state()


def _get_ws_manager():
    """Import and return the WebSocket manager."""
    from ios_gps_spoofer.api.server import get_ws_manager

    return get_ws_manager()


# ------------------------------------------------------------------
# Device endpoints
# ------------------------------------------------------------------

@router.get(
    "/api/devices",
    response_model=DeviceListResponse,
    tags=["Devices"],
    summary="List connected devices",
)
async def list_devices():
    """Return all currently connected iOS devices."""
    state = _get_state()
    devices = state.device_manager.list_connected_devices()
    device_list = [
        DeviceInfoResponse(**conn.to_dict()) for conn in devices
    ]
    return DeviceListResponse(devices=device_list, count=len(device_list))


@router.get(
    "/api/devices/{udid}",
    response_model=DeviceInfoResponse,
    tags=["Devices"],
    summary="Get device info",
    responses={404: {"model": ErrorResponse}},
)
async def get_device(udid: str):
    """Return information about a specific connected device."""
    state = _get_state()
    try:
        conn = state.device_manager.get_device(udid)
        return DeviceInfoResponse(**conn.to_dict())
    except Exception as exc:
        return _error_response("Device not found", str(exc), status_code=404)


@router.post(
    "/api/devices/{udid}/connect",
    response_model=SuccessResponse,
    tags=["Devices"],
    summary="Connect to a device",
    responses={400: {"model": ErrorResponse}},
)
async def connect_device(udid: str):
    """Attempt to connect and prepare a device for location simulation."""
    state = _get_state()
    try:
        await asyncio.to_thread(state.device_manager.connect_device, udid)
        return SuccessResponse(message=f"Device {udid} connected")
    except Exception as exc:
        logger.exception("Failed to connect device %s", udid)
        return _error_response("Connection failed", str(exc))


# ------------------------------------------------------------------
# Location endpoints
# ------------------------------------------------------------------

@router.post(
    "/api/location/set",
    response_model=SuccessResponse,
    tags=["Location"],
    summary="Set simulated GPS location",
    responses={400: {"model": ErrorResponse}},
)
async def set_location(request: SetLocationRequest):
    """Set a simulated GPS location on a device."""
    state = _get_state()
    try:
        from ios_gps_spoofer.location.coordinates import Coordinate

        coord = Coordinate(
            latitude=request.latitude, longitude=request.longitude
        )
        await asyncio.to_thread(
            state.location_service.set_location, request.udid, coord
        )
        return SuccessResponse(
            message=f"Location set to ({request.latitude}, {request.longitude})"
        )
    except Exception as exc:
        logger.exception("Failed to set location on %s", request.udid)
        return _error_response("Failed to set location", str(exc))


@router.post(
    "/api/location/clear",
    response_model=SuccessResponse,
    tags=["Location"],
    summary="Clear simulated location (restore real GPS)",
    responses={400: {"model": ErrorResponse}},
)
async def clear_location(request: ClearLocationRequest):
    """Clear the simulated location and restore real GPS."""
    state = _get_state()
    try:
        # Also stop any running simulation
        state.stop_simulator(request.udid)
        await asyncio.to_thread(
            state.location_service.clear_location, request.udid
        )
        return SuccessResponse(message="Location cleared, real GPS restored")
    except Exception as exc:
        logger.exception("Failed to clear location on %s", request.udid)
        return _error_response("Failed to clear location", str(exc))


@router.get(
    "/api/location/{udid}",
    response_model=LocationStatusResponse,
    tags=["Location"],
    summary="Get current location status",
)
async def get_location_status(udid: str):
    """Get the current simulated location status for a device."""
    state = _get_state()
    status = state.location_service.get_status(udid)
    current = status.get("current_location")
    coord_model = None
    if current is not None:
        coord_model = CoordinateModel(
            latitude=current["latitude"],
            longitude=current["longitude"],
        )
    return LocationStatusResponse(
        udid=udid,
        simulation_active=bool(status.get("simulation_active", False)),
        current_location=coord_model,
    )


# ------------------------------------------------------------------
# Simulation endpoints
# ------------------------------------------------------------------

@router.post(
    "/api/simulation/start",
    response_model=SuccessResponse,
    tags=["Simulation"],
    summary="Start path simulation",
    responses={400: {"model": ErrorResponse}},
)
async def start_simulation(request: StartSimulationRequest):
    """Start a path simulation on a device."""
    state = _get_state()
    ws_manager = _get_ws_manager()

    try:
        from ios_gps_spoofer.location.coordinates import Coordinate
        from ios_gps_spoofer.simulation.path_simulator import (
            PathSimulator,
            SimulationConfig,
        )
        from ios_gps_spoofer.simulation.speed_profiles import kmh_to_ms

        # Convert path coordinates
        path = [
            Coordinate(latitude=p.latitude, longitude=p.longitude)
            for p in request.path
        ]

        # Build config
        config = SimulationConfig(
            drift_enabled=request.drift_enabled,
            drift_sigma_meters=request.drift_sigma_meters,
            loop_path=request.loop_path,
        )

        # Build callbacks that push to WebSocket
        udid = request.udid

        def on_progress(progress):
            """Callback for simulation progress -- schedule WS broadcast."""
            try:
                progress_resp = ProgressResp(
                    current_position=CoordinateModel(
                        latitude=progress.current_position.latitude,
                        longitude=progress.current_position.longitude,
                    ),
                    segment_index=progress.segment_index,
                    total_segments=progress.total_segments,
                    distance_covered_m=progress.distance_covered_m,
                    total_distance_m=progress.total_distance_m,
                    fraction_complete=progress.fraction_complete,
                    elapsed_time_s=progress.elapsed_time_s,
                    speed_ms=progress.speed_ms,
                    state=progress.state.value,
                )
                msg = WSSimulationProgress(
                    udid=udid, progress=progress_resp
                )
                _schedule_ws_broadcast_throttled(ws_manager, msg, udid)
            except Exception:
                logger.exception("Error in progress callback for %s", udid)

        def on_complete():
            """Callback for simulation completion."""
            state.unregister_simulator(udid)
            msg = WSSimulationComplete(udid=udid)
            _schedule_ws_broadcast(ws_manager, msg)
            logger.info("Simulation complete for %s", udid)

        def on_error(exc):
            """Callback for simulation error."""
            state.unregister_simulator(udid)
            msg = WSSimulationError(udid=udid, error=str(exc))
            _schedule_ws_broadcast(ws_manager, msg)
            logger.error("Simulation error for %s: %s", udid, exc)

        # Create and start simulator
        simulator = PathSimulator(
            udid=udid,
            path=path,
            location_service=state.location_service,
            config=config,
            on_progress=on_progress,
            on_complete=on_complete,
            on_error=on_error,
        )
        simulator.speed_controller.set_speed_ms(kmh_to_ms(request.speed_kmh))

        state.register_simulator(udid, simulator)
        simulator.start()

        return SuccessResponse(
            message=f"Simulation started with {len(path)} waypoints"
        )
    except Exception as exc:
        logger.exception("Failed to start simulation for %s", request.udid)
        return _error_response("Failed to start simulation", str(exc))


@router.post(
    "/api/simulation/pause",
    response_model=SuccessResponse,
    tags=["Simulation"],
    summary="Pause simulation",
    responses={400: {"model": ErrorResponse}},
)
async def pause_simulation(request: SimulationControlRequest):
    """Pause the active simulation on a device."""
    state = _get_state()
    simulator = state.get_simulator(request.udid)
    if simulator is None:
        return _error_response(
            "No active simulation",
            f"No simulation running for device {request.udid}",
        )
    try:
        simulator.pause()
        return SuccessResponse(message="Simulation paused")
    except Exception as exc:
        return _error_response("Failed to pause", str(exc))


@router.post(
    "/api/simulation/resume",
    response_model=SuccessResponse,
    tags=["Simulation"],
    summary="Resume simulation",
    responses={400: {"model": ErrorResponse}},
)
async def resume_simulation(request: SimulationControlRequest):
    """Resume a paused simulation on a device."""
    state = _get_state()
    simulator = state.get_simulator(request.udid)
    if simulator is None:
        return _error_response(
            "No active simulation",
            f"No simulation running for device {request.udid}",
        )
    try:
        simulator.resume()
        return SuccessResponse(message="Simulation resumed")
    except Exception as exc:
        return _error_response("Failed to resume", str(exc))


@router.post(
    "/api/simulation/stop",
    response_model=SuccessResponse,
    tags=["Simulation"],
    summary="Stop simulation",
    responses={400: {"model": ErrorResponse}},
)
async def stop_simulation(request: SimulationControlRequest):
    """Stop the active simulation on a device."""
    state = _get_state()
    stopped = state.stop_simulator(request.udid)
    if not stopped:
        return _error_response(
            "No active simulation",
            f"No simulation running for device {request.udid}",
        )
    return SuccessResponse(message="Simulation stopped")


@router.post(
    "/api/simulation/speed",
    response_model=SuccessResponse,
    tags=["Simulation"],
    summary="Change simulation speed",
    responses={400: {"model": ErrorResponse}},
)
async def set_speed(request: SetSpeedRequest):
    """Change the speed of a running simulation."""
    state = _get_state()
    simulator = state.get_simulator(request.udid)
    if simulator is None:
        return _error_response(
            "No active simulation",
            f"No simulation running for device {request.udid}",
        )
    try:
        from ios_gps_spoofer.simulation.speed_profiles import kmh_to_ms

        simulator.speed_controller.set_speed_ms(kmh_to_ms(request.speed_kmh))
        return SuccessResponse(
            message=f"Speed set to {request.speed_kmh} km/h"
        )
    except Exception as exc:
        return _error_response("Failed to set speed", str(exc))


@router.get(
    "/api/simulation/{udid}",
    response_model=SimulationStatusResponse | ErrorResponse,
    tags=["Simulation"],
    summary="Get simulation status",
)
async def get_simulation_status(udid: str):
    """Get the current simulation status for a device."""
    state = _get_state()
    status = state.get_simulator_status(udid)
    if status is None:
        return SimulationStatusResponse(
            udid=udid,
            state="idle",
            speed_kmh=0.0,
            progress=None,
        )
    return SimulationStatusResponse(
        udid=str(status["udid"]),
        state=str(status["state"]),
        speed_kmh=float(status["speed_kmh"]),
        progress=None,
    )


# ------------------------------------------------------------------
# GPX endpoints
# ------------------------------------------------------------------

@router.post(
    "/api/gpx/parse",
    response_model=GPXParseResponse,
    tags=["GPX"],
    summary="Parse GPX content",
    responses={400: {"model": ErrorResponse}},
)
async def parse_gpx(request: LoadGPXRequest):
    """Parse GPX XML content and return waypoints."""
    try:
        from ios_gps_spoofer.simulation.gpx_parser import parse_gpx_string

        coordinates = await asyncio.to_thread(
            parse_gpx_string, request.gpx_content, request.source
        )
        waypoints = [
            CoordinateModel(latitude=c.latitude, longitude=c.longitude)
            for c in coordinates
        ]
        return GPXParseResponse(waypoints=waypoints, count=len(waypoints))
    except Exception as exc:
        logger.exception("Failed to parse GPX")
        return _error_response("GPX parse failed", str(exc))


# ------------------------------------------------------------------
# Favorites endpoints
# ------------------------------------------------------------------

@router.get(
    "/api/favorites",
    response_model=FavoriteListResponse,
    tags=["Favorites"],
    summary="List favorite locations",
)
async def list_favorites():
    """Return all saved favorite locations."""
    state = _get_state()
    favorites = state.get_favorites()
    return FavoriteListResponse(favorites=favorites, count=len(favorites))


@router.post(
    "/api/favorites",
    response_model=SuccessResponse,
    tags=["Favorites"],
    summary="Add a favorite location",
)
async def add_favorite(request: AddFavoriteRequest):
    """Add a new favorite location."""
    state = _get_state()
    favorite = FavoriteLocation(
        name=request.name,
        latitude=request.latitude,
        longitude=request.longitude,
    )
    state.add_favorite(favorite)
    return SuccessResponse(message=f"Favorite '{request.name}' added")


@router.delete(
    "/api/favorites/{index}",
    response_model=SuccessResponse,
    tags=["Favorites"],
    summary="Remove a favorite location",
    responses={404: {"model": ErrorResponse}},
)
async def remove_favorite(index: int):
    """Remove a favorite location by index."""
    state = _get_state()
    removed = state.remove_favorite(index)
    if removed is None:
        return _error_response(
            "Favorite not found",
            f"No favorite at index {index}",
            status_code=404,
        )
    return SuccessResponse(message=f"Favorite '{removed.name}' removed")


# ------------------------------------------------------------------
# Health check
# ------------------------------------------------------------------

@router.get(
    "/api/health",
    response_model=SuccessResponse,
    tags=["System"],
    summary="Health check",
)
async def health_check():
    """Simple health check endpoint."""
    return SuccessResponse(success=True, message="OK")


# ------------------------------------------------------------------
# WebSocket endpoint
# ------------------------------------------------------------------

@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time updates.

    The server pushes device status changes and simulation progress
    to all connected WebSocket clients.  Clients can send:
    - ``{"type": "pong"}`` -- heartbeat response
    - ``{"type": "ping"}`` -- explicit ping request
    """
    ws_manager = _get_ws_manager()
    await ws_manager.connect(websocket)

    try:
        while True:
            try:
                data = await websocket.receive_json()
                msg_type = data.get("type", "")

                if msg_type == "pong":
                    ws_manager.record_pong(websocket)
                elif msg_type == "ping":
                    import time as _time

                    from ios_gps_spoofer.api.models import WSHeartbeat

                    await websocket.send_text(
                        WSHeartbeat(timestamp=_time.time()).model_dump_json()
                    )
                else:
                    logger.debug("Unknown WS message type: %s", msg_type)
            except WebSocketDisconnect:
                break
            except Exception:
                logger.exception("Error processing WebSocket message")
                break
    finally:
        ws_manager.disconnect(websocket)


# ------------------------------------------------------------------
# Helpers for scheduling WebSocket broadcasts from sync callbacks
# ------------------------------------------------------------------

def _schedule_ws_broadcast(ws_manager, message):
    """Schedule a WebSocket broadcast from a synchronous context.

    The simulation callbacks run on the simulator thread, so we use
    the server's stored event loop reference to schedule the async
    broadcast via ``call_soon_threadsafe``.

    Args:
        ws_manager: The WebSocket manager.
        message: The Pydantic model to broadcast.
    """
    try:
        from ios_gps_spoofer.api.server import get_event_loop

        loop = get_event_loop()
        if loop is not None and loop.is_running():
            loop.call_soon_threadsafe(
                asyncio.ensure_future,
                ws_manager.broadcast(message),
            )
    except Exception:
        logger.debug("Could not schedule WS broadcast: no event loop available")


def _schedule_ws_broadcast_throttled(ws_manager, message, throttle_key):
    """Schedule a throttled WebSocket broadcast from a synchronous context.

    Args:
        ws_manager: The WebSocket manager.
        message: The Pydantic model to broadcast.
        throttle_key: Key for throttling (device UDID).
    """
    try:
        from ios_gps_spoofer.api.server import get_event_loop

        loop = get_event_loop()
        if loop is not None and loop.is_running():
            loop.call_soon_threadsafe(
                asyncio.ensure_future,
                ws_manager.broadcast_throttled(message, throttle_key),
            )
    except Exception:
        logger.debug("Could not schedule throttled WS broadcast")
