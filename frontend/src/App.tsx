/**
 * Main application component.
 *
 * Layout: Left sidebar (device panel, controls) + Right map area.
 * Manages global state: devices, selected device, simulation status.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { DevicePanel } from "./components/DevicePanel";
import { ControlPanel } from "./components/ControlPanel";
import { MapView } from "./components/MapView";
import { StatusBar } from "./components/StatusBar";
import * as api from "./services/apiClient";
import { WebSocketClient } from "./services/wsClient";
import type {
  Coordinate,
  DeviceInfo,
  FavoriteLocation,
  SimulationProgress,
} from "./types/api";
import "./App.css";

function App() {
  // Device state
  const [devices, setDevices] = useState<DeviceInfo[]>([]);
  const [selectedUdid, setSelectedUdid] = useState<string | null>(null);

  // Location state
  const [currentLocation, setCurrentLocation] = useState<Coordinate | null>(null);
  const [pickedLocation, setPickedLocation] = useState<Coordinate | null>(null);

  // Simulation state
  const [simState, setSimState] = useState<string>("idle");
  const [simProgress, setSimProgress] = useState<SimulationProgress | null>(null);
  const [speedKmh, setSpeedKmh] = useState(5.0);

  // Path state
  const [pathPoints, setPathPoints] = useState<Coordinate[]>([]);
  const [isDrawingPath, setIsDrawingPath] = useState(false);

  // Favorites
  const [favorites, setFavorites] = useState<FavoriteLocation[]>([]);

  // Connection state
  const [wsConnected, setWsConnected] = useState(false);
  const [backendReady, setBackendReady] = useState(false);

  // WebSocket client ref
  const wsClientRef = useRef<WebSocketClient | null>(null);

  // Ref to track selectedUdid in WebSocket callbacks (avoids stale closure)
  const selectedUdidRef = useRef<string | null>(null);
  selectedUdidRef.current = selectedUdid;

  // ------------------------------------------------------------------
  // Initialize WebSocket and poll devices
  // ------------------------------------------------------------------

  useEffect(() => {
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
        }
        try {
          const favList = await api.listFavorites();
          setFavorites(favList);
        } catch (err) {
          console.error("Failed to load favorites:", err);
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
            if (selectedUdidRef.current === msg.udid) {
              setSimState("idle");
              setSimProgress(null);
            }
          },
          onSimulationProgress: (msg) => {
            if (msg.udid === selectedUdidRef.current) {
              setSimProgress(msg.progress);
              setSimState(msg.progress.state);
              setCurrentLocation(msg.progress.current_position);
            }
          },
          onSimulationComplete: (msg) => {
            if (msg.udid === selectedUdidRef.current) {
              setSimState("idle");
              setSimProgress(null);
            }
          },
          onSimulationError: (msg) => {
            if (msg.udid === selectedUdidRef.current) {
              setSimState("idle");
              setSimProgress(null);
              console.error(`Simulation error: ${msg.error}`);
            }
          },
          onConnectionChange: (connected) => {
            setWsConnected(connected);
          },
        },
        wsUrl,
      );
      client.connect();
      wsClientRef.current = client;
    };
    setupWs();

    // Poll devices every 5 seconds as fallback
    const pollInterval = setInterval(async () => {
      try {
        const deviceList = await api.listDevices();
        setDevices(deviceList);
      } catch {
        // ignore polling errors
      }
    }, 5000);

    return () => {
      clearInterval(pollInterval);
      wsClientRef.current?.disconnect();
    };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // ------------------------------------------------------------------
  // Handlers
  // ------------------------------------------------------------------

  const handleMapClick = useCallback(
    (lat: number, lng: number) => {
      if (isDrawingPath) {
        setPathPoints((prev) => [...prev, { latitude: lat, longitude: lng }]);
        return;
      }
      setPickedLocation({ latitude: lat, longitude: lng });
    },
    [isDrawingPath],
  );

  const handleTeleport = useCallback(async () => {
    if (!selectedUdid || !pickedLocation) return;
    try {
      await api.setLocation(selectedUdid, pickedLocation.latitude, pickedLocation.longitude);
      setCurrentLocation(pickedLocation);
      setPickedLocation(null);
    } catch (err) {
      console.error("Failed to set location:", err);
    }
  }, [selectedUdid, pickedLocation]);

  const handleCancelPick = useCallback(() => {
    setPickedLocation(null);
  }, []);

  const handleClearLocation = useCallback(async () => {
    if (!selectedUdid) return;
    try {
      await api.clearLocation(selectedUdid);
      setCurrentLocation(null);
      setSimState("idle");
      setSimProgress(null);
    } catch (err) {
      console.error("Failed to clear location:", err);
    }
  }, [selectedUdid]);

  const handleStartSimulation = useCallback(async () => {
    if (!selectedUdid || pathPoints.length < 2) return;
    try {
      await api.startSimulation({
        udid: selectedUdid,
        path: pathPoints,
        speed_kmh: speedKmh,
      });
      setSimState("running");
    } catch (err) {
      console.error("Failed to start simulation:", err);
    }
  }, [selectedUdid, pathPoints, speedKmh]);

  const handlePause = useCallback(async () => {
    if (!selectedUdid) return;
    try {
      await api.pauseSimulation(selectedUdid);
      setSimState("paused");
    } catch (err) {
      console.error("Failed to pause:", err);
    }
  }, [selectedUdid]);

  const handleResume = useCallback(async () => {
    if (!selectedUdid) return;
    try {
      await api.resumeSimulation(selectedUdid);
      setSimState("running");
    } catch (err) {
      console.error("Failed to resume:", err);
    }
  }, [selectedUdid]);

  const handleStop = useCallback(async () => {
    if (!selectedUdid) return;
    try {
      await api.stopSimulation(selectedUdid);
      setSimState("idle");
      setSimProgress(null);
    } catch (err) {
      console.error("Failed to stop:", err);
    }
  }, [selectedUdid]);

  const handleSpeedChange = useCallback(
    async (newSpeed: number) => {
      setSpeedKmh(newSpeed);
      if (selectedUdid && (simState === "running" || simState === "paused")) {
        try {
          await api.setSimulationSpeed(selectedUdid, newSpeed);
        } catch (err) {
          console.error("Failed to set speed:", err);
        }
      }
    },
    [selectedUdid, simState],
  );

  const handleGPXLoad = useCallback(
    async (content: string) => {
      try {
        const result = await api.parseGPX(content);
        setPathPoints(result.waypoints);
        setIsDrawingPath(false);
      } catch (err) {
        console.error("Failed to parse GPX:", err);
      }
    },
    [],
  );

  const handleAddFavorite = useCallback(
    async (name: string, lat: number, lng: number) => {
      try {
        await api.addFavorite(name, lat, lng);
        const updated = await api.listFavorites();
        setFavorites(updated);
      } catch (err) {
        console.error("Failed to add favorite:", err);
      }
    },
    [],
  );

  const handleRemoveFavorite = useCallback(async (index: number) => {
    try {
      await api.removeFavorite(index);
      const updated = await api.listFavorites();
      setFavorites(updated);
    } catch (err) {
      console.error("Failed to remove favorite:", err);
    }
  }, []);

  const handleSelectFavorite = useCallback(
    async (fav: FavoriteLocation) => {
      if (!selectedUdid) return;
      try {
        await api.setLocation(selectedUdid, fav.latitude, fav.longitude);
        setCurrentLocation({ latitude: fav.latitude, longitude: fav.longitude });
      } catch (err) {
        console.error("Failed to set favorite location:", err);
      }
    },
    [selectedUdid],
  );

  const handleClearPath = useCallback(() => {
    setPathPoints([]);
    setIsDrawingPath(false);
  }, []);

  // ------------------------------------------------------------------
  // Render
  // ------------------------------------------------------------------

  const selectedDevice = devices.find((d) => d.udid === selectedUdid) || null;

  return (
    <div className="app">
      <div className="sidebar">
        <DevicePanel
          devices={devices}
          selectedUdid={selectedUdid}
          onSelectDevice={setSelectedUdid}
        />
        <ControlPanel
          selectedDevice={selectedDevice}
          simState={simState}
          simProgress={simProgress}
          speedKmh={speedKmh}
          isDrawingPath={isDrawingPath}
          pathPointCount={pathPoints.length}
          favorites={favorites}
          onStartSimulation={handleStartSimulation}
          onPause={handlePause}
          onResume={handleResume}
          onStop={handleStop}
          onSpeedChange={handleSpeedChange}
          onClearLocation={handleClearLocation}
          onToggleDrawPath={() => setIsDrawingPath((v) => !v)}
          onClearPath={handleClearPath}
          onGPXLoad={handleGPXLoad}
          onAddFavorite={handleAddFavorite}
          onRemoveFavorite={handleRemoveFavorite}
          onSelectFavorite={handleSelectFavorite}
        />
      </div>
      <div className="main-content">
        <MapView
          currentLocation={currentLocation}
          pickedLocation={pickedLocation}
          pathPoints={pathPoints}
          isDrawingPath={isDrawingPath}
          onMapClick={handleMapClick}
          onTeleport={handleTeleport}
          onCancelPick={handleCancelPick}
          canTeleport={!!selectedUdid}
        />
        <StatusBar
          backendReady={backendReady}
          wsConnected={wsConnected}
          deviceCount={devices.length}
          simState={simState}
        />
      </div>
    </div>
  );
}

export default App;
