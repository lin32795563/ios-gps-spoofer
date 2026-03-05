/**
 * Tests for the ControlPanel component.
 *
 * Verifies:
 * - Conditional rendering based on device state
 * - Speed preset and slider controls
 * - Simulation state-dependent button rendering
 * - Progress display
 * - Favorite management
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ControlPanel } from "../components/ControlPanel";
import type {
  DeviceInfo,
  FavoriteLocation,
  SimulationProgress,
} from "../types/api";

function makeDevice(overrides: Partial<DeviceInfo> = {}): DeviceInfo {
  return {
    udid: "test-udid",
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

function makeProgress(
  overrides: Partial<SimulationProgress> = {},
): SimulationProgress {
  return {
    current_position: { latitude: 37.0, longitude: -122.0 },
    segment_index: 2,
    total_segments: 10,
    distance_covered_m: 500,
    total_distance_m: 2000,
    fraction_complete: 0.25,
    elapsed_time_s: 120,
    speed_ms: 1.39,
    state: "running",
    ...overrides,
  };
}

const defaultHandlers = {
  onStartSimulation: vi.fn(),
  onPause: vi.fn(),
  onResume: vi.fn(),
  onStop: vi.fn(),
  onSpeedChange: vi.fn(),
  onClearLocation: vi.fn(),
  onToggleDrawPath: vi.fn(),
  onClearPath: vi.fn(),
  onGPXLoad: vi.fn(),
  onAddFavorite: vi.fn(),
  onRemoveFavorite: vi.fn(),
  onSelectFavorite: vi.fn(),
};

beforeEach(() => {
  Object.values(defaultHandlers).forEach((fn) => fn.mockClear());
});

describe("ControlPanel", () => {
  describe("no device selected", () => {
    it("should show prompt to select device", () => {
      render(
        <ControlPanel
          selectedDevice={null}
          simState="idle"
          simProgress={null}
          speedKmh={5}
          isDrawingPath={false}
          pathPointCount={0}
          favorites={[]}
          {...defaultHandlers}
        />,
      );

      expect(screen.getByText(/Select a device/)).toBeInTheDocument();
    });

    it("should not show simulation controls", () => {
      render(
        <ControlPanel
          selectedDevice={null}
          simState="idle"
          simProgress={null}
          speedKmh={5}
          isDrawingPath={false}
          pathPointCount={0}
          favorites={[]}
          {...defaultHandlers}
        />,
      );

      expect(screen.queryByText("Restore Real Location")).toBeNull();
      expect(screen.queryByText("Start")).toBeNull();
    });
  });

  describe("device not ready", () => {
    it("should show warning when device is not ready", () => {
      const device = makeDevice({ is_ready: false, state: "connected" });

      render(
        <ControlPanel
          selectedDevice={device}
          simState="idle"
          simProgress={null}
          speedKmh={5}
          isDrawingPath={false}
          pathPointCount={0}
          favorites={[]}
          {...defaultHandlers}
        />,
      );

      expect(screen.getByText(/not ready/)).toBeInTheDocument();
    });

    it("should show error message if present", () => {
      const device = makeDevice({
        is_ready: false,
        error_message: "DDI failed",
      });

      render(
        <ControlPanel
          selectedDevice={device}
          simState="idle"
          simProgress={null}
          speedKmh={5}
          isDrawingPath={false}
          pathPointCount={0}
          favorites={[]}
          {...defaultHandlers}
        />,
      );

      expect(screen.getByText("DDI failed")).toBeInTheDocument();
    });
  });

  describe("location controls", () => {
    it("should render Restore Real Location button", () => {
      render(
        <ControlPanel
          selectedDevice={makeDevice()}
          simState="idle"
          simProgress={null}
          speedKmh={5}
          isDrawingPath={false}
          pathPointCount={0}
          favorites={[]}
          {...defaultHandlers}
        />,
      );

      expect(screen.getByText("Restore Real Location")).toBeInTheDocument();
    });

    it("should call onClearLocation when clicked", async () => {
      const user = userEvent.setup();

      render(
        <ControlPanel
          selectedDevice={makeDevice()}
          simState="idle"
          simProgress={null}
          speedKmh={5}
          isDrawingPath={false}
          pathPointCount={0}
          favorites={[]}
          {...defaultHandlers}
        />,
      );

      await user.click(screen.getByText("Restore Real Location"));
      expect(defaultHandlers.onClearLocation).toHaveBeenCalled();
    });

    it("should disable restore button during simulation", () => {
      render(
        <ControlPanel
          selectedDevice={makeDevice()}
          simState="running"
          simProgress={makeProgress()}
          speedKmh={5}
          isDrawingPath={false}
          pathPointCount={0}
          favorites={[]}
          {...defaultHandlers}
        />,
      );

      expect(screen.getByText("Restore Real Location")).toBeDisabled();
    });
  });

  describe("path drawing", () => {
    it("should show Draw Path button", () => {
      render(
        <ControlPanel
          selectedDevice={makeDevice()}
          simState="idle"
          simProgress={null}
          speedKmh={5}
          isDrawingPath={false}
          pathPointCount={0}
          favorites={[]}
          {...defaultHandlers}
        />,
      );

      expect(screen.getByText("Draw Path")).toBeInTheDocument();
    });

    it("should show Stop Drawing when drawing", () => {
      render(
        <ControlPanel
          selectedDevice={makeDevice()}
          simState="idle"
          simProgress={null}
          speedKmh={5}
          isDrawingPath={true}
          pathPointCount={3}
          favorites={[]}
          {...defaultHandlers}
        />,
      );

      expect(screen.getByText("Stop Drawing")).toBeInTheDocument();
    });

    it("should show point count when path has points", () => {
      render(
        <ControlPanel
          selectedDevice={makeDevice()}
          simState="idle"
          simProgress={null}
          speedKmh={5}
          isDrawingPath={false}
          pathPointCount={5}
          favorites={[]}
          {...defaultHandlers}
        />,
      );

      expect(screen.getByText("5 points")).toBeInTheDocument();
    });

    it("should call onClearPath when Clear Path is clicked", async () => {
      const user = userEvent.setup();

      render(
        <ControlPanel
          selectedDevice={makeDevice()}
          simState="idle"
          simProgress={null}
          speedKmh={5}
          isDrawingPath={false}
          pathPointCount={3}
          favorites={[]}
          {...defaultHandlers}
        />,
      );

      await user.click(screen.getByText("Clear Path"));
      expect(defaultHandlers.onClearPath).toHaveBeenCalled();
    });
  });

  describe("speed controls", () => {
    it("should display current speed", () => {
      render(
        <ControlPanel
          selectedDevice={makeDevice()}
          simState="idle"
          simProgress={null}
          speedKmh={15}
          isDrawingPath={false}
          pathPointCount={0}
          favorites={[]}
          {...defaultHandlers}
        />,
      );

      expect(screen.getByText(/15\.0 km\/h/)).toBeInTheDocument();
    });

    it("should render speed preset buttons", () => {
      render(
        <ControlPanel
          selectedDevice={makeDevice()}
          simState="idle"
          simProgress={null}
          speedKmh={5}
          isDrawingPath={false}
          pathPointCount={0}
          favorites={[]}
          {...defaultHandlers}
        />,
      );

      expect(screen.getByText("Walking")).toBeInTheDocument();
      expect(screen.getByText("Cycling")).toBeInTheDocument();
      expect(screen.getByText("Driving")).toBeInTheDocument();
      expect(screen.getByText("Fast")).toBeInTheDocument();
    });

    it("should call onSpeedChange when preset is clicked", async () => {
      const user = userEvent.setup();

      render(
        <ControlPanel
          selectedDevice={makeDevice()}
          simState="idle"
          simProgress={null}
          speedKmh={5}
          isDrawingPath={false}
          pathPointCount={0}
          favorites={[]}
          {...defaultHandlers}
        />,
      );

      await user.click(screen.getByText("Cycling"));
      expect(defaultHandlers.onSpeedChange).toHaveBeenCalledWith(15);
    });
  });

  describe("simulation controls", () => {
    it("should show Start button in idle state", () => {
      render(
        <ControlPanel
          selectedDevice={makeDevice()}
          simState="idle"
          simProgress={null}
          speedKmh={5}
          isDrawingPath={false}
          pathPointCount={5}
          favorites={[]}
          {...defaultHandlers}
        />,
      );

      expect(screen.getByText("Start")).toBeInTheDocument();
    });

    it("should disable Start when less than 2 path points", () => {
      render(
        <ControlPanel
          selectedDevice={makeDevice()}
          simState="idle"
          simProgress={null}
          speedKmh={5}
          isDrawingPath={false}
          pathPointCount={1}
          favorites={[]}
          {...defaultHandlers}
        />,
      );

      expect(screen.getByText("Start")).toBeDisabled();
    });

    it("should show Pause and Stop during running", () => {
      render(
        <ControlPanel
          selectedDevice={makeDevice()}
          simState="running"
          simProgress={makeProgress()}
          speedKmh={5}
          isDrawingPath={false}
          pathPointCount={5}
          favorites={[]}
          {...defaultHandlers}
        />,
      );

      expect(screen.getByText("Pause")).toBeInTheDocument();
      expect(screen.getByText("Stop")).toBeInTheDocument();
    });

    it("should show Resume and Stop when paused", () => {
      render(
        <ControlPanel
          selectedDevice={makeDevice()}
          simState="paused"
          simProgress={makeProgress({ state: "paused" })}
          speedKmh={5}
          isDrawingPath={false}
          pathPointCount={5}
          favorites={[]}
          {...defaultHandlers}
        />,
      );

      expect(screen.getByText("Resume")).toBeInTheDocument();
      expect(screen.getByText("Stop")).toBeInTheDocument();
    });

    it("should call onStartSimulation when Start clicked", async () => {
      const user = userEvent.setup();

      render(
        <ControlPanel
          selectedDevice={makeDevice()}
          simState="idle"
          simProgress={null}
          speedKmh={5}
          isDrawingPath={false}
          pathPointCount={5}
          favorites={[]}
          {...defaultHandlers}
        />,
      );

      await user.click(screen.getByText("Start"));
      expect(defaultHandlers.onStartSimulation).toHaveBeenCalled();
    });

    it("should call onPause when Pause clicked", async () => {
      const user = userEvent.setup();

      render(
        <ControlPanel
          selectedDevice={makeDevice()}
          simState="running"
          simProgress={makeProgress()}
          speedKmh={5}
          isDrawingPath={false}
          pathPointCount={5}
          favorites={[]}
          {...defaultHandlers}
        />,
      );

      await user.click(screen.getByText("Pause"));
      expect(defaultHandlers.onPause).toHaveBeenCalled();
    });
  });

  describe("progress display", () => {
    it("should show progress bar and details when simulation active", () => {
      render(
        <ControlPanel
          selectedDevice={makeDevice()}
          simState="running"
          simProgress={makeProgress({
            fraction_complete: 0.5,
            elapsed_time_s: 300,
            distance_covered_m: 1500,
            total_distance_m: 3000,
            segment_index: 5,
            total_segments: 10,
          })}
          speedKmh={5}
          isDrawingPath={false}
          pathPointCount={5}
          favorites={[]}
          {...defaultHandlers}
        />,
      );

      expect(screen.getByText("50.0%")).toBeInTheDocument();
      expect(screen.getByText("05:00")).toBeInTheDocument();
      expect(screen.getByText("1.50km / 3.00km")).toBeInTheDocument();
      expect(screen.getByText("Seg 6/10")).toBeInTheDocument();
    });

    it("should not show progress when simProgress is null", () => {
      render(
        <ControlPanel
          selectedDevice={makeDevice()}
          simState="idle"
          simProgress={null}
          speedKmh={5}
          isDrawingPath={false}
          pathPointCount={0}
          favorites={[]}
          {...defaultHandlers}
        />,
      );

      expect(screen.queryByText("Progress")).toBeNull();
    });
  });

  describe("favorites", () => {
    it("should show empty state when no favorites", () => {
      render(
        <ControlPanel
          selectedDevice={makeDevice()}
          simState="idle"
          simProgress={null}
          speedKmh={5}
          isDrawingPath={false}
          pathPointCount={0}
          favorites={[]}
          {...defaultHandlers}
        />,
      );

      expect(screen.getByText("No saved locations.")).toBeInTheDocument();
    });

    it("should render favorite locations", () => {
      const favorites: FavoriteLocation[] = [
        { name: "Home", latitude: 37.0, longitude: -122.0 },
        { name: "Work", latitude: 37.5, longitude: -122.5 },
      ];

      render(
        <ControlPanel
          selectedDevice={makeDevice()}
          simState="idle"
          simProgress={null}
          speedKmh={5}
          isDrawingPath={false}
          pathPointCount={0}
          favorites={favorites}
          {...defaultHandlers}
        />,
      );

      expect(screen.getByText("Home")).toBeInTheDocument();
      expect(screen.getByText("Work")).toBeInTheDocument();
    });

    it("should call onSelectFavorite when favorite clicked", async () => {
      const user = userEvent.setup();
      const fav = { name: "Home", latitude: 37.0, longitude: -122.0 };

      render(
        <ControlPanel
          selectedDevice={makeDevice()}
          simState="idle"
          simProgress={null}
          speedKmh={5}
          isDrawingPath={false}
          pathPointCount={0}
          favorites={[fav]}
          {...defaultHandlers}
        />,
      );

      await user.click(screen.getByText("Home"));
      expect(defaultHandlers.onSelectFavorite).toHaveBeenCalledWith(fav);
    });

    it("should call onRemoveFavorite when X clicked", async () => {
      const user = userEvent.setup();
      const fav = { name: "Home", latitude: 37.0, longitude: -122.0 };

      render(
        <ControlPanel
          selectedDevice={makeDevice()}
          simState="idle"
          simProgress={null}
          speedKmh={5}
          isDrawingPath={false}
          pathPointCount={0}
          favorites={[fav]}
          {...defaultHandlers}
        />,
      );

      await user.click(screen.getByLabelText("Remove Home"));
      expect(defaultHandlers.onRemoveFavorite).toHaveBeenCalledWith(0);
    });
  });
});
