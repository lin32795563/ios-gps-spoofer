/**
 * Tests for the StatusBar component (multi-select version).
 *
 * Verifies:
 * - Backend connection status display
 * - WebSocket connection status display
 * - Device count and selected count display
 * - Simulation state display
 * - Correct CSS classes for status indicators
 */

import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { StatusBar } from "../components/StatusBar";

const baseProps = {
  backendReady: true,
  wsConnected: true,
  deviceCount: 1,
  selectedCount: 0,
  simState: "idle" as const,
};

describe("StatusBar", () => {
  it("should show backend connected when healthy", () => {
    render(<StatusBar {...baseProps} />);

    expect(screen.getByText(/後端：已連線/)).toBeInTheDocument();
  });

  it("should show backend disconnected when unhealthy", () => {
    render(
      <StatusBar {...baseProps} backendReady={false} wsConnected={false} deviceCount={0} />,
    );

    expect(screen.getByText(/後端：未連線/)).toBeInTheDocument();
  });

  it("should show WebSocket connected status", () => {
    render(<StatusBar {...baseProps} />);

    expect(screen.getByText(/WebSocket：已連線/)).toBeInTheDocument();
  });

  it("should show WebSocket disconnected status", () => {
    render(<StatusBar {...baseProps} wsConnected={false} />);

    expect(screen.getByText(/WebSocket：未連線/)).toBeInTheDocument();
  });

  it("should show device count and selected count", () => {
    render(<StatusBar {...baseProps} deviceCount={3} selectedCount={2} />);

    expect(screen.getByText(/裝置：3 \(已選 2\)/)).toBeInTheDocument();
  });

  it("should show simulation state idle", () => {
    render(<StatusBar {...baseProps} />);

    expect(screen.getByText(/模擬：閒置/)).toBeInTheDocument();
  });

  it("should show simulation state running", () => {
    render(<StatusBar {...baseProps} simState="running" />);

    expect(screen.getByText(/模擬：模擬中/)).toBeInTheDocument();
  });

  it("should show simulation state paused", () => {
    render(<StatusBar {...baseProps} simState="paused" />);

    expect(screen.getByText(/模擬：已暫停/)).toBeInTheDocument();
  });

  it("should show simulation state completed", () => {
    render(<StatusBar {...baseProps} simState="completed" />);

    expect(screen.getByText(/模擬：已完成/)).toBeInTheDocument();
  });

  it("should show simulation state error", () => {
    render(<StatusBar {...baseProps} simState="error" />);

    expect(screen.getByText(/模擬：錯誤/)).toBeInTheDocument();
  });

  it("should use green indicator for healthy backend", () => {
    const { container } = render(<StatusBar {...baseProps} />);

    const indicators = container.querySelectorAll(".status-indicator--ok");
    expect(indicators.length).toBeGreaterThanOrEqual(1);
  });

  it("should use red indicator for unhealthy backend", () => {
    const { container } = render(
      <StatusBar {...baseProps} backendReady={false} />,
    );

    const indicators = container.querySelectorAll(".status-indicator--error");
    expect(indicators.length).toBe(1);
  });

  it("should use warning indicator for disconnected WebSocket", () => {
    const { container } = render(
      <StatusBar {...baseProps} wsConnected={false} />,
    );

    const indicators = container.querySelectorAll(".status-indicator--warn");
    expect(indicators.length).toBe(1);
  });
});
