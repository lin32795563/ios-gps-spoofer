/**
 * TypeScript type definitions matching the backend API models.
 *
 * These types mirror the Pydantic models in api/models.py.
 * Keep them in sync when the backend API changes.
 */

// ------------------------------------------------------------------
// Coordinates
// ------------------------------------------------------------------

export interface Coordinate {
  latitude: number;
  longitude: number;
}

// ------------------------------------------------------------------
// Device
// ------------------------------------------------------------------

export interface DeviceInfo {
  udid: string;
  name: string;
  product_type: string;
  product_version: string;
  build_version: string;
  device_class: string;
  state: string;
  ios_category: string;
  is_ready: boolean;
  error_message: string | null;
  connected_at: string;
  last_seen_at: string;
}

export interface DeviceListResponse {
  devices: DeviceInfo[];
  count: number;
}

// ------------------------------------------------------------------
// Location
// ------------------------------------------------------------------

export interface LocationStatus {
  udid: string;
  simulation_active: boolean;
  current_location: Coordinate | null;
}

// ------------------------------------------------------------------
// Simulation
// ------------------------------------------------------------------

export interface SimulationProgress {
  current_position: Coordinate;
  segment_index: number;
  total_segments: number;
  distance_covered_m: number;
  total_distance_m: number;
  fraction_complete: number;
  elapsed_time_s: number;
  speed_ms: number;
  state: string;
}

export interface SimulationStatus {
  udid: string;
  state: string;
  speed_kmh: number;
  progress: SimulationProgress | null;
}

export interface StartSimulationParams {
  udid: string;
  path: Coordinate[];
  speed_kmh?: number;
  drift_enabled?: boolean;
  drift_sigma_meters?: number;
  loop_path?: boolean;
}

// ------------------------------------------------------------------
// GPX
// ------------------------------------------------------------------

export interface GPXParseResult {
  waypoints: Coordinate[];
  count: number;
}

// ------------------------------------------------------------------
// Favorites
// ------------------------------------------------------------------

export interface FavoriteLocation {
  name: string;
  latitude: number;
  longitude: number;
}

export interface FavoriteListResponse {
  favorites: FavoriteLocation[];
  count: number;
}

// ------------------------------------------------------------------
// Generic responses
// ------------------------------------------------------------------

export interface SuccessResponse {
  success: boolean;
  message: string;
}

export interface ErrorResponse {
  success: false;
  error: string;
  detail: string;
}

export type ApiResponse = SuccessResponse | ErrorResponse;

// ------------------------------------------------------------------
// WebSocket messages
// ------------------------------------------------------------------

export interface WSDeviceUpdate {
  type: "device_update";
  device: DeviceInfo;
}

export interface WSDeviceDisconnected {
  type: "device_disconnected";
  udid: string;
}

export interface WSSimulationProgress {
  type: "simulation_progress";
  udid: string;
  progress: SimulationProgress;
}

export interface WSSimulationComplete {
  type: "simulation_complete";
  udid: string;
}

export interface WSSimulationError {
  type: "simulation_error";
  udid: string;
  error: string;
}

export interface WSHeartbeat {
  type: "heartbeat";
  timestamp: number;
}

export type WSMessage =
  | WSDeviceUpdate
  | WSDeviceDisconnected
  | WSSimulationProgress
  | WSSimulationComplete
  | WSSimulationError
  | WSHeartbeat;

// ------------------------------------------------------------------
// Electron API (exposed via preload)
// ------------------------------------------------------------------

export interface ElectronAPI {
  getApiUrl: () => Promise<string>;
  getWsUrl: () => Promise<string>;
}

declare global {
  interface Window {
    electronAPI?: ElectronAPI;
  }
}
