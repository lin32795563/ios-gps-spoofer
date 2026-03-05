import type { DeviceInfo } from "../types/api";

interface DevicePanelProps {
  devices: DeviceInfo[];
  selectedUdid: string | null;
  onSelectDevice: (udid: string) => void;
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

export function DevicePanel({
  devices,
  selectedUdid,
  onSelectDevice,
}: DevicePanelProps) {
  return (
    <div className="device-panel">
      <h2 className="panel-title">裝置列表</h2>

      {devices.length === 0 && (
        <div className="empty-state">
          <p>尚未連接任何裝置</p>
          <p className="empty-hint">
            請透過 USB 連接 iOS 裝置
          </p>
        </div>
      )}

      <div className="device-list">
        {devices.map((device) => (
          <button
            key={device.udid}
            type="button"
            className={`device-item ${
              device.udid === selectedUdid ? "device-item--selected" : ""
            }`}
            onClick={() => onSelectDevice(device.udid)}
            title={`UDID: ${device.udid}`}
          >
            <div className="device-item__header">
              <span
                className={`device-item__indicator ${stateColorClass(device)}`}
              />
              <span className="device-item__name">
                {device.name || "未知裝置"}
              </span>
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
        ))}
      </div>
    </div>
  );
}
