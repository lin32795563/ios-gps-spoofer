import { useCallback, useRef } from "react";
import type {
  DeviceInfo,
  FavoriteLocation,
  SimulationProgress,
} from "../types/api";

interface ControlPanelProps {
  selectedDevice: DeviceInfo | null;
  simState: string;
  simProgress: SimulationProgress | null;
  speedKmh: number;
  isDrawingPath: boolean;
  pathPointCount: number;
  favorites: FavoriteLocation[];
  onStartSimulation: () => void;
  onPause: () => void;
  onResume: () => void;
  onStop: () => void;
  onSpeedChange: (speed: number) => void;
  onClearLocation: () => void;
  onToggleDrawPath: () => void;
  onClearPath: () => void;
  onGPXLoad: (content: string) => void;
  onAddFavorite: (name: string, lat: number, lng: number) => void;
  onRemoveFavorite: (index: number) => void;
  onSelectFavorite: (fav: FavoriteLocation) => void;
}

const SPEED_PRESETS = [
  { label: "步行", value: 5 },
  { label: "騎車", value: 15 },
  { label: "開車", value: 60 },
  { label: "高速", value: 120 },
];

function formatTime(seconds: number): string {
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  return `${mins.toString().padStart(2, "0")}:${secs.toString().padStart(2, "0")}`;
}

function formatDistance(meters: number): string {
  if (meters < 1000) {
    return `${Math.round(meters)}m`;
  }
  return `${(meters / 1000).toFixed(2)}km`;
}

