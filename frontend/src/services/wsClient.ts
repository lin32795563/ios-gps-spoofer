/**
 * WebSocket client for real-time updates from the backend.
 *
 * Features:
 * - Automatic reconnection with exponential backoff
 * - Heartbeat pong responses
 * - Typed message dispatching via callbacks
 * - Clean disconnect on unmount
 */

import type {
  WSDeviceDisconnected,
  WSDeviceUpdate,
  WSMessage,
  WSSimulationComplete,
  WSSimulationError,
  WSSimulationProgress,
} from "../types/api";

const DEFAULT_WS_URL = "ws://127.0.0.1:8456/ws";
const RECONNECT_BASE_DELAY_MS = 1000;
const RECONNECT_MAX_DELAY_MS = 30000;
const RECONNECT_BACKOFF_FACTOR = 2;

export interface WSCallbacks {
  onDeviceUpdate?: (msg: WSDeviceUpdate) => void;
  onDeviceDisconnected?: (msg: WSDeviceDisconnected) => void;
  onSimulationProgress?: (msg: WSSimulationProgress) => void;
  onSimulationComplete?: (msg: WSSimulationComplete) => void;
  onSimulationError?: (msg: WSSimulationError) => void;
  onConnectionChange?: (connected: boolean) => void;
}

export class WebSocketClient {
  private ws: WebSocket | null = null;
  private wsUrl: string;
  private callbacks: WSCallbacks;
  private reconnectDelay: number = RECONNECT_BASE_DELAY_MS;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private isClosed: boolean = false;

  constructor(callbacks: WSCallbacks, wsUrl?: string) {
    this.callbacks = callbacks;
    this.wsUrl = wsUrl || DEFAULT_WS_URL;
  }

  /**
   * Connect to the WebSocket server.
   */
  connect(): void {
    if (this.isClosed) return;
    if (this.ws?.readyState === WebSocket.OPEN) return;

    try {
      this.ws = new WebSocket(this.wsUrl);

      this.ws.onopen = () => {
        console.log("WebSocket connected");
        this.reconnectDelay = RECONNECT_BASE_DELAY_MS;
        this.callbacks.onConnectionChange?.(true);
      };

      this.ws.onmessage = (event: MessageEvent) => {
        this.handleMessage(event.data);
      };

      this.ws.onclose = () => {
        console.log("WebSocket disconnected");
        this.callbacks.onConnectionChange?.(false);
        this.scheduleReconnect();
      };

      this.ws.onerror = (error: Event) => {
        console.error("WebSocket error:", error);
      };
    } catch (error) {
      console.error("Failed to create WebSocket:", error);
      this.scheduleReconnect();
    }
  }

  /**
   * Disconnect and stop reconnection attempts.
   */
  disconnect(): void {
    this.isClosed = true;
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    if (this.ws) {
      this.ws.onclose = null; // prevent reconnect
      this.ws.close();
      this.ws = null;
    }
  }

  /**
   * Update the WebSocket URL (e.g., from Electron IPC).
   */
  setUrl(url: string): void {
    this.wsUrl = url;
  }

  /**
   * Whether the WebSocket is currently connected.
   */
  get isConnected(): boolean {
    return this.ws?.readyState === WebSocket.OPEN;
  }

  // ------------------------------------------------------------------
  // Internal
  // ------------------------------------------------------------------

  private handleMessage(raw: string): void {
    try {
      const msg: WSMessage = JSON.parse(raw);

      switch (msg.type) {
        case "device_update":
          this.callbacks.onDeviceUpdate?.(msg as WSDeviceUpdate);
          break;
        case "device_disconnected":
          this.callbacks.onDeviceDisconnected?.(msg as WSDeviceDisconnected);
          break;
        case "simulation_progress":
          this.callbacks.onSimulationProgress?.(msg as WSSimulationProgress);
          break;
        case "simulation_complete":
          this.callbacks.onSimulationComplete?.(msg as WSSimulationComplete);
          break;
        case "simulation_error":
          this.callbacks.onSimulationError?.(msg as WSSimulationError);
          break;
        case "heartbeat":
          this.handleHeartbeat();
          break;
        default:
          console.debug("Unknown WS message type:", (msg as { type: string }).type);
      }
    } catch (error) {
      console.error("Failed to parse WS message:", error);
    }
  }

  private handleHeartbeat(): void {
    // Respond with pong
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({ type: "pong" }));
    }
  }

  private scheduleReconnect(): void {
    if (this.isClosed) return;

    console.log(`Reconnecting in ${this.reconnectDelay}ms...`);
    this.reconnectTimer = setTimeout(() => {
      this.connect();
    }, this.reconnectDelay);

    // Exponential backoff
    this.reconnectDelay = Math.min(
      this.reconnectDelay * RECONNECT_BACKOFF_FACTOR,
      RECONNECT_MAX_DELAY_MS,
    );
  }
}
