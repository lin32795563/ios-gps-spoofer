/**
 * Tests for the DevicePanel component (multi-select version).
 *
 * Verifies:
 * - Empty state rendering
 * - Device list rendering with correct details
 * - Multi-select highlighting via checkbox
 * - Toggle handler invocation
 * - Select all / select none
 * - Error message display
 * - Simulation state icon display
 */

import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { DevicePanel } from "../components/DevicePanel";
import type { DeviceInfo, DeviceSessionState } from "../types/api";
import { createDefaultSession } from "../types/api";

function makeDevice(overrides: Partial<DeviceInfo> = {}): DeviceInfo {
  return {
    udid: "test-udid-001",
    name: "Test iPhone",
    product_type: "iPhone14,5",
    product_version: "17.2",
    build_version: "21C62",
    device_class: "iPhone",
    state: "ready",
    ios_category: "TUNNEL",
    is_ready: true,
    error_message: null,
    connected_at: "2024-01-01T00:00:00Z",
    last_seen_at: "2024-01-01T00:00:00Z",
    ...overrides,
  };
}

const emptyProps = {
  devices: [] as DeviceInfo[],
  selectedUdids: new Set<string>(),
  onToggleDevice: vi.fn(),
  deviceSessions: new Map<string, DeviceSessionState>(),
  onSelectAll: vi.fn(),
  onSelectNone: vi.fn(),
};

