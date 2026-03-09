import type { SimStateLabel } from "../types/api";

interface StatusBarProps {
  backendReady: boolean;
  wsConnected: boolean;
  deviceCount: number;
  selectedCount: number;
  simState: SimStateLabel;
}

function formatSimState(state: SimStateLabel): string {
  switch (state) {
    case "idle":
      return "閒置";
    case "running":
      return "模擬中";
    case "paused":
      return "已暫停";
    case "completed":
      return "已完成";
    case "error":
      return "錯誤";
    default:
      return state;
  }
}

export function StatusBar({
  backendReady,
  wsConnected,
  deviceCount,
  selectedCount,
  simState,
}: StatusBarProps) {
  return (
    <div className="status-bar">
      <div className="status-bar__left">
        <span
          className={`status-indicator ${backendReady ? "status-indicator--ok" : "status-indicator--error"}`}
        />
        <span className="status-label">
          後端：{backendReady ? "已連線" : "未連線"}
        </span>

        <span className="status-separator" />

        <span
          className={`status-indicator ${wsConnected ? "status-indicator--ok" : "status-indicator--warn"}`}
        />
        <span className="status-label">
          WebSocket：{wsConnected ? "已連線" : "未連線"}
        </span>
      </div>

      <div className="status-bar__right">
        <span className="status-label">
          裝置：{deviceCount} (已選 {selectedCount})
        </span>
        <span className="status-separator" />
        <span className="status-label">
          模擬：{formatSimState(simState)}
        </span>
      </div>
    </div>
  );
}
