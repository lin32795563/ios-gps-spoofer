/**
 * REST API client for communicating with the Python backend.
 *
 * Wraps fetch() calls with proper error handling, JSON parsing,
 * and the correct base URL (obtained from Electron IPC or defaulting
 * to localhost for development).
 */

import type {
  DeviceInfo,
  DeviceListResponse,
  FavoriteListResponse,
  FavoriteLocation,
  GPXParseResult,
  LocationStatus,
  SimulationStatus,
  StartSimulationParams,
  SuccessResponse,
} from "../types/api";

// Default backend URL for development
const DEFAULT_API_URL = "http://127.0.0.1:8456";

let cachedApiUrl: string | null = null;

/**
 * Get the backend API base URL.
 * In Electron, this comes from IPC. In dev browser, it uses the default.
 */
async function getApiUrl(): Promise<string> {
  if (cachedApiUrl) return cachedApiUrl;

  if (window.electronAPI) {
    cachedApiUrl = await window.electronAPI.getApiUrl();
  } else {
    cachedApiUrl = DEFAULT_API_URL;
  }
  return cachedApiUrl;
}

/**
 * Make an HTTP request to the backend API.
 */
async function apiRequest<T>(
  method: string,
  path: string,
  body?: unknown,
): Promise<T> {
  const baseUrl = await getApiUrl();
  const url = `${baseUrl}${path}`;

  const options: RequestInit = {
    method,
    headers: { "Content-Type": "application/json" },
  };

  if (body !== undefined) {
    options.body = JSON.stringify(body);
  }

  const response = await fetch(url, options);

  let data: Record<string, unknown>;
  try {
    data = await response.json();
  } catch {
    throw new Error(`HTTP ${response.status}: non-JSON response`);
  }

  if (!response.ok) {
    const errorMsg =
      (typeof data.error === "string" && data.error) ||
      (typeof data.detail === "string" && data.detail) ||
      `HTTP ${response.status}`;
    throw new Error(errorMsg);
  }

  return data as T;
}

// ------------------------------------------------------------------
// Device API
// ------------------------------------------------------------------

export async function listDevices(): Promise<DeviceInfo[]> {
  const result = await apiRequest<DeviceListResponse>("GET", "/api/devices");
  return result.devices;
}

export async function getDevice(udid: string): Promise<DeviceInfo> {
  return apiRequest<DeviceInfo>("GET", `/api/devices/${udid}`);
}

export async function connectDevice(udid: string): Promise<SuccessResponse> {
  return apiRequest<SuccessResponse>("POST", `/api/devices/${udid}/connect`);
}

// ------------------------------------------------------------------
// Location API
// ------------------------------------------------------------------

export async function setLocation(
  udid: string,
  latitude: number,
  longitude: number,
): Promise<SuccessResponse> {
  return apiRequest<SuccessResponse>("POST", "/api/location/set", {
    udid,
    latitude,
    longitude,
  });
}

export async function clearLocation(
  udid: string,
): Promise<SuccessResponse> {
  return apiRequest<SuccessResponse>("POST", "/api/location/clear", {
    udid,
  });
}

export async function getLocationStatus(
  udid: string,
): Promise<LocationStatus> {
  return apiRequest<LocationStatus>("GET", `/api/location/${udid}`);
}

// ------------------------------------------------------------------
// Simulation API
// ------------------------------------------------------------------

export async function startSimulation(
  params: StartSimulationParams,
): Promise<SuccessResponse> {
  return apiRequest<SuccessResponse>("POST", "/api/simulation/start", params);
}

export async function pauseSimulation(
  udid: string,
): Promise<SuccessResponse> {
  return apiRequest<SuccessResponse>("POST", "/api/simulation/pause", {
    udid,
  });
}

export async function resumeSimulation(
  udid: string,
): Promise<SuccessResponse> {
  return apiRequest<SuccessResponse>("POST", "/api/simulation/resume", {
    udid,
  });
}

export async function stopSimulation(
  udid: string,
): Promise<SuccessResponse> {
  return apiRequest<SuccessResponse>("POST", "/api/simulation/stop", {
    udid,
  });
}

export async function setSimulationSpeed(
  udid: string,
  speedKmh: number,
): Promise<SuccessResponse> {
  return apiRequest<SuccessResponse>("POST", "/api/simulation/speed", {
    udid,
    speed_kmh: speedKmh,
  });
}

export async function getSimulationStatus(
  udid: string,
): Promise<SimulationStatus> {
  return apiRequest<SimulationStatus>("GET", `/api/simulation/${udid}`);
}

// ------------------------------------------------------------------
// GPX API
// ------------------------------------------------------------------

export async function parseGPX(
  gpxContent: string,
  source?: string,
): Promise<GPXParseResult> {
  return apiRequest<GPXParseResult>("POST", "/api/gpx/parse", {
    gpx_content: gpxContent,
    source: source || "<upload>",
  });
}

// ------------------------------------------------------------------
// Favorites API
// ------------------------------------------------------------------

export async function listFavorites(): Promise<FavoriteLocation[]> {
  const result = await apiRequest<FavoriteListResponse>(
    "GET",
    "/api/favorites",
  );
  return result.favorites;
}

export async function addFavorite(
  name: string,
  latitude: number,
  longitude: number,
): Promise<SuccessResponse> {
  return apiRequest<SuccessResponse>("POST", "/api/favorites", {
    name,
    latitude,
    longitude,
  });
}

export async function removeFavorite(
  index: number,
): Promise<SuccessResponse> {
  return apiRequest<SuccessResponse>("DELETE", `/api/favorites/${index}`);
}

// ------------------------------------------------------------------
// Health check
// ------------------------------------------------------------------

export async function healthCheck(): Promise<boolean> {
  try {
    const result = await apiRequest<SuccessResponse>("GET", "/api/health");
    return result.success;
  } catch {
    return false;
  }
}
