/**
 * Tests for the StatusBar component.
 *
 * Verifies:
 * - Backend connection status display
 * - WebSocket connection status display
 * - Device count display
 * - Simulation state display
 * - Correct CSS classes for status indicators
 */

import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { StatusBar } from "../components/StatusBar";

describe("StatusBar", () => {
  it("should show backend connected when healthy", () => {
    render(
      <StatusBar
        backendReady={true}
        wsConnected={true}
        deviceCount={1}
        simState="idle"
      />,
    );

    expect(screen.getByText("Backend: Connected")).toBeInTheDocument();
  });

  it("should show backend disconnected when unhealthy", () => {
    render(
      <StatusBar
        backendReady={false}
        wsConnected={false}
        deviceCount={0}
        simState="idle"
      />,
    );

    expect(screen.getByText("Backend: Disconnected")).toBeInTheDocument();
  });

  it("should show WebSocket connected status", () => {
    render(
      <StatusBar
        backendReady={true}
        wsConnected={true}
        deviceCount={0}
        simState="idle"
      />,
    );

    expect(screen.getByText("WebSocket: Connected")).toBeInTheDocument();
  });

  it("should show WebSocket disconnected status", () => {
    render(
      <StatusBar
        backendReady={true}
        wsConnected={false}
        deviceCount={0}
        simState="idle"
      />,
    );

    expect(screen.getByText("WebSocket: Disconnected")).toBeInTheDocument();
  });

  it("should show device count", () => {
    render(
      <StatusBar
        backendReady={true}
        wsConnected={true}
        deviceCount={3}
        simState="idle"
      />,
    );

    expect(screen.getByText("Devices: 3")).toBeInTheDocument();
  });

  it("should show simulation state idle", () => {
    render(
      <StatusBar
        backendReady={true}
        wsConnected={true}
        deviceCount={0}
        simState="idle"
      />,
    );

    expect(screen.getByText("Simulation: Idle")).toBeInTheDocument();
  });

  it("should show simulation state running", () => {
    render(
      <StatusBar
        backendReady={true}
        wsConnected={true}
        deviceCount={1}
        simState="running"
      />,
    );

    expect(screen.getByText("Simulation: Running")).toBeInTheDocument();
  });

  it("should show simulation state paused", () => {
    render(
      <StatusBar
        backendReady={true}
        wsConnected={true}
        deviceCount={1}
        simState="paused"
      />,
    );

    expect(screen.getByText("Simulation: Paused")).toBeInTheDocument();
  });

  it("should use green indicator for healthy backend", () => {
    const { container } = render(
      <StatusBar
        backendReady={true}
        wsConnected={true}
        deviceCount={0}
        simState="idle"
      />,
    );

    const indicators = container.querySelectorAll(".status-indicator--ok");
    expect(indicators.length).toBeGreaterThanOrEqual(1);
  });

  it("should use red indicator for unhealthy backend", () => {
    const { container } = render(
      <StatusBar
        backendReady={false}
        wsConnected={true}
        deviceCount={0}
        simState="idle"
      />,
    );

    const indicators = container.querySelectorAll(".status-indicator--error");
    expect(indicators.length).toBe(1);
  });

  it("should use warning indicator for disconnected WebSocket", () => {
    const { container } = render(
      <StatusBar
        backendReady={true}
        wsConnected={false}
        deviceCount={0}
        simState="idle"
      />,
    );

    const indicators = container.querySelectorAll(".status-indicator--warn");
    expect(indicators.length).toBe(1);
  });

  it("should display unknown states as-is", () => {
    render(
      <StatusBar
        backendReady={true}
        wsConnected={true}
        deviceCount={0}
        simState="custom_state"
      />,
    );

    expect(screen.getByText("Simulation: custom_state")).toBeInTheDocument();
  });
});
