/**
 * Main application component.
 *
 * Layout: Left sidebar (device panel, controls) + Right map area.
 * Manages global state: devices, selected devices (multi-select), simulation status.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { DevicePanel } from "./components/DevicePanel";
import { ControlPanel } from "./components/ControlPanel";
import { MapView } from "./components/MapView";
import { StatusBar } from "./components/StatusBar";
import { ToastContainer } from "./components/Toast";
import { useToast } from "./hooks/useToast";
import * as api from "./services/apiClient";
import { WebSocketClient } from "./services/wsClient";
import type {
  Coordinate,
  DeviceInfo,
  DeviceSessionState,
  FavoriteLocation,
  SimStateLabel,
} from "./types/api";
import { createDefaultSession } from "./types/api";
import "./App.css";

function App() {
  // Device state
  const [devices, setDevices] = useState<DeviceInfo[]>([]);
  const [selectedUdids, setSelectedUdids] = useState<Set<string>>(new Set());

  // Per-device session state
  const [deviceSessions, setDeviceSessions] = useState<Map<string, DeviceSessionState>>(new Map());

  // Picked location (shared across devices -- user picks on map)
  const [pickedLocation, setPickedLocation] = useState<Coordinate | null>(null);

  // Favorites
  const [favorites, setFavorites] = useState<FavoriteLocation[]>([]);

  // Connection state
  const [wsConnected, setWsConnected] = useState(false);
  const [backendReady, setBackendReady] = useState(false);

  // Toast notifications
  const { toasts, showError, removeToast } = useToast();

  // WebSocket client ref
  const wsClientRef = useRef<WebSocketClient | null>(null);

  // Poll interval ref (to stop polling when WS is connected)
  const pollIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // ------------------------------------------------------------------
  // Helper: update a single device session
  // ------------------------------------------------------------------

  const updateSession = useCallback((udid: string, patch: Partial<DeviceSessionState>) => {
    setDeviceSessions(prev => {
      const session = prev.get(udid) ?? createDefaultSession();
      return new Map(prev).set(udid, { ...session, ...patch });
    });
  }, []);

  // ------------------------------------------------------------------
  // Derived: get the "active" session (first selected device)
  // ------------------------------------------------------------------

  const firstSelectedUdid = selectedUdids.size > 0 ? Array.from(selectedUdids)[0] : null;
  const activeSession = firstSelectedUdid ? (deviceSessions.get(firstSelectedUdid) ?? createDefaultSession()) : null;

  // ------------------------------------------------------------------
  // Aggregate sim state for StatusBar
  // ------------------------------------------------------------------

  const aggregateSimState: SimStateLabel = useMemo(() => {
    if (selectedUdids.size === 0) return "idle";
    const states = Array.from(selectedUdids).map(udid => {
      const s = deviceSessions.get(udid);
      return s ? s.simState : "idle";
    });
    if (states.includes("running")) return "running";
    if (states.includes("paused")) return "paused";
    if (states.includes("error")) return "error";
    if (states.includes("completed")) return "completed";
    return "idle";
  }, [selectedUdids, deviceSessions]);

  // ------------------------------------------------------------------
  // Compute device locations for MapView
  // ------------------------------------------------------------------

  const deviceLocations = useMemo(() => {
    const locations = new Map<string, { coordinate: Coordinate; isSelected: boolean; name: string }>();
    for (const device of devices) {
      const session = deviceSessions.get(device.udid);
      if (session?.currentLocation) {
        locations.set(device.udid, {
          coordinate: session.currentLocation,
          isSelected: selectedUdids.has(device.udid),
          name: device.name || device.udid.slice(-8),
        });
      }
    }
    return locations;
  }, [devices, deviceSessions, selectedUdids]);

  // ------------------------------------------------------------------
  // Initialize WebSocket and poll devices
  // ------------------------------------------------------------------

  useEffect(() => {
    // Helper: start device polling (used as fallback when WS is disconnected)
    const startPolling = () => {
      if (pollIntervalRef.current !== null) return; // already polling
      pollIntervalRef.current = setInterval(async () => {
        try {
          const deviceList = await api.listDevices();
          setDevices(deviceList);
        } catch {
          // ignore polling errors
        }
      }, 5000);
    };

    const stopPolling = () => {
      if (pollIntervalRef.current !== null) {
        clearInterval(pollIntervalRef.current);
        pollIntervalRef.current = null;
      }
    };

    // Check backend health
    const checkHealth = async () => {
      const healthy = await api.healthCheck();
      setBackendReady(healthy);
      if (healthy) {
        // Load initial data
        try {
          const deviceList = await api.listDevices();
          setDevices(deviceList);
        } catch (err) {
          console.error("Failed to load devices:", err);
          showError("無法載入裝置清單");
        }
        try {
          const favList = await api.listFavorites();
          setFavorites(favList);
        } catch (err) {
          console.error("Failed to load favorites:", err);
          showError("無法載入收藏地點");
        }
      }
    };
    checkHealth();

    // Set up WebSocket
    const getWsUrl = async (): Promise<string> => {
      if (window.electronAPI) {
        return window.electronAPI.getWsUrl();
      }
      return "ws://127.0.0.1:8456/ws";
    };

    const setupWs = async () => {
      const wsUrl = await getWsUrl();
      const client = new WebSocketClient(
        {
          onDeviceUpdate: (msg) => {
            setDevices((prev) => {
              const idx = prev.findIndex((d) => d.udid === msg.device.udid);
              if (idx >= 0) {
                const updated = [...prev];
                updated[idx] = msg.device;
                return updated;
              }
              return [...prev, msg.device];
            });
          },
          onDeviceDisconnected: (msg) => {
            setDevices((prev) => prev.filter((d) => d.udid !== msg.udid));
            // Remove from selected and clear session
            setSelectedUdids((prev) => {
              if (!prev.has(msg.udid)) return prev;
              const next = new Set(prev);
              next.delete(msg.udid);
              return next;
            });
            setDeviceSessions((prev) => {
              if (!prev.has(msg.udid)) return prev;
              const next = new Map(prev);
              next.delete(msg.udid);
              return next;
            });
          },
          onSimulationProgress: (msg) => {
            setDeviceSessions((prev) => {
              const session = prev.get(msg.udid) ?? createDefaultSession();
              return new Map(prev).set(msg.udid, {
                ...session,
                simState: msg.progress.state as SimStateLabel,
                simProgress: msg.progress,
                currentLocation: msg.progress.current_position,
              });
            });
          },
          onSimulationComplete: (msg) => {
            setDeviceSessions((prev) => {
              const session = prev.get(msg.udid) ?? createDefaultSession();
              return new Map(prev).set(msg.udid, {
                ...session,
                simState: "completed",
                simProgress: null,
              });
            });
          },
          onSimulationError: (msg) => {
            setDeviceSessions((prev) => {
              const session = prev.get(msg.udid) ?? createDefaultSession();
              return new Map(prev).set(msg.udid, {
                ...session,
                simState: "error",
              });
            });
            console.error(`Simulation error for ${msg.udid}: ${msg.error}`);
            showError(`模擬錯誤 (${msg.udid.slice(-8)}): ${msg.error}`);
          },
          onConnectionChange: (connected) => {
            setWsConnected(connected);
            if (connected) {
              stopPolling();
            } else {
              startPolling();
            }
          },
        },
        wsUrl,
      );
      client.connect();
      wsClientRef.current = client;
    };
    setupWs();

    // Start polling as fallback until WS connects
    startPolling();

    return () => {
      stopPolling();
      wsClientRef.current?.disconnect();
    };
  // showError is stable (wrapped in useCallback with stable deps), safe to include
  }, [showError]);

  // ------------------------------------------------------------------
  // Device selection handlers
  // ------------------------------------------------------------------

  const handleToggleDevice = useCallback((udid: string) => {
    setSelectedUdids(prev => {
      const next = new Set(prev);
      if (next.has(udid)) next.delete(udid);
      else next.add(udid);
      return next;
    });
    // Ensure default session exists
    setDeviceSessions(prev => {
      if (prev.has(udid)) return prev;
      return new Map(prev).set(udid, createDefaultSession());
    });
  }, []);

  const handleSelectAll = useCallback(() => {
    const allUdids = new Set(devices.map(d => d.udid));
    setSelectedUdids(allUdids);
    // Ensure sessions exist for all
    setDeviceSessions(prev => {
      let next = prev;
      for (const udid of allUdids) {
        if (!next.has(udid)) {
          if (next === prev) next = new Map(prev);
          next.set(udid, createDefaultSession());
        }
      }
      return next;
    });
  }, [devices]);

  const handleSelectNone = useCallback(() => {
    setSelectedUdids(new Set());
  }, []);

  // ------------------------------------------------------------------
  // Handlers
  // ------------------------------------------------------------------

  const handleMapClick = useCallback(
    (lat: number, lng: number) => {
      // Use first selected device's drawing state
      const firstUdid = firstSelectedUdid;
      const session = firstUdid ? deviceSessions.get(firstUdid) : null;
      const drawing = session?.isDrawingPath ?? false;

      if (drawing && firstUdid) {
        // Add path point to the first selected device's session
        updateSession(firstUdid, {
          pathPoints: [...(session?.pathPoints ?? []), { latitude: lat, longitude: lng }],
        });
        return;
      }
      setPickedLocation({ latitude: lat, longitude: lng });
    },
    [firstSelectedUdid, deviceSessions, updateSession],
  );

  const handleTeleport = useCallback(async () => {
    if (selectedUdids.size === 0 || !pickedLocation) return;
    await Promise.allSettled(
      Array.from(selectedUdids).map(udid =>
        api.setLocation(udid, pickedLocation.latitude, pickedLocation.longitude)
          .then(() => updateSession(udid, { currentLocation: pickedLocation }))
          .catch(err => showError(`${udid.slice(-8)} 設定位置失敗：${(err as Error).message}`))
      )
    );
    setPickedLocation(null);
  }, [selectedUdids, pickedLocation, updateSession, showError]);

  const handleCancelPick = useCallback(() => {
    setPickedLocation(null);
  }, []);

  const handleClearLocation = useCallback(async () => {
    if (selectedUdids.size === 0) return;
    await Promise.allSettled(
      Array.from(selectedUdids).map(udid =>
        api.clearLocation(udid)
          .then(() => updateSession(udid, { currentLocation: null, simState: "idle", simProgress: null }))
          .catch(err => showError(`${udid.slice(-8)} 清除位置失敗：${(err as Error).message}`))
      )
    );
  }, [selectedUdids, updateSession, showError]);

  const handleStartSimulation = useCallback(async () => {
    if (selectedUdids.size === 0) return;
    // Use first selected device's path (shared path mode)
    const firstUdid = Array.from(selectedUdids)[0];
    const session = deviceSessions.get(firstUdid) ?? createDefaultSession();
    if (session.pathPoints.length < 2) {
      showError("請先繪製路徑（至少 2 個點）");
      return;
    }

    await Promise.allSettled(
      Array.from(selectedUdids).map(udid =>
        api.startSimulation({
          udid,
          path: session.pathPoints,
          speed_kmh: session.speedKmh,
        })
          .then(() => updateSession(udid, { simState: "running" }))
          .catch(err => showError(`${udid.slice(-8)} 啟動失敗：${(err as Error).message}`))
      )
    );
  }, [selectedUdids, deviceSessions, updateSession, showError]);

  const handlePause = useCallback(async () => {
    if (selectedUdids.size === 0) return;
    await Promise.allSettled(
      Array.from(selectedUdids).map(udid =>
        api.pauseSimulation(udid)
          .then(() => updateSession(udid, { simState: "paused" }))
          .catch(err => showError(`${udid.slice(-8)} 暫停失敗：${(err as Error).message}`))
      )
    );
  }, [selectedUdids, updateSession, showError]);

  const handleResume = useCallback(async () => {
    if (selectedUdids.size === 0) return;
    await Promise.allSettled(
      Array.from(selectedUdids).map(udid =>
        api.resumeSimulation(udid)
          .then(() => updateSession(udid, { simState: "running" }))
          .catch(err => showError(`${udid.slice(-8)} 繼續失敗：${(err as Error).message}`))
      )
    );
  }, [selectedUdids, updateSession, showError]);

  const handleStop = useCallback(async () => {
    if (selectedUdids.size === 0) return;
    await Promise.allSettled(
      Array.from(selectedUdids).map(udid =>
        api.stopSimulation(udid)
          .then(() => updateSession(udid, { simState: "idle", simProgress: null }))
          .catch(err => showError(`${udid.slice(-8)} 停止失敗：${(err as Error).message}`))
      )
    );
  }, [selectedUdids, updateSession, showError]);

  const handleSpeedChange = useCallback(
    async (newSpeed: number) => {
      // Update speed for all selected device sessions
      for (const udid of selectedUdids) {
        updateSession(udid, { speedKmh: newSpeed });
      }
      // If any selected device is running/paused, update speed on backend
      await Promise.allSettled(
        Array.from(selectedUdids)
          .filter(udid => {
            const s = deviceSessions.get(udid);
            return s && (s.simState === "running" || s.simState === "paused");
          })
          .map(udid =>
            api.setSimulationSpeed(udid, newSpeed)
              .catch(err => showError(`${udid.slice(-8)} 設定速度失敗：${(err as Error).message}`))
          )
      );
    },
    [selectedUdids, deviceSessions, updateSession, showError],
  );

  const handleGPXLoad = useCallback(
    async (content: string) => {
      try {
        const result = await api.parseGPX(content);
        // Load GPX path into first selected device's session
        if (firstSelectedUdid) {
          updateSession(firstSelectedUdid, {
            pathPoints: result.waypoints,
            isDrawingPath: false,
          });
        }
      } catch (err) {
        console.error("Failed to parse GPX:", err);
        showError("GPX 檔案解析失敗");
      }
    },
    [firstSelectedUdid, updateSession, showError],
  );

  const handleAddFavorite = useCallback(
    async (name: string, lat: number, lng: number) => {
      try {
        await api.addFavorite(name, lat, lng);
        const updated = await api.listFavorites();
        setFavorites(updated);
      } catch (err) {
        console.error("Failed to add favorite:", err);
        showError("新增收藏失敗");
      }
    },
    [showError],
  );

  const handleRemoveFavorite = useCallback(async (fav: FavoriteLocation) => {
    try {
      // 先取得最新列表，避免 stale index
      const currentFavs = await api.listFavorites();
      const index = currentFavs.findIndex(
        f => f.name === fav.name &&
             Math.abs(f.latitude - fav.latitude) < 0.000001 &&
             Math.abs(f.longitude - fav.longitude) < 0.000001
      );
      if (index === -1) {
        // 已被刪除，只更新本地狀態
        setFavorites(currentFavs);
        return;
      }
      await api.removeFavorite(index);
      setFavorites(await api.listFavorites());
    } catch (err) {
      console.error("Failed to remove favorite:", err);
      showError("刪除收藏失敗：" + (err as Error).message);
    }
  }, [showError]);

  const handleSelectFavorite = useCallback(
    async (fav: FavoriteLocation) => {
      if (selectedUdids.size === 0) return;
      const coord: Coordinate = { latitude: fav.latitude, longitude: fav.longitude };
      await Promise.allSettled(
        Array.from(selectedUdids).map(udid =>
          api.setLocation(udid, fav.latitude, fav.longitude)
            .then(() => updateSession(udid, { currentLocation: coord }))
            .catch(err => showError(`${udid.slice(-8)} 設定收藏位置失敗：${(err as Error).message}`))
        )
      );
    },
    [selectedUdids, updateSession, showError],
  );

  const handleClearPath = useCallback(() => {
    if (firstSelectedUdid) {
      updateSession(firstSelectedUdid, { pathPoints: [], isDrawingPath: false });
    }
  }, [firstSelectedUdid, updateSession]);

  const handleToggleDrawPath = useCallback(() => {
    if (firstSelectedUdid) {
      const session = deviceSessions.get(firstSelectedUdid) ?? createDefaultSession();
      updateSession(firstSelectedUdid, { isDrawingPath: !session.isDrawingPath });
    }
  }, [firstSelectedUdid, deviceSessions, updateSession]);

  // ------------------------------------------------------------------
  // Render
  // ------------------------------------------------------------------

  // Check if at least one selected device is ready
  const anySelectedReady = Array.from(selectedUdids).some(udid => {
    const dev = devices.find(d => d.udid === udid);
    return dev?.is_ready === true;
  });

  return (
    <div className="app">
      <div className="sidebar">
        <DevicePanel
          devices={devices}
          selectedUdids={selectedUdids}
          onToggleDevice={handleToggleDevice}
          deviceSessions={deviceSessions}
          onSelectAll={handleSelectAll}
          onSelectNone={handleSelectNone}
        />
        <ControlPanel
          selectedCount={selectedUdids.size}
          anyDeviceReady={anySelectedReady}
          simState={aggregateSimState}
          simProgress={activeSession?.simProgress ?? null}
          speedKmh={activeSession?.speedKmh ?? 10}
          isDrawingPath={activeSession?.isDrawingPath ?? false}
          pathPointCount={activeSession?.pathPoints?.length ?? 0}
          favorites={favorites}
          deviceSessions={deviceSessions}
          selectedUdids={selectedUdids}
          onStartSimulation={handleStartSimulation}
          onPause={handlePause}
          onResume={handleResume}
          onStop={handleStop}
          onSpeedChange={handleSpeedChange}
          onClearLocation={handleClearLocation}
          onToggleDrawPath={handleToggleDrawPath}
          onClearPath={handleClearPath}
          onGPXLoad={handleGPXLoad}
          onAddFavorite={handleAddFavorite}
          onRemoveFavorite={handleRemoveFavorite}
          onSelectFavorite={handleSelectFavorite}
        />
      </div>
      <div className="main-content">
        <MapView
          currentLocation={activeSession?.currentLocation ?? null}
          pickedLocation={pickedLocation}
          pathPoints={activeSession?.pathPoints ?? []}
          isDrawingPath={activeSession?.isDrawingPath ?? false}
          onMapClick={handleMapClick}
          onTeleport={handleTeleport}
          onCancelPick={handleCancelPick}
          canTeleport={selectedUdids.size > 0}
          deviceLocations={deviceLocations}
        />
        <StatusBar
          backendReady={backendReady}
          wsConnected={wsConnected}
          deviceCount={devices.length}
          selectedCount={selectedUdids.size}
          simState={aggregateSimState}
        />
      </div>
      <ToastContainer toasts={toasts} onRemove={removeToast} />
    </div>
  );
}

export default App;
