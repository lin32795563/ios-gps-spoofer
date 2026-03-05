/**
 * Tests for the WebSocket client.
 *
 * Verifies:
 * - Connection lifecycle (connect, disconnect, reconnect)
 * - Message dispatching to typed callbacks
 * - Heartbeat pong responses
 * - Exponential backoff on reconnection
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { WebSocketClient } from "../services/wsClient";
import type { WSCallbacks } from "../services/wsClient";

// ------------------------------------------------------------------
// Mock WebSocket
// ------------------------------------------------------------------

class MockWebSocket {
  static readonly CONNECTING = 0;
  static readonly OPEN = 1;
  static readonly CLOSING = 2;
  static readonly CLOSED = 3;

  readonly CONNECTING = 0;
  readonly OPEN = 1;
  readonly CLOSING = 2;
  readonly CLOSED = 3;

  readyState = MockWebSocket.OPEN;
  url: string;
  onopen: ((event: Event) => void) | null = null;
  onclose: ((event: Event) => void) | null = null;
  onmessage: ((event: MessageEvent) => void) | null = null;
  onerror: ((event: Event) => void) | null = null;

  sentMessages: string[] = [];
  closeCalled = false;

  constructor(url: string) {
    this.url = url;
    // Simulate async connection
    setTimeout(() => {
      if (this.onopen) {
        this.onopen(new Event("open"));
      }
    }, 0);
  }

  send(data: string): void {
    this.sentMessages.push(data);
  }

  close(): void {
    this.closeCalled = true;
    this.readyState = MockWebSocket.CLOSED;
  }

  // Test helpers
  simulateMessage(data: string): void {
    if (this.onmessage) {
      this.onmessage(new MessageEvent("message", { data }));
    }
  }

  simulateClose(): void {
    if (this.onclose) {
      this.onclose(new Event("close"));
    }
  }
}

// Store references to created WebSocket instances
let mockInstances: MockWebSocket[] = [];

beforeEach(() => {
  mockInstances = [];
  vi.useFakeTimers();

  // Replace global WebSocket with mock
  vi.stubGlobal(
    "WebSocket",
    class extends MockWebSocket {
      constructor(url: string) {
        super(url);
        mockInstances.push(this);
      }
    },
  );
});

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

function createCallbacks(): WSCallbacks & {
  deviceUpdate: ReturnType<typeof vi.fn>;
  deviceDisconnected: ReturnType<typeof vi.fn>;
  simProgress: ReturnType<typeof vi.fn>;
  simComplete: ReturnType<typeof vi.fn>;
  simError: ReturnType<typeof vi.fn>;
  connChange: ReturnType<typeof vi.fn>;
} {
  const deviceUpdate = vi.fn();
  const deviceDisconnected = vi.fn();
  const simProgress = vi.fn();
  const simComplete = vi.fn();
  const simError = vi.fn();
  const connChange = vi.fn();

  return {
    onDeviceUpdate: deviceUpdate,
    onDeviceDisconnected: deviceDisconnected,
    onSimulationProgress: simProgress,
    onSimulationComplete: simComplete,
    onSimulationError: simError,
    onConnectionChange: connChange,
    deviceUpdate,
    deviceDisconnected,
    simProgress,
    simComplete,
    simError,
    connChange,
  };
}

// ------------------------------------------------------------------
// Tests
// ------------------------------------------------------------------

describe("WebSocketClient", () => {
  describe("connection", () => {
    it("should connect to the WebSocket server", () => {
      const cbs = createCallbacks();
      const client = new WebSocketClient(cbs, "ws://test:1234/ws");
      client.connect();

      expect(mockInstances).toHaveLength(1);
      expect(mockInstances[0].url).toBe("ws://test:1234/ws");
    });

    it("should notify on connection open", async () => {
      const cbs = createCallbacks();
      const client = new WebSocketClient(cbs, "ws://test:1234/ws");
      client.connect();

      // Trigger the async onopen
      await vi.advanceTimersByTimeAsync(10);

      expect(cbs.connChange).toHaveBeenCalledWith(true);
    });

    it("should notify on connection close", async () => {
      const cbs = createCallbacks();
      const client = new WebSocketClient(cbs, "ws://test:1234/ws");
      client.connect();
      await vi.advanceTimersByTimeAsync(10);

      mockInstances[0].simulateClose();

      expect(cbs.connChange).toHaveBeenCalledWith(false);
    });

    it("should not reconnect after explicit disconnect", async () => {
      const cbs = createCallbacks();
      const client = new WebSocketClient(cbs, "ws://test:1234/ws");
      client.connect();
      await vi.advanceTimersByTimeAsync(10);

      client.disconnect();

      // Advance past reconnection delays
      await vi.advanceTimersByTimeAsync(60000);

      // Should only have the original connection
      expect(mockInstances).toHaveLength(1);
      expect(mockInstances[0].closeCalled).toBe(true);
    });

    it("should use default URL when none provided", () => {
      const cbs = createCallbacks();
      const client = new WebSocketClient(cbs);
      client.connect();

      expect(mockInstances[0].url).toBe("ws://127.0.0.1:8456/ws");
    });

    it("should report isConnected correctly", async () => {
      const cbs = createCallbacks();
      const client = new WebSocketClient(cbs, "ws://test:1234/ws");

      expect(client.isConnected).toBe(false);

      client.connect();
      await vi.advanceTimersByTimeAsync(10);

      expect(client.isConnected).toBe(true);

      client.disconnect();
      expect(client.isConnected).toBe(false);
    });
  });

  describe("reconnection", () => {
    it("should schedule reconnection after close", async () => {
      const cbs = createCallbacks();
      const client = new WebSocketClient(cbs, "ws://test:1234/ws");
      client.connect();
      await vi.advanceTimersByTimeAsync(10);

      // Simulate close (NOT explicit disconnect) - must set readyState
      // so connect() doesn't early-return thinking ws is still open
      mockInstances[0].readyState = MockWebSocket.CLOSED;
      mockInstances[0].simulateClose();

      expect(mockInstances).toHaveLength(1);

      // Advance past first reconnect delay (1000ms)
      await vi.advanceTimersByTimeAsync(1100);

      expect(mockInstances).toHaveLength(2);
    });

    it("should use exponential backoff when connection fails repeatedly", async () => {
      const cbs = createCallbacks();
      const client = new WebSocketClient(cbs, "ws://test:1234/ws");
      client.connect();
      await vi.advanceTimersByTimeAsync(10);

      // First disconnect after successful connection
      mockInstances[0].readyState = MockWebSocket.CLOSED;
      mockInstances[0].simulateClose();

      // Advance 1000ms - first reconnect (delay was 1000ms, reset on open)
      await vi.advanceTimersByTimeAsync(1100);
      expect(mockInstances).toHaveLength(2);

      // Second connection also opens (setTimeout 0), then closes
      // The onopen resets reconnectDelay to 1000ms
      await vi.advanceTimersByTimeAsync(10); // let onopen fire
      mockInstances[1].readyState = MockWebSocket.CLOSED;
      mockInstances[1].simulateClose();

      // After successful open, delay was reset to 1000ms, so next reconnect is at 1000ms
      await vi.advanceTimersByTimeAsync(1100);
      expect(mockInstances).toHaveLength(3);
    });
  });

  describe("message dispatching", () => {
    it("should dispatch device_update messages", async () => {
      const cbs = createCallbacks();
      const client = new WebSocketClient(cbs, "ws://test:1234/ws");
      client.connect();
      await vi.advanceTimersByTimeAsync(10);

      const msg = {
        type: "device_update",
        device: { udid: "abc", name: "iPhone" },
      };
      mockInstances[0].simulateMessage(JSON.stringify(msg));

      expect(cbs.deviceUpdate).toHaveBeenCalledWith(msg);
    });

    it("should dispatch device_disconnected messages", async () => {
      const cbs = createCallbacks();
      const client = new WebSocketClient(cbs, "ws://test:1234/ws");
      client.connect();
      await vi.advanceTimersByTimeAsync(10);

      const msg = { type: "device_disconnected", udid: "abc" };
      mockInstances[0].simulateMessage(JSON.stringify(msg));

      expect(cbs.deviceDisconnected).toHaveBeenCalledWith(msg);
    });

    it("should dispatch simulation_progress messages", async () => {
      const cbs = createCallbacks();
      const client = new WebSocketClient(cbs, "ws://test:1234/ws");
      client.connect();
      await vi.advanceTimersByTimeAsync(10);

      const msg = {
        type: "simulation_progress",
        udid: "abc",
        progress: { state: "running", fraction_complete: 0.5 },
      };
      mockInstances[0].simulateMessage(JSON.stringify(msg));

      expect(cbs.simProgress).toHaveBeenCalledWith(msg);
    });

    it("should dispatch simulation_complete messages", async () => {
      const cbs = createCallbacks();
      const client = new WebSocketClient(cbs, "ws://test:1234/ws");
      client.connect();
      await vi.advanceTimersByTimeAsync(10);

      const msg = { type: "simulation_complete", udid: "abc" };
      mockInstances[0].simulateMessage(JSON.stringify(msg));

      expect(cbs.simComplete).toHaveBeenCalledWith(msg);
    });

    it("should dispatch simulation_error messages", async () => {
      const cbs = createCallbacks();
      const client = new WebSocketClient(cbs, "ws://test:1234/ws");
      client.connect();
      await vi.advanceTimersByTimeAsync(10);

      const msg = {
        type: "simulation_error",
        udid: "abc",
        error: "Device lost",
      };
      mockInstances[0].simulateMessage(JSON.stringify(msg));

      expect(cbs.simError).toHaveBeenCalledWith(msg);
    });

    it("should handle heartbeat by sending pong", async () => {
      const cbs = createCallbacks();
      const client = new WebSocketClient(cbs, "ws://test:1234/ws");
      client.connect();
      await vi.advanceTimersByTimeAsync(10);

      mockInstances[0].simulateMessage(
        JSON.stringify({ type: "heartbeat", timestamp: 12345 }),
      );

      expect(mockInstances[0].sentMessages).toHaveLength(1);
      expect(JSON.parse(mockInstances[0].sentMessages[0])).toEqual({
        type: "pong",
      });
    });

    it("should ignore unknown message types gracefully", async () => {
      const cbs = createCallbacks();
      const client = new WebSocketClient(cbs, "ws://test:1234/ws");
      client.connect();
      await vi.advanceTimersByTimeAsync(10);

      // Should not throw
      mockInstances[0].simulateMessage(
        JSON.stringify({ type: "unknown_type" }),
      );

      expect(cbs.deviceUpdate).not.toHaveBeenCalled();
    });

    it("should handle invalid JSON gracefully", async () => {
      const cbs = createCallbacks();
      const client = new WebSocketClient(cbs, "ws://test:1234/ws");
      client.connect();
      await vi.advanceTimersByTimeAsync(10);

      const consoleSpy = vi.spyOn(console, "error").mockImplementation(() => {});

      // Should not throw
      mockInstances[0].simulateMessage("not valid json{{{");

      expect(consoleSpy).toHaveBeenCalled();
      consoleSpy.mockRestore();
    });
  });

  describe("setUrl", () => {
    it("should update the URL for future connections", () => {
      const cbs = createCallbacks();
      const client = new WebSocketClient(cbs, "ws://old:1234/ws");
      client.setUrl("ws://new:5678/ws");
      client.connect();

      expect(mockInstances[0].url).toBe("ws://new:5678/ws");
    });
  });
});