describe("DevicePanel", () => {
  it("should render empty state when no devices", () => {
    render(<DevicePanel {...emptyProps} />);

    expect(screen.getByText("尚未連接任何裝置")).toBeInTheDocument();
    expect(screen.getByText(/請透過 USB 或 WiFi 連接 iOS 裝置/)).toBeInTheDocument();
  });

  it("should not show select all/none when empty", () => {
    render(<DevicePanel {...emptyProps} />);

    expect(screen.queryByText("全選")).toBeNull();
    expect(screen.queryByText("全不選")).toBeNull();
  });

  it("should render device name and version", () => {
    const device = makeDevice({ name: "My iPhone 15", product_version: "17.2" });

    render(
      <DevicePanel
        {...emptyProps}
        devices={[device]}
      />,
    );

    expect(screen.getByText("My iPhone 15")).toBeInTheDocument();
    expect(screen.getByText("iOS 17.2")).toBeInTheDocument();
  });

  it("should show '未知裝置' when name is empty", () => {
    const device = makeDevice({ name: "" });

    render(
      <DevicePanel
        {...emptyProps}
        devices={[device]}
      />,
    );

    expect(screen.getByText("未知裝置")).toBeInTheDocument();
  });

  it("should highlight selected device", () => {
    const device = makeDevice({ udid: "selected-udid" });

    const { container } = render(
      <DevicePanel
        {...emptyProps}
        devices={[device]}
        selectedUdids={new Set(["selected-udid"])}
      />,
    );

    const button = container.querySelector(".device-item--selected");
    expect(button).toBeInTheDocument();
  });

  it("should not highlight unselected device", () => {
    const device = makeDevice({ udid: "other-udid" });

    const { container } = render(
      <DevicePanel
        {...emptyProps}
        devices={[device]}
        selectedUdids={new Set(["selected-udid"])}
      />,
    );

    const button = container.querySelector(".device-item--selected");
    expect(button).toBeNull();
  });

  it("should call onToggleDevice when device is clicked", async () => {
    const user = userEvent.setup();
    const handleToggle = vi.fn();
    const device = makeDevice({ udid: "click-me" });

    render(
      <DevicePanel
        {...emptyProps}
        devices={[device]}
        onToggleDevice={handleToggle}
      />,
    );

    await user.click(screen.getByText("Test iPhone"));

    expect(handleToggle).toHaveBeenCalledWith("click-me");
  });

  it("should display error message when present", () => {
    const device = makeDevice({
      is_ready: false,
      error_message: "DDI mount failed",
      state: "error",
    });

    render(
      <DevicePanel
        {...emptyProps}
        devices={[device]}
      />,
    );

    expect(screen.getByText("DDI mount failed")).toBeInTheDocument();
  });

  it("should show ready indicator for ready devices", () => {
    const device = makeDevice({ is_ready: true });

    const { container } = render(
      <DevicePanel
        {...emptyProps}
        devices={[device]}
      />,
    );

    const indicator = container.querySelector(".state-ready");
    expect(indicator).toBeInTheDocument();
  });

  it("should show error indicator for devices with errors", () => {
    const device = makeDevice({
      is_ready: false,
      error_message: "Connection lost",
    });

    const { container } = render(
      <DevicePanel
        {...emptyProps}
        devices={[device]}
      />,
    );

    const indicator = container.querySelector(".state-error");
    expect(indicator).toBeInTheDocument();
  });

  it("should render multiple devices", () => {
    const devices = [
      makeDevice({ udid: "d1", name: "iPhone A" }),
      makeDevice({ udid: "d2", name: "iPhone B" }),
      makeDevice({ udid: "d3", name: "iPhone C" }),
    ];

    render(
      <DevicePanel
        {...emptyProps}
        devices={devices}
      />,
    );

    expect(screen.getByText("iPhone A")).toBeInTheDocument();
    expect(screen.getByText("iPhone B")).toBeInTheDocument();
    expect(screen.getByText("iPhone C")).toBeInTheDocument();
  });

  it("should display device class", () => {
    const device = makeDevice({ device_class: "iPad" });

    render(
      <DevicePanel
        {...emptyProps}
        devices={[device]}
      />,
    );

    expect(screen.getByText("iPad")).toBeInTheDocument();
  });

  it("should show select all/none buttons when devices exist", () => {
    const device = makeDevice();

    render(
      <DevicePanel
        {...emptyProps}
        devices={[device]}
      />,
    );

    expect(screen.getByText("全選")).toBeInTheDocument();
    expect(screen.getByText("全不選")).toBeInTheDocument();
  });

  it("should call onSelectAll when clicked", async () => {
    const user = userEvent.setup();
    const handleSelectAll = vi.fn();
    const device = makeDevice();

    render(
      <DevicePanel
        {...emptyProps}
        devices={[device]}
        onSelectAll={handleSelectAll}
      />,
    );

    await user.click(screen.getByText("全選"));
    expect(handleSelectAll).toHaveBeenCalled();
  });

  it("should call onSelectNone when clicked", async () => {
    const user = userEvent.setup();
    const handleSelectNone = vi.fn();
    const device = makeDevice();

    render(
      <DevicePanel
        {...emptyProps}
        devices={[device]}
        onSelectNone={handleSelectNone}
      />,
    );

    await user.click(screen.getByText("全不選"));
    expect(handleSelectNone).toHaveBeenCalled();
  });

  it("should show running sim state icon", () => {
    const device = makeDevice({ udid: "d1" });
    const sessions = new Map<string, DeviceSessionState>();
    sessions.set("d1", { ...createDefaultSession(), simState: "running" });

    const { container } = render(
      <DevicePanel
        {...emptyProps}
        devices={[device]}
        deviceSessions={sessions}
      />,
    );

    const icon = container.querySelector(".sim-state-icon--running");
    expect(icon).toBeInTheDocument();
  });

  it("should show checkbox checked for selected devices", () => {
    const device = makeDevice({ udid: "d1" });

    render(
      <DevicePanel
        {...emptyProps}
        devices={[device]}
        selectedUdids={new Set(["d1"])}
      />,
    );

    const checkbox = screen.getByRole("checkbox");
    expect(checkbox).toBeChecked();
  });

  it("should show checkbox unchecked for unselected devices", () => {
    const device = makeDevice({ udid: "d1" });

    render(
      <DevicePanel
        {...emptyProps}
        devices={[device]}
        selectedUdids={new Set()}
      />,
    );

    const checkbox = screen.getByRole("checkbox");
    expect(checkbox).not.toBeChecked();
  });
});
