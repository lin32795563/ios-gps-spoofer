/**
 * MapView component.
 *
 * Renders a MapLibre GL map (GPU-accelerated vector tiles) with:
 * - Click-to-pick location, then confirm to teleport
 * - Current simulated position marker (blue)
 * - Picked/pending location marker (red) with teleport popup
 * - Path visualization (line + numbered markers)
 * - Search box for geocoding (Nominatim)
 * - Coordinate display of cursor position
 */

import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import Map, {
  Layer,
  Marker,
  NavigationControl,
  Source,
} from "react-map-gl/maplibre";
import type { MapLayerMouseEvent, MapRef } from "react-map-gl/maplibre";
import type { Coordinate } from "../types/api";

// Default map center (Taipei)
const DEFAULT_CENTER = { latitude: 25.033964, longitude: 121.564468 };
const DEFAULT_ZOOM = 13;

// OpenFreeMap style URL (free, no API key needed)
const MAP_STYLE = "https://tiles.openfreemap.org/styles/liberty";

interface DeviceLocationEntry {
  coordinate: Coordinate;
  isSelected: boolean;
  name: string;
}

interface MapViewProps {
  currentLocation: Coordinate | null;
  pickedLocation: Coordinate | null;
  pathPoints: Coordinate[];
  isDrawingPath: boolean;
  onMapClick: (lat: number, lng: number) => void;
  onTeleport: () => void;
  onCancelPick: () => void;
  canTeleport: boolean;
  deviceLocations?: Map<string, DeviceLocationEntry>;
}

/**
 * Try to parse a string as coordinates.
 * Supports formats: "25.033, 121.564", "25.033 121.564", "25.033,121.564"
 * Returns [lat, lng] or null if not valid coordinates.
 */
function parseCoordinates(input: string): [number, number] | null {
  const match = input.match(
    /^\s*(-?\d+(?:\.\d+)?)\s*[,\s]\s*(-?\d+(?:\.\d+)?)\s*$/,
  );
  if (!match) return null;
  const lat = parseFloat(match[1]);
  const lng = parseFloat(match[2]);
  if (lat < -90 || lat > 90 || lng < -180 || lng > 180) return null;
  return [lat, lng];
}

function SearchBox({
  onFlyTo,
  onPick,
}: {
  onFlyTo: (lat: number, lng: number) => void;
  onPick: (lat: number, lng: number) => void;
}) {
  const [query, setQuery] = useState("");
  const [isSearching, setIsSearching] = useState(false);

  const handleSearch = useCallback(
    async (event: React.FormEvent) => {
      event.preventDefault();
      const trimmed = query.trim();
      if (!trimmed || isSearching) return;

      // If input looks like coordinates, parse directly
      const coords = parseCoordinates(trimmed);
      if (coords) {
        onFlyTo(coords[0], coords[1]);
        onPick(coords[0], coords[1]);
        return;
      }

      // Otherwise, geocode via Nominatim
      setIsSearching(true);
      try {
        const url = `https://nominatim.openstreetmap.org/search?format=json&q=${encodeURIComponent(trimmed)}&limit=1&accept-language=zh-TW`;
        const response = await fetch(url, {
          headers: { "User-Agent": "iOSGPSSpoofer/0.1" },
        });
        const results = await response.json();

        if (results.length > 0) {
          const lat = parseFloat(results[0].lat);
          const lon = parseFloat(results[0].lon);
          onFlyTo(lat, lon);
          onPick(lat, lon);
        } else {
          console.warn("No results found for:", trimmed);
        }
      } catch (error) {
        console.error("Search failed:", error);
      } finally {
        setIsSearching(false);
      }
    },
    [query, isSearching, onFlyTo, onPick],
  );

  return (
    <div className="map-search-box">
      <form onSubmit={handleSearch}>
        <input
          type="text"
          className="map-search-input"
          placeholder="搜尋地點或座標 (25.03, 121.56)..."
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <button
          type="submit"
          className="map-search-btn"
          disabled={isSearching || !query.trim()}
        >
          {isSearching ? "..." : "搜尋"}
        </button>
      </form>
    </div>
  );
}