export function ControlPanel({
  selectedDevice,
  simState,
  simProgress,
  speedKmh,
  isDrawingPath,
  pathPointCount,
  favorites,
  onStartSimulation,
  onPause,
  onResume,
  onStop,
  onSpeedChange,
  onClearLocation,
  onToggleDrawPath,
  onClearPath,
  onGPXLoad,
  onAddFavorite,
  onRemoveFavorite,
  onSelectFavorite,
}: ControlPanelProps) {
  const gpxInputRef = useRef<HTMLInputElement>(null);
  const favoriteNameRef = useRef<HTMLInputElement>(null);
  const favLatRef = useRef<HTMLInputElement>(null);
  const favLngRef = useRef<HTMLInputElement>(null);

  const isSimRunning = simState === "running" || simState === "paused";
  const deviceReady = selectedDevice?.is_ready === true;

  const handleGPXFileChange = useCallback(
    (event: React.ChangeEvent<HTMLInputElement>) => {
      const file = event.target.files?.[0];
      if (!file) return;

      const reader = new FileReader();
      reader.onload = (e) => {
        const content = e.target?.result;
        if (typeof content === "string") {
          onGPXLoad(content);
        }
      };
      reader.readAsText(file);
      event.target.value = "";
    },
    [onGPXLoad],
  );

  const handleAddFavorite = useCallback(() => {
    const name = favoriteNameRef.current?.value.trim();
    const lat = parseFloat(favLatRef.current?.value || "");
    const lng = parseFloat(favLngRef.current?.value || "");

    if (!name) {
      alert("請輸入收藏名稱");
      return;
    }
    if (isNaN(lat) || isNaN(lng)) {
      alert("請輸入有效的經緯度");
      return;
    }
    if (lat < -90 || lat > 90 || lng < -180 || lng > 180) {
      alert("座標超出範圍。緯度：-90 ~ 90，經度：-180 ~ 180");
      return;
    }

    onAddFavorite(name, lat, lng);

    if (favoriteNameRef.current) favoriteNameRef.current.value = "";
    if (favLatRef.current) favLatRef.current.value = "";
    if (favLngRef.current) favLngRef.current.value = "";
  }, [onAddFavorite]);

  return (
    <div className="control-panel">
      {!selectedDevice && (
        <div className="control-section">
          <p className="empty-hint">請先選擇裝置</p>
        </div>
      )}

      {selectedDevice && !deviceReady && (
        <div className="control-section">
          <p className="warning-text">
            裝置尚未就緒。狀態：{selectedDevice.state}
          </p>
          {selectedDevice.error_message && (
            <p className="error-text">{selectedDevice.error_message}</p>
          )}
        </div>
      )}

      {deviceReady && (
        <>
          {/* 定位設定 */}
          <div className="control-section">
            <h3 className="section-title">定位設定</h3>
            <p className="section-hint">
              點擊地圖設定模擬 GPS 位置
            </p>
            <button
              type="button"
              className="btn btn--danger"
              onClick={onClearLocation}
              disabled={isSimRunning}
            >
              恢復真實定位
            </button>
          </div>

          {/* 路徑模擬 */}
          <div className="control-section">
            <h3 className="section-title">路徑模擬</h3>
            <div className="btn-row">
              <button
                type="button"
                className={`btn ${isDrawingPath ? "btn--active" : "btn--secondary"}`}
                onClick={onToggleDrawPath}
                disabled={isSimRunning}
              >
                {isDrawingPath ? "結束繪製" : "繪製路徑"}
              </button>
              <button
                type="button"
                className="btn btn--secondary"
                onClick={() => gpxInputRef.current?.click()}
                disabled={isSimRunning}
              >
                匯入 GPX
              </button>
              <input
                ref={gpxInputRef}
                type="file"
                accept=".gpx"
                style={{ display: "none" }}
                onChange={handleGPXFileChange}
              />
            </div>
            {pathPointCount > 0 && (
              <div className="path-info">
                <span>{pathPointCount} 個路徑點</span>
                <button
                  type="button"
                  className="btn btn--small btn--secondary"
                  onClick={onClearPath}
                  disabled={isSimRunning}
                >
                  清除路徑
                </button>
              </div>
            )}
          </div>

          {/* 速度控制 */}
          <div className="control-section">
            <h3 className="section-title">
              速度：{speedKmh.toFixed(1)} km/h
            </h3>
            <div className="speed-presets">
              {SPEED_PRESETS.map((preset) => (
                <button
                  key={preset.label}
                  type="button"
                  className={`btn btn--small ${
                    Math.abs(speedKmh - preset.value) < 0.1
                      ? "btn--active"
                      : "btn--secondary"
                  }`}
                  onClick={() => onSpeedChange(preset.value)}
                >
                  {preset.label}
                </button>
              ))}
            </div>
            <input
              type="range"
              className="speed-slider"
              min="1"
              max="200"
              step="1"
              value={speedKmh}
              onChange={(e) => onSpeedChange(parseFloat(e.target.value))}
            />
          </div>

          {/* 模擬控制 */}
          <div className="control-section">
            <h3 className="section-title">模擬控制</h3>
            <div className="btn-row">
              {simState === "idle" && (
                <button
                  type="button"
                  className="btn btn--primary"
                  onClick={onStartSimulation}
                  disabled={pathPointCount < 2}
                  title={
                    pathPointCount < 2
                      ? "請先繪製至少 2 個路徑點"
                      : ""
                  }
                >
                  開始模擬
                </button>
              )}
              {simState === "running" && (
                <>
                  <button
                    type="button"
                    className="btn btn--secondary"
                    onClick={onPause}
                  >
                    暫停
                  </button>
                  <button
                    type="button"
                    className="btn btn--danger"
                    onClick={onStop}
                  >
                    停止
                  </button>
                </>
              )}
              {simState === "paused" && (
                <>
                  <button
                    type="button"
                    className="btn btn--primary"
                    onClick={onResume}
                  >
                    繼續
                  </button>
                  <button
                    type="button"
                    className="btn btn--danger"
                    onClick={onStop}
                  >
                    停止
                  </button>
                </>
              )}
            </div>
          </div>

          {/* 模擬進度 */}
          {simProgress && (
            <div className="control-section progress-section">
              <h3 className="section-title">模擬進度</h3>
              <div className="progress-bar-container">
                <div
                  className="progress-bar-fill"
                  style={{
                    width: `${(simProgress.fraction_complete * 100).toFixed(1)}%`,
                  }}
                />
              </div>
              <div className="progress-details">
                <span>
                  {(simProgress.fraction_complete * 100).toFixed(1)}%
                </span>
                <span>{formatTime(simProgress.elapsed_time_s)}</span>
                <span>
                  {formatDistance(simProgress.distance_covered_m)} /{" "}
                  {formatDistance(simProgress.total_distance_m)}
                </span>
                <span>
                  路段 {simProgress.segment_index + 1}/
                  {simProgress.total_segments}
                </span>
              </div>
            </div>
          )}

          {/* 收藏地點 */}
          <div className="control-section">
            <h3 className="section-title">收藏地點</h3>
            <div className="favorite-add-form">
              <input
                ref={favoriteNameRef}
                type="text"
                placeholder="名稱"
                className="input-field input-field--name"
              />
              <input
                ref={favLatRef}
                type="number"
                placeholder="緯度"
                className="input-field input-field--coord"
                step="any"
              />
              <input
                ref={favLngRef}
                type="number"
                placeholder="經度"
                className="input-field input-field--coord"
                step="any"
              />
              <button
                type="button"
                className="btn btn--small btn--primary"
                onClick={handleAddFavorite}
              >
                新增
              </button>
            </div>
            {favorites.length === 0 && (
              <p className="empty-hint">尚無收藏地點</p>
            )}
            <div className="favorite-list">
              {favorites.map((fav, index) => (
                <div key={`${fav.name}-${index}`} className="favorite-item">
                  <button
                    type="button"
                    className="favorite-item__select"
                    onClick={() => onSelectFavorite(fav)}
                    title={`${fav.latitude.toFixed(6)}, ${fav.longitude.toFixed(6)}`}
                  >
                    <span className="favorite-item__name">{fav.name}</span>
                    <span className="favorite-item__coords">
                      {fav.latitude.toFixed(4)}, {fav.longitude.toFixed(4)}
                    </span>
                  </button>
                  <button
                    type="button"
                    className="btn btn--icon btn--danger"
                    onClick={() => onRemoveFavorite(index)}
                    title="刪除收藏"
                    aria-label={`刪除 ${fav.name}`}
                  >
                    X
                  </button>
                </div>
              ))}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
