/**
 * Tests for the REST API client.
 *
 * Verifies:
 * - Correct HTTP methods and URLs for each endpoint
 * - Request body serialization
 * - Error handling (HTTP errors, non-JSON responses)
 * - API URL resolution (default and Electron IPC)
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

// We need to import the module after setting up fetch mock
let apiModule: typeof import("../services/apiClient");

// ------------------------------------------------------------------
// Fetch mock
// ------------------------------------------------------------------

interface MockFetchResponse {
  ok: boolean;
  status: number;
  json: () => Promise<unknown>;
}

let mockFetch: ReturnType<typeof vi.fn>;

beforeEach(async () => {
  // Reset module cache to clear cachedApiUrl
  vi.resetModules();

  mockFetch = vi.fn();
  vi.stubGlobal("fetch", mockFetch);

  // Clear electronAPI
  delete (window as unknown as Record<string, unknown>).electronAPI;

  // Re-import the module fresh for each test
  apiModule = await import("../services/apiClient");
});

afterEach(() => {
  vi.restoreAllMocks();
});

function mockFetchSuccess(data: unknown, status = 200): void {
  mockFetch.mockResolvedValueOnce({
    ok: status >= 200 && status < 300,
    status,
    json: () => Promise.resolve(data),
  } as MockFetchResponse);
}

function mockFetchError(error: string, detail: string, status = 400): void {
  mockFetch.mockResolvedValueOnce({
    ok: false,
    status,
    json: () => Promise.resolve({ success: false, error, detail }),
  } as MockFetchResponse);
}

function mockFetchNetworkError(): void {
  mockFetch.mockRejectedValueOnce(new TypeError("Failed to fetch"));
}

function mockFetchNonJson(status = 502): void {
  mockFetch.mockResolvedValueOnce({
    ok: false,
    status,
    json: () => Promise.reject(new SyntaxError("Unexpected token")),
  } as MockFetchResponse);
}

// ------------------------------------------------------------------
// Tests
// ------------------------------------------------------------------

describe("apiClient", () => {
  describe("healthCheck", () => {
    it("should return true when backend is healthy", async () => {
      mockFetchSuccess({ success: true });
      const result = await apiModule.healthCheck();
      expect(result).toBe(true);
    });

    it("should return false when backend is not reachable", async () => {
      mockFetchNetworkError();
      const result = await apiModule.healthCheck();
      expect(result).toBe(false);
    });

    it("should return false on non-success response", async () => {
      mockFetchError("unhealthy", "", 500);
      const result = await apiModule.healthCheck();
      expect(result).toBe(false);
    });
  });

  describe("listDevices", () => {
    it("should return device list from API", async () => {
      const devices = [
        { udid: "abc", name: "iPhone", product_version: "17.0" },
      ];
      mockFetchSuccess({ devices, count: 1 });

      const result = await apiModule.listDevices();

      expect(result).toEqual(devices);
      expect(mockFetch).toHaveBeenCalledWith(
        "http://127.0.0.1:8456/api/devices",
        expect.objectContaining({ method: "GET" }),
      );
    });
  });

  describe("getDevice", () => {
    it("should fetch a single device by UDID", async () => {
      const device = { udid: "abc", name: "iPhone" };
      mockFetchSuccess(device);

      const result = await apiModule.getDevice("abc");

      expect(result).toEqual(device);
      expect(mockFetch).toHaveBeenCalledWith(
        "http://127.0.0.1:8456/api/devices/abc",
        expect.objectContaining({ method: "GET" }),
      );
    });
  });

  describe("setLocation", () => {
    it("should POST correct body", async () => {
      mockFetchSuccess({ success: true, message: "ok" });

      await apiModule.setLocation("abc", 37.7749, -122.4194);

      expect(mockFetch).toHaveBeenCalledWith(
        "http://127.0.0.1:8456/api/location/set",
        expect.objectContaining({
          method: "POST",
          body: JSON.stringify({
            udid: "abc",
            latitude: 37.7749,
            longitude: -122.4194,
          }),
        }),
      );
    });
  });

  describe("clearLocation", () => {
    it("should POST with UDID", async () => {
      mockFetchSuccess({ success: true, message: "ok" });

      await apiModule.clearLocation("abc");

      expect(mockFetch).toHaveBeenCalledWith(
        "http://127.0.0.1:8456/api/location/clear",
        expect.objectContaining({
          method: "POST",
          body: JSON.stringify({ udid: "abc" }),
        }),
      );
    });
  });

  describe("startSimulation", () => {
    it("should POST simulation parameters", async () => {
      mockFetchSuccess({ success: true, message: "started" });

      await apiModule.startSimulation({
        udid: "abc",
        path: [
          { latitude: 37.0, longitude: -122.0 },
          { latitude: 37.1, longitude: -122.1 },
        ],
        speed_kmh: 15,
      });

      const call = mockFetch.mock.calls[0];
      expect(call[0]).toBe("http://127.0.0.1:8456/api/simulation/start");
      expect(call[1].method).toBe("POST");

      const body = JSON.parse(call[1].body);
      expect(body.udid).toBe("abc");
      expect(body.path).toHaveLength(2);
      expect(body.speed_kmh).toBe(15);
    });
  });

  describe("pauseSimulation", () => {
    it("should POST with UDID", async () => {
      mockFetchSuccess({ success: true, message: "paused" });
      await apiModule.pauseSimulation("abc");

      expect(mockFetch).toHaveBeenCalledWith(
        "http://127.0.0.1:8456/api/simulation/pause",
        expect.objectContaining({ method: "POST" }),
      );
    });
  });

  describe("resumeSimulation", () => {
    it("should POST with UDID", async () => {
      mockFetchSuccess({ success: true, message: "resumed" });
      await apiModule.resumeSimulation("abc");

      expect(mockFetch).toHaveBeenCalledWith(
        "http://127.0.0.1:8456/api/simulation/resume",
        expect.objectContaining({ method: "POST" }),
      );
    });
  });

  describe("stopSimulation", () => {
    it("should POST with UDID", async () => {
      mockFetchSuccess({ success: true, message: "stopped" });
      await apiModule.stopSimulation("abc");

      expect(mockFetch).toHaveBeenCalledWith(
        "http://127.0.0.1:8456/api/simulation/stop",
        expect.objectContaining({ method: "POST" }),
      );
    });
  });

  describe("setSimulationSpeed", () => {
    it("should POST speed in km/h", async () => {
      mockFetchSuccess({ success: true, message: "speed set" });
      await apiModule.setSimulationSpeed("abc", 60);

      const call = mockFetch.mock.calls[0];
      const body = JSON.parse(call[1].body);
      expect(body.udid).toBe("abc");
      expect(body.speed_kmh).toBe(60);
    });
  });

  describe("parseGPX", () => {
    it("should POST GPX content", async () => {
      mockFetchSuccess({
        waypoints: [{ latitude: 37.0, longitude: -122.0 }],
        count: 1,
      });

      const result = await apiModule.parseGPX("<gpx>...</gpx>", "test.gpx");

      const call = mockFetch.mock.calls[0];
      const body = JSON.parse(call[1].body);
      expect(body.gpx_content).toBe("<gpx>...</gpx>");
      expect(body.source).toBe("test.gpx");
      expect(result.waypoints).toHaveLength(1);
    });
  });

  describe("favorites", () => {
    it("should list favorites", async () => {
      const favorites = [{ name: "Home", latitude: 37.0, longitude: -122.0 }];
      mockFetchSuccess({ favorites, count: 1 });

      const result = await apiModule.listFavorites();
      expect(result).toEqual(favorites);
    });

    it("should add a favorite", async () => {
      mockFetchSuccess({ success: true, message: "added" });
      await apiModule.addFavorite("Home", 37.0, -122.0);

      const call = mockFetch.mock.calls[0];
      const body = JSON.parse(call[1].body);
      expect(body.name).toBe("Home");
      expect(body.latitude).toBe(37.0);
      expect(body.longitude).toBe(-122.0);
    });

    it("should remove a favorite by index", async () => {
      mockFetchSuccess({ success: true, message: "removed" });
      await apiModule.removeFavorite(2);

      expect(mockFetch).toHaveBeenCalledWith(
        "http://127.0.0.1:8456/api/favorites/2",
        expect.objectContaining({ method: "DELETE" }),
      );
    });
  });

  describe("error handling", () => {
    it("should throw on HTTP error with error message", async () => {
      mockFetchError("Device not found", "No device with UDID xyz", 404);

      await expect(apiModule.getDevice("xyz")).rejects.toThrow(
        "Device not found",
      );
    });

    it("should throw on non-JSON response", async () => {
      mockFetchNonJson(502);

      await expect(apiModule.listDevices()).rejects.toThrow(
        "HTTP 502: non-JSON response",
      );
    });

    it("should throw on network failure", async () => {
      mockFetchNetworkError();

      await expect(apiModule.listDevices()).rejects.toThrow("Failed to fetch");
    });
  });

  describe("API URL resolution", () => {
    it("should use Electron API URL when available", async () => {
      // Reset module again to clear cache
      vi.resetModules();
      (window as unknown as Record<string, unknown>).electronAPI = {
        getApiUrl: () => Promise.resolve("http://electron:9999"),
        getWsUrl: () => Promise.resolve("ws://electron:9999/ws"),
      };
      mockFetch = vi.fn();
      vi.stubGlobal("fetch", mockFetch);

      const freshModule = await import("../services/apiClient");
      mockFetchSuccess({ success: true });

      await freshModule.healthCheck();

      expect(mockFetch).toHaveBeenCalledWith(
        "http://electron:9999/api/health",
        expect.anything(),
      );
    });
  });
});