export function MapView({
  currentLocation,
  pickedLocation,
  pathPoints,
  isDrawingPath,
  onMapClick,
  onTeleport,
  onCancelPick,
  canTeleport,
  deviceLocations,
}: MapViewProps) {
  const mapRef = useRef<MapRef>(null);
  const [cursorCoords, setCursorCoords] = useState<{
    lat: number;
    lng: number;
  } | null>(null);
  const lastFlyLocation = useRef<Coordinate | null>(null);

  // Fly to current location when it changes significantly
  useEffect(() => {
    if (!currentLocation || !mapRef.current) return;
    const prev = lastFlyLocation.current;
    if (prev) {
      const dlat = Math.abs(currentLocation.latitude - prev.latitude);
      const dlng = Math.abs(currentLocation.longitude - prev.longitude);
      if (dlat < 0.001 && dlng < 0.001) return;
    }
    mapRef.current.flyTo({
      center: [currentLocation.longitude, currentLocation.latitude],
      duration: 500,
    });
    lastFlyLocation.current = currentLocation;
  }, [currentLocation]);

  const handleClick = useCallback(
    (event: MapLayerMouseEvent) => {
      onMapClick(event.lngLat.lat, event.lngLat.lng);
    },
    [onMapClick],
  );

  const handleMouseMove = useCallback((event: MapLayerMouseEvent) => {
    setCursorCoords({ lat: event.lngLat.lat, lng: event.lngLat.lng });
  }, []);

  const handleMouseLeave = useCallback(() => {
    setCursorCoords(null);
  }, []);

  const handleFlyTo = useCallback((lat: number, lng: number) => {
    mapRef.current?.flyTo({
      center: [lng, lat],
      zoom: 15,
      duration: 1000,
    });
  }, []);

  // Build GeoJSON for the path line
  const pathLineGeoJSON = useMemo(() => {
    if (pathPoints.length < 2) return null;
    return {
      type: "Feature" as const,
      properties: {},
      geometry: {
        type: "LineString" as const,
        coordinates: pathPoints.map((p) => [p.longitude, p.latitude]),
      },
    };
  }, [pathPoints]);

  return (
    <div
      className={`map-container ${isDrawingPath ? "map-container--drawing" : ""}`}
    >
      <Map
        ref={mapRef}
        initialViewState={{
          latitude: DEFAULT_CENTER.latitude,
          longitude: DEFAULT_CENTER.longitude,
          zoom: DEFAULT_ZOOM,
        }}
        style={{ width: "100%", height: "100%" }}
        mapStyle={MAP_STYLE}
        onClick={handleClick}
        onMouseMove={handleMouseMove}
        onMouseLeave={handleMouseLeave}
        cursor={isDrawingPath ? "crosshair" : undefined}
        attributionControl={true}
      >
        <NavigationControl position="top-left" />

        {/* Path line */}
        {pathLineGeoJSON && (
          <Source id="path-line" type="geojson" data={pathLineGeoJSON}>
            <Layer
              id="path-line-layer"
              type="line"
              paint={{
                "line-color": "#3388ff",
                "line-width": 3,
                "line-opacity": 0.8,
              }}
            />
          </Source>
        )}

        {/* Path point markers (limit to 50 for performance) */}
        {pathPoints.length > 0 &&
          pathPoints.length <= 50 &&
          pathPoints.map((point, index) => (
            <Marker
              key={`path-${index}-${point.latitude}-${point.longitude}`}
              latitude={point.latitude}
              longitude={point.longitude}
              anchor="center"
            >
              <div className="maplibre-path-marker">{index + 1}</div>
            </Marker>
          ))}

        {/* Current simulated location marker (blue) -- shown when no multi-device data */}
        {currentLocation && !deviceLocations?.size && (
          <Marker
            latitude={currentLocation.latitude}
            longitude={currentLocation.longitude}
            anchor="center"
          >
            <div className="maplibre-current-marker" />
          </Marker>
        )}

        {/* Multi-device location markers */}
        {deviceLocations && Array.from(deviceLocations.entries()).map(([udid, entry]) => (
          <Marker
            key={`device-${udid}`}
            latitude={entry.coordinate.latitude}
            longitude={entry.coordinate.longitude}
            anchor="center"
          >
            <div
              className={`maplibre-device-marker ${entry.isSelected ? "maplibre-device-marker--selected" : ""}`}
              title={entry.name}
            >
              <span className="maplibre-device-marker__label">
                {entry.name.length > 6 ? entry.name.slice(-6) : entry.name}
              </span>
            </div>
          </Marker>
        ))}

        {/* Picked location marker (red) with teleport popup */}
        {pickedLocation && (
          <Marker
            latitude={pickedLocation.latitude}
            longitude={pickedLocation.longitude}
            anchor="bottom"
          >
            <div className="maplibre-picked-wrapper">
              <div className="maplibre-picked-popup">
                <div className="picked-popup__coords">
                  {pickedLocation.latitude.toFixed(6)},{" "}
                  {pickedLocation.longitude.toFixed(6)}
                </div>
                <div className="picked-popup__actions">
                  <button
                    type="button"
                    className="picked-popup__teleport"
                    onClick={(e) => {
                      e.stopPropagation();
                      onTeleport();
                    }}
                    disabled={!canTeleport}
                    title={!canTeleport ? "請先選擇裝置" : ""}
                  >
                    瞬移到這裡
                  </button>
                  <button
                    type="button"
                    className="picked-popup__cancel"
                    onClick={(e) => {
                      e.stopPropagation();
                      onCancelPick();
                    }}
                  >
                    取消
                  </button>
                </div>
              </div>
              <div className="maplibre-picked-pin" />
            </div>
          </Marker>
        )}
      </Map>

      <SearchBox onFlyTo={handleFlyTo} onPick={onMapClick} />

      {cursorCoords && (
        <div className="map-cursor-coords">
          {cursorCoords.lat.toFixed(6)}, {cursorCoords.lng.toFixed(6)}
        </div>
      )}

      {isDrawingPath && (
        <div className="map-drawing-indicator">
          繪製模式：點擊地圖新增路徑點
        </div>
      )}

      {pathPoints.length > 50 && (
        <div
          style={{
            position: "absolute",
            top: 12,
            right: 12,
            backgroundColor: "rgba(0, 0, 0, 0.65)",
            color: "#fff",
            padding: "6px 12px",
            borderRadius: 4,
            fontSize: 12,
            lineHeight: 1.4,
            zIndex: 1000,
            pointerEvents: "none",
          }}
        >
          {`路徑點 ${pathPoints.length} 個（超過 50 個後序號標記已隱藏）`}
        </div>
      )}
    </div>
  );
}
