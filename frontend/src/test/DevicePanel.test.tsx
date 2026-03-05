/**
 * Tests for the DevicePanel component.
 *
 * Verifies:
 * - Empty state rendering
 * - Device list rendering with correct details
 * - Device selection highlighting
 * - Click handler invocation
 * - Error message display
 */

import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { DevicePanel } from "../components/DevicePanel";
import type { DeviceInfo } from "../types/api";

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

describe("DevicePanel", () => {
  it("should render empty state when no devices", () => {
    render(
      <DevicePanel
        devices={[]}
        selectedUdid={null}
        onSelectDevice={vi.fn()}
      />,
    );

    expect(screen.getByText("No devices connected.")).toBeInTheDocument();
    expect(screen.getByText(/Connect an iOS device/)).toBeInTheDocument();
  });

  it("should render device name and version", () => {
    const device = makeDevice({ name: "My iPhone 15", product_version: "17.2" });

    render(
      <DevicePanel
        devices={[device]}
        selectedUdid={null}
        onSelectDevice={vi.fn()}
      />,
    );

    expect(screen.getByText("My iPhone 15")).toBeInTheDocument();
    expect(screen.getByText("iOS 17.2")).toBeInTheDocument();
  });

  it("should show 'Unknown Device' when name is empty", () => {
    const device = makeDevice({ name: "" });

    render(
      <DevicePanel
        devices={[device]}
        selectedUdid={null}
        onSelectDevice={vi.fn()}
      />,
    );

    expect(screen.getByText("Unknown Device")).toBeInTheDocument();
  });

  it("should highlight selected device", () => {
    const device = makeDevice({ udid: "selected-udid" });

    const { container } = render(
      <DevicePanel
        devices={[device]}
        selectedUdid="selected-udid"
        onSelectDevice={vi.fn()}
      />,
    );

    const button = container.querySelector(".device-item--selected");
    expect(button).toBeInTheDocument();
  });

  it("should not highlight unselected device", () => {
    const device = makeDevice({ udid: "other-udid" });

    const { container } = render(
      <DevicePanel
        devices={[device]}
        selectedUdid="selected-udid"
        onSelectDevice={vi.fn()}
      />,
    );

    const button = container.querySelector(".device-item--selected");
    expect(button).toBeNull();
  });

  it("should call onSelectDevice when device is clicked", async () => {
    const user = userEvent.setup();
    const handleSelect = vi.fn();
    const device = makeDevice({ udid: "click-me" });

    render(
      <DevicePanel
        devices={[device]}
        selectedUdid={null}
        onSelectDevice={handleSelect}
      />,
    );

    await user.click(screen.getByText("Test iPhone"));

    expect(handleSelect).toHaveBeenCalledWith("click-me");
  });

  it("should display error message when present", () => {
    const device = makeDevice({
      is_ready: false,
      error_message: "DDI mount failed",
      state: "error",
    });

    render(
      <DevicePanel
        devices={[device]}
        selectedUdid={null}
        onSelectDevice={vi.fn()}
      />,
    );

    expect(screen.getByText("DDI mount failed")).toBeInTheDocument();
  });

  it("should show ready indicator for ready devices", () => {
    const device = makeDevice({ is_ready: true });

    const { container } = render(
      <DevicePanel
        devices={[device]}
        selectedUdid={null}
        onSelectDevice={vi.fn()}
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
        devices={[device]}
        selectedUdid={null}
        onSelectDevice={vi.fn()}
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
        devices={devices}
        selectedUdid={null}
        onSelectDevice={vi.fn()}
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
        devices={[device]}
        selectedUdid={null}
        onSelectDevice={vi.fn()}
      />,
    );

    expect(screen.getByText("iPad")).toBeInTheDocument();
  });

  it("should format device state for display", () => {
    const device = makeDevice({ state: "tunnel_active" });

    render(
      <DevicePanel
        devices={[device]}
        selectedUdid={null}
        onSelectDevice={vi.fn()}
      />,
    );

    expect(screen.getByText("Tunnel Active")).toBeInTheDocument();
  });
});
