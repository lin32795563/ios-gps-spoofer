import type { DeviceInfo, DeviceSessionState, SimStateLabel } from "../types/api";

interface DevicePanelProps {
  devices: DeviceInfo[];
  selectedUdids: Set<string>;
  onToggleDevice: (udid: string) => void;
  deviceSessions: Map<string, DeviceSessionState>;
  onSelectAll: () => void;
  onSelectNone: () => void;
}

function formatState(state: string): string {
  switch (state) {
    case "connected":
      return "已連接";
    case "ready":
      return "就緒";
    case "ddi_mounted":
      return "DDI 已掛載";
    case "tunnel_active":
      return "通道已建立";
    case "error":
      return "錯誤";
    default:
      return state;
  }
}

function stateColorClass(device: DeviceInfo): string {
  if (device.is_ready) return "state-ready";
  if (device.error_message) return "state-error";
  return "state-pending";
}

function SimStateIcon({ state }: { state: SimStateLabel }) {
  switch (state) {
    case "running":
      return (
        <span
          className="sim-state-icon sim-state-icon--running"
          title="模擬中"
        />
      );
    case "paused":
      return (
        <span
          className="sim-state-icon sim-state-icon--paused"
          title="已暫停"
        />
      );
    case "completed":
      return (
        <span
          className="sim-state-icon sim-state-icon--completed"
          title="已完成"
        >
          &#10003;
        </span>
      );
    case "error":
      return (
        <span
          className="sim-state-icon sim-state-icon--error"
          title="錯誤"
        >
          &#10005;
        </span>
      );
    case "idle":
    default:
      return (
        <span
          className="sim-state-icon sim-state-icon--idle"
          title="閒置"
        />
      );
  }
}

export function DevicePanel({
  devices,
  selectedUdids,
  onToggleDevice,
  deviceSessions,
  onSelectAll,
  onSelectNone,
}: DevicePanelProps) {
  return (
    <div className="device-panel">
      <div className="device-panel__header">
        <h2 className="panel-title">裝置列表</h2>
        {devices.length > 0 && (
          <div className="device-panel__actions">
            <button
              type="button"
              className="btn btn--small btn--secondary"
              onClick={onSelectAll}
            >
              全選
            </button>
            <button
              type="button"
              className="btn btn--small btn--secondary"
              onClick={onSelectNone}
            >
              全不選
            </button>
          </div>
        )}
      </div>

      {devices.length === 0 && (
        <div className="empty-state">
          <p>尚未連接任何裝置</p>
          <p className="empty-hint">
            請透過 USB 或 WiFi 連接 iOS 裝置
          </p>
        </div>
      )}

      <div className="device-list">
        {devices.map((device) => {
          const isSelected = selectedUdids.has(device.udid);
          const session = deviceSessions.get(device.udid);
          const simState: SimStateLabel = session?.simState ?? "idle";

          return (
            <button
              key={device.udid}
              type="button"
              className={`device-item ${isSelected ? "device-item--selected" : ""}`}
              onClick={() => onToggleDevice(device.udid)}
              title={`UDID: ${device.udid}`}
            >
              <div className="device-item__header">
                <input
                  type="checkbox"
                  className="device-item__checkbox"
                  checked={isSelected}
                  onChange={() => { /* handled by parent button click */ }}
                  tabIndex={-1}
                />
                <span
                  className={`device-item__indicator ${stateColorClass(device)}`}
                />
                <span className="device-item__name">
                  {device.name || "未知裝置"}
                </span>
                <SimStateIcon state={simState} />
              </div>
              <div className="device-item__details">
                <span className="device-item__version">
                  iOS {device.product_version}
                </span>
                <span className="device-item__class">{device.device_class}</span>
                <span className="device-item__state">
                  {formatState(device.state)}
                </span>
              </div>
              {device.error_message && (
                <div className="device-item__error">{device.error_message}</div>
              )}
            </button>
          );
        })}
      </div>
    </div>
  );
}
